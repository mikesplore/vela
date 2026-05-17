import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, List

import psutil
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import Config
from dependencies import get_current_user

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


def _file_entry(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "type": "directory" if path.is_dir() else "file",
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


class FileEntry(BaseModel):
    name: str
    path: str
    type: str
    size: int
    modified: float


class FileListResponse(BaseModel):
    files: List[FileEntry]


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
async def list_files(path: str = Query(".")) -> Any:
    """List directory contents for a given path."""
    target = _validate_path(path, must_exist=True)
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a directory")
    files = [_file_entry(child) for child in sorted(target.iterdir(), key=lambda p: p.name)]
    return FileListResponse(files=[FileEntry(**entry) for entry in files])


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
    """Delete a file or directory."""
    target = _validate_path(request.path, must_exist=True)
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return FileActionResponse(success=True, message=f"Deleted {target}")


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


@router.get("/search", response_model=FileListResponse, dependencies=[Depends(get_current_user)])
async def search_files(query: str = Query(...), path: str = Query(".")) -> Any:
    """Search for files and directories by name."""
    target = _validate_path(path, must_exist=True)
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a directory")
    matches: List[dict[str, Any]] = []
    for root, dirs, files in os.walk(target):
        for name in dirs + files:
            if query.lower() in name.lower():
                matches.append(_file_entry(Path(root) / name))
    return FileListResponse(files=[FileEntry(**entry) for entry in matches])


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
