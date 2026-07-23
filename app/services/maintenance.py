import json
import re
import shutil
from typing import List, Optional, Tuple

from app.domain.maintenance import (
    ActionResponse,
    BootErrorsResponse,
    PackageInstalledResponse,
    ServiceEntry,
    ServiceStatusResponse,
    TimerEntry,
)
from app.utils.run_command import run_command


def detect_package_manager() -> Optional[str]:
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("pacman"):
        return "pacman"
    return None


def _systemctl_base(scope: str) -> List[str]:
    if scope == "user":
        return ["systemctl", "--user"]
    return ["systemctl"]


def _normalize_service_name(name: str) -> str:
    name = name.strip()
    if not name.endswith(".service"):
        return f"{name}.service"
    return name


def _parse_systemctl_show(stdout: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        props[key.strip()] = value.strip()
    return props


def _service_is_running(active: str, sub: str) -> bool:
    if active == "active":
        return sub in {"running", "exited", "listening"}
    return False


def _list_systemd_services_for_scope(scope: str) -> Tuple[List[ServiceEntry], Optional[str]]:
    cmd = _systemctl_base(scope) + [
        "list-units",
        "--type=service",
        "--all",
        "--output=json",
        "--no-pager",
    ]
    stdout, stderr, rc = run_command(cmd)
    if rc == 0 and stdout.strip():
        try:
            services = _parse_services_json(stdout)
            for service in services:
                service.scope = scope
            return services, None
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            pass

    cmd = _systemctl_base(scope) + [
        "list-units",
        "--type=service",
        "--all",
        "--no-legend",
        "--no-pager",
        "--plain",
    ]
    stdout, stderr, rc = run_command(cmd)
    if rc != 0:
        return [], stderr or "Could not list services"
    services = _parse_services_table(stdout)
    for service in services:
        service.scope = scope
    return services, None


def list_systemd_services(
    filter_text: Optional[str] = None,
    scope: str = "system",
) -> Tuple[List[ServiceEntry], Optional[str]]:
    """Return systemd services for the given scope, optionally filtered by name/description."""
    scopes = ["system", "user"] if scope == "all" else [scope if scope in {"system", "user"} else "system"]
    all_services: List[ServiceEntry] = []
    errors: List[str] = []
    for item_scope in scopes:
        services, error = _list_systemd_services_for_scope(item_scope)
        if error:
            errors.append(error)
        else:
            all_services.extend(services)
    if not all_services and errors:
        return [], "; ".join(errors)

    if filter_text:
        needle = filter_text.lower()
        all_services = [
            service
            for service in all_services
            if needle in service.name.lower() or needle in service.description.lower()
        ]
    return all_services, None


def get_service_status(name: str, scope: str = "system") -> Tuple[Optional[ServiceStatusResponse], Optional[str]]:
    """Return status for one systemd unit, searching user scope when scope=all."""
    normalized = _normalize_service_name(name)
    scopes = ["system", "user"] if scope == "all" else [scope if scope in {"system", "user"} else "system"]
    for item_scope in scopes:
        cmd = _systemctl_base(item_scope) + [
            "show",
            normalized,
            "--property=LoadState,ActiveState,SubState,Description,UnitFileState",
            "--no-pager",
        ]
        stdout, stderr, rc = run_command(cmd)
        if rc != 0:
            continue
        props = _parse_systemctl_show(stdout)
        if props.get("LoadState") == "not-found":
            continue
        active = props.get("ActiveState", "")
        sub = props.get("SubState", "")
        return (
            ServiceStatusResponse(
                name=normalized,
                scope=item_scope,
                load=props.get("LoadState", ""),
                active=active,
                sub=sub,
                description=props.get("Description", ""),
                enabled=props.get("UnitFileState") or None,
                running=_service_is_running(active, sub),
            ),
            None,
        )
    return None, f"Service {normalized} not found"


def resolve_service_scope(name: str, scope: str = "all") -> Tuple[Optional[str], Optional[str]]:
    """Find which systemd scope owns a unit."""
    if scope in {"system", "user"}:
        return scope, None
    status, _ = get_service_status(name, "system")
    if status:
        return "system", None
    status, _ = get_service_status(name, "user")
    if status:
        return "user", None
    return None, f"Service {_normalize_service_name(name)} not found"


def list_failed_services(scope: str = "system") -> Tuple[List[ServiceEntry], Optional[str]]:
    scopes = ["system", "user"] if scope == "all" else [scope if scope in {"system", "user"} else "system"]
    failed: List[ServiceEntry] = []
    errors: List[str] = []
    for item_scope in scopes:
        cmd = _systemctl_base(item_scope) + ["--failed", "--no-legend", "--no-pager", "--plain"]
        stdout, stderr, rc = run_command(cmd)
        if rc != 0:
            errors.append(stderr or "Could not list failed services")
            continue
        for service in _parse_services_table(stdout):
            service.scope = item_scope
            failed.append(service)
    if not failed and errors:
        return [], "; ".join(errors)
    return failed, None


def list_systemd_timers(
    filter_text: Optional[str] = None,
    scope: str = "system",
) -> Tuple[List[TimerEntry], Optional[str]]:
    scopes = ["system", "user"] if scope == "all" else [scope if scope in {"system", "user"} else "system"]
    timers: List[TimerEntry] = []
    errors: List[str] = []
    for item_scope in scopes:
        cmd = _systemctl_base(item_scope) + [
            "list-timers",
            "--all",
            "--no-legend",
            "--no-pager",
            "--plain",
        ]
        stdout, stderr, rc = run_command(cmd)
        if rc != 0:
            errors.append(stderr or "Could not list timers")
            continue
        timers.extend(_parse_timers_table(stdout, item_scope))
    if not timers and errors:
        return [], "; ".join(errors)
    if filter_text:
        needle = filter_text.lower()
        timers = [
            timer
            for timer in timers
            if needle in timer.name.lower() or needle in timer.description.lower()
        ]
    return timers, None


def is_package_installed(name: str) -> PackageInstalledResponse:
    manager = detect_package_manager()
    package = name.strip()
    if manager == "apt":
        stdout, _, rc = run_command(["dpkg", "-s", package])
        installed = rc == 0
        version = None
        if installed:
            for line in stdout.splitlines():
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                    break
        return PackageInstalledResponse(name=package, installed=installed, manager=manager, version=version)
    if manager == "dnf":
        stdout, _, rc = run_command(["rpm", "-q", package])
        installed = rc == 0
        version = stdout.strip() if installed else None
        return PackageInstalledResponse(name=package, installed=installed, manager=manager, version=version)
    if manager == "pacman":
        stdout, _, rc = run_command(["pacman", "-Q", package])
        installed = rc == 0
        version = stdout.strip().split()[1] if installed and stdout.split() else None
        return PackageInstalledResponse(name=package, installed=installed, manager=manager, version=version)
    return PackageInstalledResponse(name=package, installed=False, manager=None)


def get_boot_errors(lines: int = 50) -> BootErrorsResponse:
    stdout, _, rc = run_command(
        ["journalctl", "-p", "err", "-b", "-n", str(lines), "--no-pager"],
        timeout=20,
    )
    if rc != 0 or not stdout.strip():
        return BootErrorsResponse(lines=[])
    return BootErrorsResponse(lines=stdout.splitlines())


def service_action(name: str, action: str, scope: str = "system") -> Tuple[ActionResponse, Optional[str]]:
    normalized = _normalize_service_name(name)
    resolved_scope, error = resolve_service_scope(normalized, scope)
    if error or not resolved_scope:
        return ActionResponse(success=False, message=error or "Service not found"), error

    if action == "start":
        status, _ = get_service_status(normalized, resolved_scope)
        if status and status.running:
            return ActionResponse(success=True, message=f"Service {normalized} is already running."), None
    if action == "stop":
        status, _ = get_service_status(normalized, resolved_scope)
        if status and status.active == "inactive":
            return ActionResponse(success=True, message=f"Service {normalized} is already stopped."), None

    stdout, stderr, rc = run_command(_systemctl_base(resolved_scope) + [action, normalized])
    if rc != 0:
        detail = stderr or stdout or f"Could not {action} service"
        return ActionResponse(success=False, message=detail), detail
    return ActionResponse(success=True, message=f"Service {normalized} {action}ed."), None


def _parse_services_json(stdout: str) -> List[ServiceEntry]:
    raw = json.loads(stdout)
    if not isinstance(raw, list):
        raise ValueError("expected a JSON array")
    services: List[ServiceEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        unit_name = str(item.get("unit") or item.get("name") or "").strip()
        if not unit_name:
            continue
        services.append(
            ServiceEntry(
                name=unit_name,
                load=str(item.get("load") or ""),
                active=str(item.get("active") or ""),
                sub=str(item.get("sub") or ""),
                description=str(item.get("description") or ""),
            )
        )
    return services


def _parse_services_table(stdout: str) -> List[ServiceEntry]:
    services: List[ServiceEntry] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[●○↻×]+\s*", "", line)
        parts = re.split(r"\s+", line, maxsplit=4)
        if len(parts) < 4:
            continue
        unit_name, load, active, sub = parts[0], parts[1], parts[2], parts[3]
        if not unit_name:
            continue
        description = parts[4] if len(parts) > 4 else ""
        services.append(
            ServiceEntry(name=unit_name, load=load, active=active, sub=sub, description=description)
        )
    return services


def _parse_timers_table(stdout: str, scope: str) -> List[TimerEntry]:
    timers: List[TimerEntry] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[●○↻×]+\s*", "", line)
        parts = re.split(r"\s+", line, maxsplit=7)
        if len(parts) < 7:
            continue
        timers.append(
            TimerEntry(
                next=parts[0],
                left=parts[1],
                last=parts[2],
                passed=parts[3],
                active=parts[4],
                unit=parts[5],
                name=parts[6],
                description=parts[7] if len(parts) > 7 else "",
                scope=scope,
            )
        )
    return timers
