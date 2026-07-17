import subprocess
from typing import List

from app.utils.desktop_env import ensure_desktop_env


def run_command(cmd: List[str], timeout: int = 10) -> tuple[str, str, int]:
    ensure_desktop_env()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1
