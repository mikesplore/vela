from pathlib import Path
from typing import Any
from fastapi import HTTPException, status

from app.utils.config import get_config

config = get_config()


def resolve_path(path_str: str) -> Path:
    # Expand user (~) first, then treat relative paths as relative to cwd
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def allowed_base_paths() -> list[Path]:
    return [Path(p).expanduser().resolve() for p in config.allowed_base_dirs]


def is_allowed(path: Path) -> bool:
    allowed_dirs = allowed_base_paths()
    if not allowed_dirs:
        return True
    return any(path == base or path.is_relative_to(base) for base in allowed_dirs)


def validate_path(path_str: str, must_exist: bool = False) -> Path:
    if not path_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path is required")
    path = resolve_path(path_str)
    if not is_allowed(path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path is outside allowed base directories")
    if must_exist and not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found")
    return path


def resolve_search_roots(path_str: str | None) -> list[Path]:
    """Map broad/root search paths onto allowed base directories.

    - empty / ``.`` / ``/`` → all allowed bases (or cwd if none configured)
    - path inside an allowed base → that path
    - path that is an ancestor of allowed bases (e.g. ``/`` or ``/home``) → those bases
    - otherwise → 403
    """
    allowed = allowed_base_paths()
    raw = (path_str or "").strip()

    if not raw or raw in {".", "/"}:
        if allowed:
            return [p for p in allowed if p.is_dir()]
        cwd = Path.cwd().resolve()
        if not cwd.is_dir():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Search path must be a directory")
        return [cwd]

    path = resolve_path(raw)

    if is_allowed(path):
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found")
        if not path.is_dir():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must be a directory")
        return [path]

    # Ancestor of one or more allowed bases: clamp search to those bases.
    descendants = [base for base in allowed if base == path or base.is_relative_to(path)]
    if descendants:
        existing = [p for p in descendants if p.is_dir()]
        if existing:
            return existing

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path is outside allowed base directories")


def file_entry(path: Path, include_tree_meta: bool = True) -> dict[str, Any]:
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
