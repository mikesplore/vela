"""Process helpers for Vela."""

from __future__ import annotations

import configparser
import os
import re
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.domain.processes import InstalledApplication, InstalledApplicationList
from app.utils.desktop_env import ensure_desktop_env

DESKTOP_DIRS = (
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/var/lib/snapd/desktop/applications"),
    Path.home() / ".local/share/applications",
)

APP_ALIASES: dict[str, list[str]] = {
    "chrome": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "google chrome": ["google-chrome", "google-chrome-stable"],
    "browser": ["firefox", "google-chrome", "google-chrome-stable", "chromium"],
    "vscode": ["code", "code-oss", "codium", "vscodium"],
    "vs code": ["code", "code-oss"],
    "terminal": ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"],
}

EXEC_FIELD_CODES = re.compile(r"%[a-zA-Z]")
_CACHE_TTL_SECONDS = 300

_cache_loaded_at: float | None = None
_cache_entries: list["DesktopEntry"] | None = None


@dataclass
class LaunchResult:
    pid: int | None
    message: str
    detached: bool
    application_id: str | None = None
    application_name: str | None = None


@dataclass
class DesktopEntry:
    id: str
    name: str
    generic_name: str
    exec_line: str
    exec_argv: list[str]
    keywords: list[str]
    categories: list[str]
    path: Path


class ApplicationNotFoundError(LookupError):
    def __init__(self, query: str, suggestions: list[str]) -> None:
        self.query = query
        self.suggestions = suggestions
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        super().__init__(f"Application {query!r} not found.{hint}")


class ApplicationNotRunningError(LookupError):
    def __init__(self, query: str, application_name: str | None = None) -> None:
        self.query = query
        self.application_name = application_name
        label = application_name or query
        super().__init__(f"No running processes found for {label!r}.")


def kill_processes_by_name(name: str) -> int:
    killed_count, _ = _terminate_processes_matching([name])
    return killed_count


def is_process_running(name: str) -> tuple[bool, int, list[int]]:
    """Return whether any process matches the given app name or alias."""
    entry = _try_resolve_application(name)
    candidates = _collect_process_name_candidates(name, entry)
    pids = _find_matching_pids(candidates)
    return bool(pids), len(pids), pids


def close_installed_application(name: str) -> tuple[int, str | None, str | None]:
    """Close a GUI application using .desktop-aware process matching."""
    entry = _try_resolve_application(name)
    candidates = _collect_process_name_candidates(name, entry)
    killed_count, killed_pids = _terminate_processes_matching(candidates)
    if killed_count == 0:
        raise ApplicationNotRunningError(name, entry.name if entry else None)
    return killed_count, entry.id if entry else None, entry.name if entry else name


def _try_resolve_application(query: str) -> DesktopEntry | None:
    try:
        return resolve_application(query)
    except ApplicationNotFoundError:
        return None


def _collect_process_name_candidates(query: str, entry: DesktopEntry | None = None) -> list[str]:
    candidates: list[str] = []

    def add(value: str) -> None:
        value = value.strip()
        if not value:
            return
        options = {value, Path(value).name, Path(value).stem}
        for token in options:
            token = token.strip()
            if not token:
                continue
            if token.lower() not in {existing.lower() for existing in candidates}:
                candidates.append(token)

    add(query)
    for alias in _alias_candidates(query):
        add(alias)
    if entry:
        add(_id_stem(entry.id))
        add(entry.name)
        for argv_part in entry.exec_argv:
            add(argv_part)
        for keyword in entry.keywords:
            add(keyword)
    return candidates


def _process_matches_candidate(proc_info: dict, candidate: str) -> bool:
    candidate = candidate.lower().strip()
    if not candidate:
        return False
    proc_name = (proc_info.get("name") or "").lower()
    if proc_name == candidate:
        return True
    cmdline = proc_info.get("cmdline") or []
    for part in cmdline:
        if not part:
            continue
        part_lower = part.lower()
        base = Path(part).name.lower()
        stem = Path(part).stem.lower()
        if candidate in {base, stem}:
            return True
        if part_lower.endswith(f"/{candidate}") or part_lower.endswith(f"/{candidate}.bin"):
            return True
    return False


