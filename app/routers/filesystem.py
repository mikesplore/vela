import os
import shutil
import subprocess
import zipfile
from typing import Optional
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Any, List

import psutil
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import Config
from app.dependencies import get_current_user

config = Config()
router = APIRouter(prefix="/fs", tags=["filesystem"])


def _resolve_path(path_str: str) -> Path:
    # Expand user (~) first, then treat relative paths as relative to cwd
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _is_allowed(path: Path) -> bool:
    allowed_dirs = [Path(p).expanduser().resolve() for p in config.allowed_base_dirs]
    if not allowed_dirs:
        return True
    return any(path == base or path.is_relative_to(base) for base in allowed_dirs)


def _validate_path(path_str: str, must_exist: bool = False) -> Path:
    if not path_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path is required")
    path = _resolve_path(path_str)
    if not _is_allowed(path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path is outside allowed base directories")
    if must_exist and not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found")
    return path


def _file_entry(path: Path, include_tree_meta: bool = True) -> dict[str, Any]:
    """Create a file/folder entry with optional tree metadata."""
    stat = path.stat()
    is_dir = path.is_dir()
    entry = {
        "name": path.name,
        "path": str(path),
        "type": "directory" if is_dir else "file",
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }
    
    # Add tree navigation metadata
    if include_tree_meta:
        if is_dir:
            try:
                # Count immediate children (files and folders)
                children = list(path.iterdir())
                entry["has_children"] = len(children) > 0
                entry["children_count"] = len(children)
            except (OSError, PermissionError):
                entry["has_children"] = False
                entry["children_count"] = 0
        else:
            # For files, add extension info for better filtering
            entry["extension"] = path.suffix.lower() if path.suffix else ""
    
    return entry


class FileEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    size: int
    modified: float
    has_children: bool | None = None  # Only for directories
    children_count: int | None = None  # Only for directories
    extension: str | None = None  # Only for files


class FileListResponse(BaseModel):
    files: List[FileEntry]
    current_path: str  # The path being listed
    parent_path: str | None  # Parent directory path for navigation
    total_items: int  # Total items in the current directory


class FileActionResponse(BaseModel):
    success: bool
    message: str


class PathRequest(BaseModel):
    path: str


class RenameRequest(BaseModel):
    from_path: str = Field(..., alias="from")
    to_path: str = Field(..., alias="to")

    model_config = {
        "populate_by_name": True,
    }


class ZipRequest(BaseModel):
    paths: List[str]
    output: str


class UnzipRequest(BaseModel):
    path: str
    destination: str


@router.get("/list", response_model=FileListResponse, dependencies=[Depends(get_current_user)])
async def list_files(
    path: str = Query("."), 
    show_hidden: bool = Query(False)  # 👈 1. Accept the boolean toggle parameter here
) -> Any:
    """List directory contents (files and folders) for tree navigation."""
    target = _validate_path(path, must_exist=True)
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a directory")
    
    # Get parent path for navigation (if not root)
    parent_path = None
    try:
        parent = target.parent
        if parent != target and _is_allowed(parent):  # Not root and is allowed
            parent_path = str(parent)
    except (OSError, ValueError):
        pass
    
    # List all items (both files and folders), sorted with folders first
    items = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        for child in children:
            # 👈 2. THE FIX: If show_hidden is False, skip items starting with a dot (.)
            if not show_hidden and child.name.startswith("."):
                continue
                
            try:
                entry_dict = _file_entry(child, include_tree_meta=True)
                items.append(FileEntry(**entry_dict))
            except (OSError, PermissionError):
                # Skip items we can't access
                continue
    except (OSError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Cannot read directory: {exc}")
    
    return FileListResponse(
        files=items,
        current_path=str(target),
        parent_path=parent_path,
        total_items=len(items)
    )


class TreeNode(BaseModel):
    name: str
    path: str
    type: str  # "directory" or "file"
    size: int
    modified: float
    
    # Crucial Fixes here: Allow them to swallow None gracefully
    has_children: Optional[bool] = Field(default=None)
    children_count: Optional[int] = Field(default=None)
    
    # Extension can stay optional as well
    extension: Optional[str] = None


class TreeResponse(BaseModel):
    """Response for tree-based folder navigation."""
    root: TreeNode
    children: List[TreeNode]
    breadcrumbs: List[dict[str, str]]  # Path navigation breadcrumbs


@router.get("/tree", response_model=TreeResponse, dependencies=[Depends(get_current_user)])
async def get_directory_tree(path: str = Query("."), max_depth: int = Query(1, ge=1, le=3)) -> Any:
    """Get directory tree structure for folder navigation.
    
    max_depth: How many levels deep to traverse (1-3 for performance).
    """
    target = _validate_path(path, must_exist=True)
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a directory")
    
    # Build breadcrumbs for current path
    breadcrumbs = []
    current = target
    allowed_dirs = [Path(p).expanduser().resolve() for p in config.allowed_base_dirs] or [Path("/")]
    
    while current != current.parent:
        breadcrumbs.insert(0, {"name": current.name or "/", "path": str(current)})
        if current in allowed_dirs:
            break
        current = current.parent
    
    # Create root node
    root_entry = _file_entry(target, include_tree_meta=True)
    root_node = TreeNode(
        name=target.name or str(target),
        path=str(target),
        type="directory",
        **{k: root_entry.get(k) for k in ["has_children", "children_count", "size", "modified"]}
    )
    
    # Get children
    children = []
    try:
        items = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        for child in items:
            try:
                entry_dict = _file_entry(child, include_tree_meta=True)
                children.append(TreeNode(
                    name=child.name,
                    path=str(child),
                    type=entry_dict["type"],
                    **{k: entry_dict.get(k) for k in ["has_children", "children_count", "size", "modified"]}
                ))
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Cannot read directory: {exc}")
    
    return TreeResponse(
        root=root_node,
        children=children,
        breadcrumbs=breadcrumbs
    )


@router.get("/download", dependencies=[Depends(get_current_user)])
async def download_file(path: str = Query(...)) -> FileResponse:
    """Download a file from the filesystem."""
    target = _validate_path(path, must_exist=True)
    if target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a file")
    return FileResponse(path=target, filename=target.name, media_type="application/octet-stream")


@router.post("/upload", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def upload_file(path: str = Form(...), file: UploadFile = File(...)) -> Any:
    """Upload a file to the given destination path."""
    target = _validate_path(path)
    if target.exists() and target.is_dir():
        target_path = target / file.filename
    else:
        target_path = target
    if not _is_allowed(target_path.parent):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Destination is outside allowed base directories")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target_path.open("wb") as out_file:
            content = await file.read()
            out_file.write(content)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return FileActionResponse(success=True, message=f"Uploaded file to {target_path}")


@router.delete("/delete", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def delete_path(request: PathRequest) -> Any:
    """Permanently delete a file, symlink, or directory safely."""
    target = _validate_path(request.path, must_exist=True)
    
    try:
        # Check if it's a directory, but ensure it's NOT a symlink
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
            message = f"Successfully deleted directory: {target.name}"
        else:
            # Safely deletes files, symlinks, broken links, or sockets
            target.unlink()
            message = f"Successfully deleted file: {target.name}"
            
        return FileActionResponse(success=True, message=message)
        
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: Unable to delete '{target.name}'"
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to delete target: {str(exc)}"
        )


@router.post("/mkdir", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def make_directory(request: PathRequest) -> Any:
    """Create a new directory."""
    target = _validate_path(request.path)
    if target.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory already exists")
    try:
        target.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return FileActionResponse(success=True, message=f"Created directory {target}")


@router.post("/rename", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def rename_path(request: RenameRequest) -> Any:
    """Rename or move a file or directory."""
    source = _validate_path(request.from_path, must_exist=True)
    destination = _validate_path(request.to_path)
    if destination.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source.replace(destination)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return FileActionResponse(success=True, message=f"Renamed {source} to {destination}")


class SystemConfigResponse(BaseModel):
    home_directory: str
    username: str

@router.get("/config", response_model=SystemConfigResponse, dependencies=[Depends(get_current_user)])
async def get_system_config() -> Any:
    """Retrieve runtime host environment configurations for app initialization."""
    home_path = Path.home()
    return SystemConfigResponse(
        home_directory=str(home_path),
        username=home_path.name
    )


@router.get("/search", response_model=FileListResponse, dependencies=[Depends(get_current_user)])
async def search_files(query: str = Query(...), path: str = Query(".")) -> Any:
    """Search for files and directories by name with tree-enabled results."""
    target = _validate_path(path, must_exist=True)
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a directory")
        
    
    matches: List[FileEntry] = []
    try:
        for root, dirs, files in os.walk(target):
            # Search in files
            for name in files:
                if query.lower() in name.lower():
                    entry_dict = _file_entry(Path(root) / name)
                    matches.append(FileEntry(**entry_dict))
            # Search in directories
            for name in dirs:
                if query.lower() in name.lower():
                    entry_dict = _file_entry(Path(root) / name)
                    matches.append(FileEntry(**entry_dict))
    except (OSError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Search failed: {exc}")
    
    # Sort results: folders first, then by name
    matches.sort(key=lambda x: (x.type != "directory", x.name.lower()))
    
    return FileListResponse(
        files=matches,
        current_path=str(target),
        parent_path=None,
        total_items=len(matches)
    )


class DiskUsageEntry(BaseModel):
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float
    filesystem: str


class DiskUsageResponse(BaseModel):
    usage: List[DiskUsageEntry]


@router.get("/disk-usage", response_model=DiskUsageResponse, dependencies=[Depends(get_current_user)])
async def disk_usage() -> Any:
    """Return disk usage statistics for mounted partitions."""
    usage_list: List[DiskUsageEntry] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        usage_list.append(
            DiskUsageEntry(
                mountpoint=part.mountpoint,
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
                filesystem=part.fstype,
            )
        )
    return DiskUsageResponse(usage=usage_list)


class ZipRequest(BaseModel):
    paths: List[str]
    output: str


@router.post("/zip", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def zip_paths(request: ZipRequest) -> Any:
    """Create a zip archive from files and directories."""
    output = _validate_path(request.output)
    if output.suffix.lower() != ".zip":
        output = output.with_suffix(".zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path_str in request.paths:
                source = _validate_path(path_str, must_exist=True)
                if source.is_file():
                    archive.write(source, arcname=source.name)
                else:
                    for root, _, files in os.walk(source):
                        for file_name in files:
                            source_path = Path(root) / file_name
                            archive.write(source_path, arcname=source_path.relative_to(source.parent))
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return FileActionResponse(success=True, message=f"Created archive {output}")


class UnzipRequest(BaseModel):
    path: str
    destination: str


@router.post("/unzip", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def unzip_path(request: UnzipRequest) -> Any:
    """Extract a zip archive to a destination directory."""
    source = _validate_path(request.path, must_exist=True)
    destination = _validate_path(request.destination)
    if source.suffix.lower() != ".zip":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source file must be a .zip archive")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            archive.extractall(destination)
    except (OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return FileActionResponse(success=True, message=f"Extracted archive to {destination}")


@router.post("/open", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def open_path(request: PathRequest) -> Any:
    """Open a file or directory with the default system application."""
    target = _validate_path(request.path, must_exist=True)
    process = subprocess.run(["xdg-open", str(target)], capture_output=True, text=True, timeout=10, check=False)
    if process.returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=process.stderr or "Could not open path")
    return FileActionResponse(success=True, message=f"Opened {target}")
