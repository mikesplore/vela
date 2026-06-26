from typing import List

from pydantic import BaseModel, Field


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
