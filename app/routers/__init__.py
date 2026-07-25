"""HTTP routers — use registry.load_routers() for capability-gated imports."""

from app.routers.registry import load_routers

__all__ = ["load_routers"]
