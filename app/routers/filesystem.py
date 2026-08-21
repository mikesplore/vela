import os
import shutil
import subprocess
import stat
import tempfile
import zipfile
from typing import Optional
from pathlib import Path
from typing import Any, List

import psutil
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.utils.config import get_config
from app.dependencies import get_current_user
from app.domain.filesystem import FileListResponse, FileEntry, FileActionResponse, PathRequest, RenameRequest
from app.services.filesystem import validate_path, file_entry, is_allowed, resolve_search_roots
from app.utils.list_limits import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT

config = get_config()
router = APIRouter(prefix="/fs", tags=["filesystem"])


def _reject_symlinked_parents(path: Path) -> None:
    """Reject symlink components before a mutating operation."""
    current = path.expanduser()
    if not current.is_absolute():
        current = Path.cwd() / current
    current = Path(os.path.abspath(str(current)))
    for component in current.parts:
        if component == current.anchor:
            candidate = Path(component)
        else:
            candidate = candidate / component
        current_component = candidate
        if current_component.is_symlink():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Symlinked paths are not permitted")


def _safe_upload_destination(target: Path, filename: str | None) -> Path:
    if target.exists() and target.is_dir():
        safe_name = Path(filename or "upload.bin").name
        if safe_name in {"", ".", ".."}:
            raise HTTPException(status_code=400, detail="Invalid upload filename")
        target = target / safe_name
    target = target.resolve(strict=False)
    if not is_allowed(target) or not is_allowed(target.parent):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Destination is outside allowed base directories")
    _reject_symlinked_parents(target.parent)
    return target




