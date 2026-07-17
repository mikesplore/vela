"""Fresh-start setup orchestration.

Setup always:
1. Wipes cached local auth tokens and relay credentials
2. Collects config (browser wizard or terminal)
3. Writes config.yaml + fresh .env (empty relay secrets)
4. Installs/enables services
5. Forces pairing (never reuses old relay secrets)
6. Restarts services so they load only the new credentials
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.setup.cli_links import install_user_cli_links
from app.setup.credentials import wipe_setup_credentials
from app.setup.deps import (
    check_and_offer_dependency_install,
    dependency_install_plan,
    install_packages,
)
from app.setup.services import enable_services, restart_all_services, write_systemd_units
from app.setup.wizard import browser_is_available, browser_onboarding_enabled, start_setup_wizard
from app.setup.writers import (
    OPTIONAL_ENV_FIELDS,
    empty_optional_integrations,
    write_config_yaml,
    write_env_file,
)


def _prompt(default: str | None, label: str, required: bool = True) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip()
        if not value and default is not None:
            value = default
        if value or not required:
            return value
        print(f"{label} is required.")


def _prompt_secret(label: str) -> str:
    import getpass

    while True:
        first = getpass.getpass(f"{label}: ").strip()
        if not first:
            print(f"{label} is required.")
            continue
        second = getpass.getpass("Confirm password: ").strip()
        if first == second:
            return first
        print("Passwords do not match.")


def _normalize_vps_url(raw: str) -> str:
    parsed = urlparse(raw.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("VPS URL must include http:// or https:// and a host")
    return raw.rstrip("/")


def _verify_vps_health(vps_url: str) -> None:
    health_url = f"{vps_url.rstrip('/')}/health"
    print(f"Checking VPS at {health_url} ...")
    resp = requests.get(health_url, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"VPS health check failed: HTTP {resp.status_code} {resp.text}")
    payload = resp.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"VPS health payload unexpected: {payload}")


def _collect_values(defaults: dict[str, str], wizard) -> dict[str, str | int]:
    browser_values = None
    if wizard:
        timeout_seconds = int(os.getenv("VELA_BROWSER_ONBOARDING_TIMEOUT", "300"))
        print(f"Waiting for browser onboarding submission (timeout: {timeout_seconds}s)...")
        if wizard["wait_for_submit"](timeout_seconds):
            browser_values = wizard["get_submitted"]()
            print("Browser onboarding submitted. Continuing setup.")
            wizard["set_phase"]("configuring", "Applying setup configuration...")
        else:
            print("Browser onboarding timed out; falling back to terminal prompts.")
            wizard["close"]()
            wizard = None

    optional = empty_optional_integrations()

    if browser_values:
        username = browser_values["username"] or defaults["username"]
        password = (browser_values["password"] or "").strip()
        if not password:
            password = _prompt_secret("Password")
        raw_vps = browser_values["vps_url"] or defaults["vps_url"]
        agent_label = browser_values["agent_label"] or defaults["agent_label"]
        host = browser_values["host"] or defaults["host"]
        port = int(browser_values["port"] or defaults["port"])
        allowed_dirs_csv = browser_values["allowed_dirs_csv"] or defaults["allowed_dirs_csv"]
        assistant_pin = browser_values["assistant_pin"] or ""
        for key in optional:
            optional[key] = (browser_values.get(key) or "").strip()
    else:
        username = _prompt(defaults["username"], "Username")
        password = _prompt_secret("Password")
        raw_vps = _prompt(defaults["vps_url"], "VPS URL")
        agent_label = _prompt(defaults["agent_label"], "Agent label (shown in app)")
        host = _prompt(defaults["host"], "Bind host")
        port = int(_prompt(defaults["port"], "Port"))
        allowed_dirs_csv = _prompt(defaults["allowed_dirs_csv"], "Allowed base dirs (comma-separated)")
        assistant_pin = _prompt("", "Assistant action PIN (optional)", required=False)
        print("")
        print("Optional integrations (leave blank to skip):")
        for key, _, label in OPTIONAL_ENV_FIELDS:
            optional[key] = _prompt(defaults.get(key, ""), f"{label} (optional)", required=False)

    if raw_vps and not raw_vps.startswith(("http://", "https://")):
        raw_vps = f"https://{raw_vps}"
    vps_url = _normalize_vps_url(raw_vps)

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Bind host must be localhost-only for safety")

    allowed_dirs = [str(Path(p.strip()).expanduser()) for p in allowed_dirs_csv.split(",") if p.strip()]
    for path in allowed_dirs:
        if not Path(path).is_absolute():
            raise RuntimeError(f"Allowed directory must be absolute: {path}")

    return {
        "username": username,
        "password": password,
        "vps_url": vps_url,
        "agent_label": agent_label,
        "host": host,
        "port": port,
        "allowed_dirs": allowed_dirs,
        "assistant_pin": assistant_pin,
        "optional": optional,
        "wizard": wizard,
    }


def run_setup() -> None:
    target_dir = Path.cwd()
    dotenv_path = target_dir / ".env"
    print("Vela setup (fresh start)")
    print(f"Target directory: {target_dir}")
    print("This clears cached local auth tokens and relay credentials, then re-pairs.")

    wipe_setup_credentials(dotenv_path)

    defaults = {
        "username": os.getenv("USERNAME") or os.getenv("USER") or "admin",
        "password": "",
        "vps_url": os.getenv("VPS_URL") or "https://vela.mikesplore.tech",
        "agent_label": os.getenv("AGENT_NAME") or os.uname().nodename,
        "host": "127.0.0.1",
        "port": "8765",
        "allowed_dirs_csv": str(Path.home()),
        "assistant_pin": "",
        **empty_optional_integrations(),
    }

    browser_available = browser_is_available()
    wizard = None
    if browser_onboarding_enabled() and browser_available:
        wizard = start_setup_wizard(defaults)

    values = _collect_values(defaults, wizard)
    wizard = values["wizard"]
    username = str(values["username"])
    password = str(values["password"])
    vps_url = str(values["vps_url"])
    agent_label = str(values["agent_label"])
    host = str(values["host"])
    port = int(values["port"])
    allowed_dirs = list(values["allowed_dirs"])
    assistant_pin = str(values["assistant_pin"])
    optional = dict(values["optional"])  # type: ignore[arg-type]

    if wizard:
        wizard["set_phase"]("dependencies", "Checking dependencies...")
        missing, pkg_manager, packages = dependency_install_plan()
        if missing:
            decision_timeout = int(os.getenv("VELA_BROWSER_DEPENDENCY_TIMEOUT", "300"))
            decision = wizard["wait_for_dependency_decision"](
                missing,
                pkg_manager,
                packages,
                decision_timeout,
            )
            if decision == "install":
                if pkg_manager == "unknown" or not packages:
                    wizard["set_error"](
                        "No supported package manager or package suggestions are available for these tools."
                    )
                else:
                    wizard["set_phase"](
                        "dependencies",
                        "Installing selected packages. Check the terminal if a system password is requested...",
                    )
                    try:
                        install_packages(pkg_manager, packages)
                    except Exception as exc:
                        wizard["set_error"](f"Could not install selected packages: {exc}")
                        raise
            else:
                wizard["set_phase"]("dependencies", "Optional package installation skipped.")
        else:
            wizard["set_phase"]("dependencies", "All checked runtime tools are available.")
    else:
        check_and_offer_dependency_install(_prompt)

    if wizard:
        wizard["set_phase"]("relay-check", "Checking VPS relay health...")
    _verify_vps_health(vps_url)

    if wizard:
        wizard["set_phase"]("writing-config", "Writing config and environment files...")
    config_path = write_config_yaml(target_dir, username, password, host, port, allowed_dirs, assistant_pin)
    env_path = write_env_file(
        target_dir,
        username,
        password,
        vps_url,
        agent_label,
        port,
        assistant_pin,
        optional=optional,
    )
    vela_service, agent_service = write_systemd_units(target_dir)
    install_user_cli_links(target_dir)

    # Stop agent so it cannot keep using any previous in-memory/env credentials
    # while we write new ones and force pairing.
    try:
        import subprocess

        subprocess.run(
            ["systemctl", "--user", "stop", "vela-agent.service"],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass

    if wizard:
        wizard["set_phase"]("services", "Installing and starting local API service...")
    try:
        enable_services()
    except Exception as exc:
        print(f"systemd setup warning: {exc}")

    os.environ["PAIRING_BROWSER_UI"] = "false" if wizard else ("true" if browser_available else "false")
    if not browser_available and not wizard:
        print("Browser not detected; pairing will continue in terminal mode.")

    pairing_ok = False
    try:
        # Import lazily, then force-reload so we never keep pre-setup credentials.
        from app.agent.helpers import ensure_agent_registration, reload_agent_env

        reload_agent_env(env_path)
        if wizard:
            wizard["set_phase"]("pairing", "Starting pairing flow...")
            ensure_agent_registration(
                force=True,
                pairing_session_callback=wizard["set_pairing_session"],
                pairing_status_callback=wizard["set_pairing_status"],
                browser_ui=False,
            )
        else:
            ensure_agent_registration(force=True)
        pairing_ok = True
    except Exception as exc:
        print(f"pairing did not complete during setup: {exc}")
        print("Re-run setup to start fresh again: vela --setup")
        if wizard:
            wizard["set_error"](str(exc))

    try:
        restart_all_services()
        print("Services restarted with the new credentials.")
    except Exception as exc:
        print(f"could not restart services: {exc}")
        if wizard:
            wizard["set_error"](f"Could not restart services: {exc}")

    print("")
    print("Setup complete" if pairing_ok else "Setup finished with pairing incomplete")
    print(f"config: {config_path}")
    print(f"env:    {env_path}")
    print(f"vela service: {vela_service}")
    print(f"agent service: {agent_service}")
    print(f"operations dashboard: http://127.0.0.1:{port}/admin/dashboard")
    print("  Reopen it any time with: vela --dashboard")
    print("  Sign in with your Vela username/password to view request audit and latency.")
    if wizard:
        done_message = (
            f"Setup complete. Agent and API services restarted. "
            f"Operations dashboard: http://127.0.0.1:{port}/admin/dashboard "
            f"(or run: vela --dashboard)"
            if pairing_ok
            else "Setup wrote config but pairing did not finish. Re-run vela --setup."
        )
        wizard["set_done"](done_message)
        time.sleep(2)
