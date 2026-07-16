"""Backward-compatible entrypoint. Implementation lives in app.setup. """

from app.setup.flow import run_setup

__all__ = ["run_setup"]