@router.get("/list", response_model=FileListResponse, dependencies=[Depends(get_current_user)])
async def list_files(
    path: str = Query("."), 
    show_hidden: bool = Query(False),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
) -> Any:
    """List directory contents (files and folders) for tree navigation."""
    target = validate_path(path, must_exist=True)
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a directory")
    
    # Get parent path for navigation (if not root)
    parent_path = None
    try:
        parent = target.parent
        if parent != target and is_allowed(parent):  # Not root and is allowed
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
                entry_dict = file_entry(child, include_tree_meta=True)
                items.append(FileEntry(**entry_dict))
            except (OSError, PermissionError):
                # Skip items we can't access
                continue
    except (OSError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Cannot read directory: {exc}")
    
    total_items = len(items)
    return FileListResponse(
        files=items[:limit],
        current_path=str(target),
        parent_path=parent_path,
        total_items=total_items,
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
    target = validate_path(path, must_exist=True)
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
    root_entry = file_entry(target, include_tree_meta=True)
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
                entry_dict = file_entry(child, include_tree_meta=True)
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
    target = validate_path(path, must_exist=True)
    if target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a file")
    return FileResponse(path=target, filename=target.name, media_type="application/octet-stream")


@router.post("/upload", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def upload_file(path: str = Form(...), file: UploadFile = File(...)) -> Any:
    """Upload a file to the given destination path."""
    target = validate_path(path)
    _reject_symlinked_parents(Path(path).expanduser())
    target_path = _safe_upload_destination(target, file.filename)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    total = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target_path.parent, prefix=f".{target_path.name}.", suffix=".upload", delete=False
        ) as out_file:
            temp_path = Path(out_file.name)
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > config.max_upload_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload is too large")
                out_file.write(chunk)
        os.replace(temp_path, target_path)
        temp_path = None
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    finally:
        await file.close()
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
    return FileActionResponse(success=True, message=f"Uploaded file to {target_path}")


@router.delete("/delete", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def delete_path(request: PathRequest) -> Any:
    """Permanently delete a file, symlink, or directory safely."""
    target = validate_path(request.path, must_exist=True)
    _reject_symlinked_parents(Path(request.path).expanduser())
    
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
    target = validate_path(request.path)
    _reject_symlinked_parents(Path(request.path).expanduser())
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
    source = validate_path(request.from_path, must_exist=True)
    destination = validate_path(request.to_path)
    _reject_symlinked_parents(Path(request.from_path).expanduser())
    _reject_symlinked_parents(Path(request.to_path).expanduser())
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
    """Search for files and directories by name with tree-enabled results.

    Broad roots like ``/`` are clamped to configured ``allowed_base_dirs``.
    """
    roots = resolve_search_roots(path)
    matches: List[FileEntry] = []
    seen: set[str] = set()

    try:
        for target in roots:
            process = subprocess.Popen(
                ["find", str(target), "-iname", f"*{query}*", "-print"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            lines: list[str] = []
            assert process.stdout is not None
            for line in process.stdout:
                lines.append(line.rstrip("\n"))
                if len(lines) > config.max_search_results:
                    process.kill()
                    process.wait(timeout=5)
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Too many search results")
            _, stderr = process.communicate(timeout=30)
            if process.returncode != 0 and not lines:
                raise OSError(stderr.strip() if stderr else "Search failed")

            for line in lines:
                if not line:
                    continue
                found_path = Path(line)
                key = str(found_path)
                if key in seen:
                    continue
                if is_allowed(found_path):
                    seen.add(key)
                    entry_dict = file_entry(found_path)
                    matches.append(FileEntry(**entry_dict))
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Search timed out")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Search failed: {exc}")

    matches.sort(key=lambda x: (x.type != "directory", x.name.lower()))

    current = str(roots[0]) if len(roots) == 1 else ",".join(str(r) for r in roots)
    return FileListResponse(
        files=matches,
        current_path=current,
        parent_path=None,
        total_items=len(matches),
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
    output = validate_path(request.output)
    _reject_symlinked_parents(Path(request.output).expanduser())
    if output.suffix.lower() != ".zip":
        output = output.with_suffix(".zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            entry_count = 0
            expanded_bytes = 0
            for path_str in request.paths:
                source = validate_path(path_str, must_exist=True)
                _reject_symlinked_parents(Path(path_str).expanduser())
                if source.is_file():
                    entry_count += 1
                    expanded_bytes += source.stat().st_size
                    if entry_count > config.max_archive_entries or expanded_bytes > config.max_archive_expanded_bytes:
                        raise HTTPException(status_code=413, detail="Archive limits exceeded")
                    archive.write(source, arcname=source.name)
                else:
                    for root, _, files in os.walk(source):
                        for file_name in files:
                            source_path = Path(root) / file_name
                            if source_path.is_symlink():
                                continue
                            entry_count += 1
                            expanded_bytes += source_path.stat().st_size
                            if entry_count > config.max_archive_entries or expanded_bytes > config.max_archive_expanded_bytes:
                                raise HTTPException(status_code=413, detail="Archive limits exceeded")
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
    source = validate_path(request.path, must_exist=True)
    destination = validate_path(request.destination)
    _reject_symlinked_parents(Path(request.destination).expanduser())
    if source.suffix.lower() != ".zip":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source file must be a .zip archive")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            members = archive.infolist()
            if len(members) > config.max_archive_entries:
                raise HTTPException(status_code=413, detail="Archive contains too many entries")
            root = destination.resolve()
            total_size = sum(max(0, member.file_size) for member in members)
            if total_size > config.max_archive_expanded_bytes:
                raise HTTPException(status_code=413, detail="Archive expanded size exceeds the limit")
            for member in members:
                name = member.filename
                if not name or name.startswith(("/", "\\")):
                    raise HTTPException(status_code=400, detail="Archive contains an unsafe path")
                mode = (member.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise HTTPException(status_code=400, detail="Archive contains a symlink entry")
                candidate = (root / name).resolve(strict=False)
                try:
                    candidate.relative_to(root)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="Archive contains a path traversal entry") from exc
                if member.is_dir():
                    candidate.mkdir(parents=True, exist_ok=True)
                    continue
                candidate.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as src, candidate.open("xb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
    except (OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return FileActionResponse(success=True, message=f"Extracted archive to {destination}")


@router.post("/open", response_model=FileActionResponse, dependencies=[Depends(get_current_user)])
async def open_path(request: PathRequest) -> Any:
    """Open a file or directory with the default system application."""
    from app.utils.desktop_env import ensure_desktop_env
    from app.services.processes import spawn_detached

    target = validate_path(request.path, must_exist=True)
    ensure_desktop_env()
    try:
        result = spawn_detached(["xdg-open", str(target)])
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="xdg-open not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return FileActionResponse(success=True, message=f"Opened {target}. {result.message}")