def _find_matching_pids(candidates: list[str]) -> list[int]:
    pids: list[int] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if any(_process_matches_candidate(proc.info, candidate) for candidate in candidates):
                pids.append(int(proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def _terminate_processes_matching(candidates: list[str]) -> tuple[int, list[int]]:
    killed_count = 0
    killed_pids: list[int] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if not any(_process_matches_candidate(proc.info, candidate) for candidate in candidates):
                continue
            proc.terminate()
            proc.wait(timeout=3)
            killed_count += 1
            killed_pids.append(proc.pid)
        except psutil.NoSuchProcess:
            continue
        except psutil.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
            killed_count += 1
            killed_pids.append(proc.pid)
        except psutil.AccessDenied:
            continue
    return killed_count, killed_pids


def list_installed_applications(filter_text: str | None = None) -> InstalledApplicationList:
    """Return installed desktop applications from Freedesktop .desktop entries."""
    entries = _load_desktop_entries()
    apps = [_to_installed_application(entry) for entry in entries]
    if filter_text:
        needle = _normalize_token(filter_text)
        apps = [
            app
            for app in apps
            if needle in _normalize_token(app.name)
            or needle in _normalize_token(app.id)
            or (app.generic_name and needle in _normalize_token(app.generic_name))
            or (app.exec_binary and needle in _normalize_token(app.exec_binary))
            or any(needle in _normalize_token(keyword) for keyword in app.keywords)
            or any(needle in _normalize_token(category) for category in app.categories)
        ]
    return InstalledApplicationList(applications=sorted(apps, key=lambda item: item.name.lower()))


def resolve_application(query: str) -> DesktopEntry:
    """Resolve a friendly name, alias, desktop id, or exec binary to a .desktop entry."""
    entries = _load_desktop_entries()
    match = _best_application_match(query, entries)
    if match:
        return match
    suggestions = [
        entry.name
        for entry, score in _rank_application_matches(query, entries)[:3]
        if score >= 40
    ]
    raise ApplicationNotFoundError(query, suggestions)


def open_installed_application(name: str, args: list[str] | None = None) -> LaunchResult:
    """Open a GUI application using .desktop resolution when possible."""
    extra_args = list(args or [])
    entry: DesktopEntry | None = None
    try:
        entry = resolve_application(name)
    except ApplicationNotFoundError:
        if shutil.which(name):
            result = spawn_detached([name, *extra_args])
            result.application_name = name
            return result
        raise

    gtk_launch = shutil.which("gtk-launch")
    if gtk_launch and not extra_args:
        result = spawn_detached([gtk_launch, entry.id])
        result.application_id = entry.id
        result.application_name = entry.name
        result.message = f"Opened {entry.name} via gtk-launch."
        return result

    if not entry.exec_argv:
        raise ApplicationNotFoundError(name, [entry.name])

    argv = list(entry.exec_argv)
    argv.extend(extra_args)
    result = spawn_detached(argv)
    result.application_id = entry.id
    result.application_name = entry.name
    result.message = f"Opened {entry.name}."
    return result


def spawn_detached(argv: list[str]) -> LaunchResult:
    """Launch a process outside the vela.service cgroup when possible.

    Children started with plain ``Popen`` stay in Vela's systemd cgroup, so
    ``systemctl --user stop/restart vela`` kills them. Prefer a transient
    user service via ``systemd-run --no-block`` so desktop apps outlive the API.
    """
    if not argv or not argv[0]:
        raise ValueError("Command is required")

    ensure_desktop_env()
    env = os.environ.copy()

    systemd_run = shutil.which("systemd-run")
    if systemd_run:
        unit = f"vela-app-{uuid.uuid4().hex[:10]}"
        # Use a transient .service (not --scope): scope mode waits until the
        # command exits, which would block the API on long-lived GUI apps.
        cmd = [
            systemd_run,
            "--user",
            "--collect",
            "--no-block",
            "--same-dir",
            f"--unit={unit}",
        ]
        for key in (
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XAUTHORITY",
            "DBUS_SESSION_BUS_ADDRESS",
            "XDG_RUNTIME_DIR",
            "XDG_SESSION_TYPE",
            "XDG_CURRENT_DESKTOP",
            "DESKTOP_SESSION",
        ):
            if env.get(key):
                cmd.append(f"--setenv={key}={env[key]}")
        cmd.extend(["--", *argv])
        completed = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, timeout=10)
        if completed.returncode == 0:
            pid = _unit_main_pid(unit)
            return LaunchResult(
                pid=pid,
                message=f"Launched detached from Vela service (unit {unit}.service).",
                detached=True,
            )
        # Fall through if systemd-run rejected the command (e.g. missing binary).
        # Keep stderr available for debugging rare failures.
        if completed.stderr:
            import logging

            logging.getLogger(__name__).debug("systemd-run failed: %s", completed.stderr.strip())

    # Fallback: new session. Survives Vela stop when KillMode=process on vela.service.
    try:
        proc = subprocess.Popen(
            argv,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except FileNotFoundError:
        raise
    return LaunchResult(
        pid=proc.pid,
        message="Process launched in a new session (detached via KillMode=process).",
        detached=False,
    )


def _unit_main_pid(unit: str) -> int | None:
    name = unit if unit.endswith((".service", ".scope")) else f"{unit}.service"
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "show", name, "-p", "MainPID", "--value"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except Exception:
        return None
    raw = (proc.stdout or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return None


def _desktop_search_dirs() -> list[Path]:
    dirs = [path for path in DESKTOP_DIRS if path.is_dir()]
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        custom = Path(data_home).expanduser() / "applications"
        if custom.is_dir() and custom not in dirs:
            dirs.append(custom)
    data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    for base in data_dirs.split(":"):
        base = base.strip()
        if not base:
            continue
        candidate = Path(base).expanduser() / "applications"
        if candidate.is_dir() and candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _load_desktop_entries(force: bool = False) -> list[DesktopEntry]:
    global _cache_loaded_at, _cache_entries
    now = time.monotonic()
    if not force and _cache_entries is not None and _cache_loaded_at is not None:
        if now - _cache_loaded_at < _CACHE_TTL_SECONDS:
            return _cache_entries

    by_id: dict[str, DesktopEntry] = {}
    for directory in _desktop_search_dirs():
        for path in sorted(directory.glob("*.desktop")):
            entry = _parse_desktop_file(path)
            if entry is None:
                continue
            existing = by_id.get(entry.id)
            if existing is None or directory == Path.home() / ".local/share/applications":
                by_id[entry.id] = entry

    _cache_entries = sorted(by_id.values(), key=lambda item: item.name.lower())
    _cache_loaded_at = now
    return _cache_entries


def _parse_desktop_file(path: Path) -> DesktopEntry | None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    if not parser.has_section("Desktop Entry"):
        return None

    section = parser["Desktop Entry"]
    entry_type = section.get("Type", "Application").strip() or "Application"
    if entry_type != "Application":
        return None
    if section.get("NoDisplay", "").strip().lower() == "true":
        return None
    if section.get("Hidden", "").strip().lower() == "true":
        return None

    name = section.get("Name", "").strip()
    exec_line = section.get("Exec", "").strip()
    if not name or not exec_line:
        return None

    exec_argv = _parse_exec_line(exec_line)
    if not exec_argv:
        return None

    return DesktopEntry(
        id=path.name,
        name=name,
        generic_name=section.get("GenericName", "").strip(),
        exec_line=exec_line,
        exec_argv=exec_argv,
        keywords=_split_desktop_list(section.get("Keywords", "")),
        categories=_split_desktop_list(section.get("Categories", "")),
        path=path,
    )


def _parse_exec_line(exec_line: str) -> list[str]:
    cleaned = EXEC_FIELD_CODES.sub("", exec_line).strip()
    if not cleaned:
        return []
    try:
        return shlex.split(cleaned)
    except ValueError:
        return cleaned.split()


def _split_desktop_list(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;]", raw) if part.strip()]


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _id_stem(desktop_id: str) -> str:
    return desktop_id[:-8] if desktop_id.endswith(".desktop") else desktop_id


def _to_installed_application(entry: DesktopEntry) -> InstalledApplication:
    return InstalledApplication(
        id=entry.id,
        name=entry.name,
        generic_name=entry.generic_name or None,
        exec_command=entry.exec_line,
        exec_binary=entry.exec_argv[0] if entry.exec_argv else None,
        keywords=entry.keywords,
        categories=entry.categories,
    )


def _alias_candidates(query: str) -> list[str]:
    normalized = _normalize_token(query)
    candidates = [normalized, query.strip().lower()]
    alias_targets = APP_ALIASES.get(normalized) or APP_ALIASES.get(query.strip().lower()) or []
    candidates.extend(alias_targets)
    deduped: list[str] = []
    for candidate in candidates:
        token = candidate.strip().lower()
        if token and token not in deduped:
            deduped.append(token)
    return deduped


def _score_application_match(query: str, entry: DesktopEntry) -> int:
    best = 0
    entry_id = _id_stem(entry.id).lower()
    entry_name = _normalize_token(entry.name)
    exec_binary = Path(entry.exec_argv[0]).name.lower() if entry.exec_argv else ""
    generic_name = _normalize_token(entry.generic_name)
    keyword_tokens = [_normalize_token(keyword) for keyword in entry.keywords]

    for candidate in _alias_candidates(query):
        token = _normalize_token(candidate)
        raw = candidate.strip().lower()
        if not token and not raw:
            continue
        if raw == entry.id.lower() or token == entry_id or raw == entry_id:
            best = max(best, 100)
        if token == entry_name or raw == entry.name.lower():
            best = max(best, 95)
        if exec_binary and (token == exec_binary or raw == exec_binary):
            best = max(best, 90)
        if generic_name and (token == generic_name or token in generic_name):
            best = max(best, 80)
        if any(token == keyword or token in keyword for keyword in keyword_tokens):
            best = max(best, 75)
        if token and token in entry_name:
            best = max(best, 65)
        if token and token in entry_id:
            best = max(best, 60)
        if exec_binary and token in exec_binary:
            best = max(best, 55)
    return best


def _rank_application_matches(query: str, entries: list[DesktopEntry]) -> list[tuple[DesktopEntry, int]]:
    ranked = [(entry, _score_application_match(query, entry)) for entry in entries]
    ranked = [(entry, score) for entry, score in ranked if score > 0]
    ranked.sort(key=lambda item: (-item[1], item[0].name.lower()))
    return ranked


def _best_application_match(query: str, entries: list[DesktopEntry]) -> DesktopEntry | None:
    ranked = _rank_application_matches(query, entries)
    if not ranked or ranked[0][1] < 50:
        return None
    top_score = ranked[0][1]
    top_entries = [entry for entry, score in ranked if score == top_score]
    if len(top_entries) == 1:
        return top_entries[0]

    normalized = _normalize_token(query)
    alias_targets = APP_ALIASES.get(normalized) or APP_ALIASES.get(query.strip().lower()) or []
    for target in alias_targets:
        target_lower = target.lower()
        for entry in top_entries:
            entry_id = _id_stem(entry.id).lower()
            exec_name = Path(entry.exec_argv[0]).name.lower() if entry.exec_argv else ""
            if target_lower in {entry_id, exec_name}:
                return entry
    return top_entries[0]
