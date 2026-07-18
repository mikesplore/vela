import json
import re
import shutil
from typing import List, Optional, Tuple

from app.domain.maintenance import ServiceEntry
from app.utils.run_command import run_command


def detect_package_manager() -> Optional[str]:
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("pacman"):
        return "pacman"
    return None


def list_systemd_services() -> Tuple[List[ServiceEntry], Optional[str]]:
    """Return systemd services, preferring JSON output for stable field mapping.

    Returns (services, error). error is set when the listing command fails.
    """
    stdout, stderr, rc = run_command(
        ["systemctl", "list-units", "--type=service", "--all", "--output=json", "--no-pager"]
    )
    if rc == 0 and stdout.strip():
        try:
            return _parse_services_json(stdout), None
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            pass

    stdout, stderr, rc = run_command(
        ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager", "--plain"]
    )
    if rc != 0:
        return [], stderr or "Could not list services"
    return _parse_services_table(stdout), None


def _parse_services_json(stdout: str) -> List[ServiceEntry]:
    raw = json.loads(stdout)
    if not isinstance(raw, list):
        raise ValueError("expected a JSON array")
    services: List[ServiceEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("unit") or item.get("name") or "").strip()
        if not name:
            continue
        services.append(
            ServiceEntry(
                name=name,
                load=str(item.get("load") or ""),
                active=str(item.get("active") or ""),
                sub=str(item.get("sub") or ""),
                description=str(item.get("description") or ""),
            )
        )
    return services


def _parse_services_table(stdout: str) -> List[ServiceEntry]:
    """Parse plain/no-legend systemctl table rows.

    Default (non-plain) output may start with spaces or a status glyph (●), which
    shifts whitespace-split columns. Strip those before mapping fields.
    """
    services: List[ServiceEntry] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[●○↻×]+\s*", "", line)
        parts = re.split(r"\s+", line, maxsplit=4)
        if len(parts) < 4:
            continue
        name, load, active, sub = parts[0], parts[1], parts[2], parts[3]
        if not name:
            continue
        description = parts[4] if len(parts) > 4 else ""
        services.append(
            ServiceEntry(name=name, load=load, active=active, sub=sub, description=description)
        )
    return services
