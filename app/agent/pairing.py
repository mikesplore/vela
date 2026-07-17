"""VPS pairing / registration flow."""

from __future__ import annotations

import getpass
import json
import os
import platform
import socket
import time

import requests

from app.agent.credentials import _persist_agent_credential, reset_agent_credential
from app.agent.envutil import _normalise_vps_url, _require_env
from app.ui.pairing_browser import start_pairing_browser_ui
from app.utils.config import get_config

PAIRING_STATUS_POLL_INTERVAL = 3
PAIRING_STATUS_TIMEOUT = 600


class PairingExpiredError(RuntimeError):
    pass


class PairingRevokedError(RuntimeError):
    pass


class ActivationTokenInvalidError(RuntimeError):
    pass


def _build_device_info() -> dict:
    fingerprint = os.getenv("DEVICE_FINGERPRINT", "").strip()
    if not fingerprint:
        host = socket.gethostname() or "unknown-host"
        user = getpass.getuser() or "unknown-user"
        fingerprint = f"{host}:{user}"

    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "device_fingerprint": fingerprint,
    }


def _build_pairing_qr_payload(vps_url: str, pairing_code: str, pairing_pin: str | None) -> str:
    payload = {
        "vps_url": vps_url,
        "pairing_code": pairing_code,
    }
    if pairing_pin:
        payload["pairing_pin"] = pairing_pin
    return json.dumps(payload, separators=(",", ":"))


def _register_start(existing_agent_id: str | None = None) -> tuple[str, str, str | None, int, str | None]:
    config = get_config()
    vps_url = _normalise_vps_url(_require_env("VPS_URL"))
    url = f"{vps_url.rstrip('/')}/agents/register/start"

    configured_agent_id = (config.agent_id or "").strip()
    default_agent_name = configured_agent_id if configured_agent_id and not configured_agent_id.startswith("agt_") else socket.gethostname()
    payload = {
        "agent_name": os.getenv("AGENT_NAME", "").strip() or default_agent_name,
        "device_info": _build_device_info(),
    }
    tenant_hint = os.getenv("TENANT_HINT", "").strip()
    if tenant_hint:
        payload["tenant_hint"] = tenant_hint
    repair_agent_id = existing_agent_id or os.getenv("PAIRING_AGENT_ID", "").strip()
    if repair_agent_id:
        payload["agent_id"] = repair_agent_id
    elif configured_agent_id.startswith("agt_"):
        # If .env already stores a VPS-issued id, treat this as a repair flow.
        payload["agent_id"] = configured_agent_id

    resp = requests.post(url, json=payload, timeout=config.local_service_timeout)
    print(f"VPS register/start status: {resp.status_code}")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"register/start failed: {resp.status_code} {resp.text}")

    data = resp.json()
    agent_id = data.get("agent_id")
    pairing_code = data.get("pairing_code")
    pairing_pin = data.get("pairing_pin")
    pairing_expires_in = int(data.get("pairing_expires_in", 0))

    if not agent_id or not pairing_code:
        raise RuntimeError("register/start response missing agent_id or pairing_code")
    if pairing_expires_in <= 0:
        raise RuntimeError("register/start returned invalid pairing_expires_in")

    qr_payload = _build_pairing_qr_payload(vps_url, pairing_code, pairing_pin)
    print(f"Pairing QR payload: {qr_payload}")

    return agent_id, pairing_code, pairing_pin, pairing_expires_in, qr_payload


def _fetch_pairing_status(agent_id: str) -> tuple[str | None, str | None]:
    config = get_config()
    vps_url = _normalise_vps_url(_require_env("VPS_URL"))
    status_url = f"{vps_url.rstrip('/')}/agents/register/status"
    resp = requests.get(
        status_url,
        params={"agent_id": agent_id},
        timeout=config.local_service_timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"register/status failed: {resp.status_code} {resp.text}")
    data = resp.json()
    return data.get("status"), data.get("activation_token")


def _wait_for_pairing(agent_id: str, on_status_update=None) -> str:

    timeout_seconds = int(os.getenv("PAIRING_STATUS_TIMEOUT", str(PAIRING_STATUS_TIMEOUT)))
    poll_interval = int(os.getenv("PAIRING_STATUS_POLL_INTERVAL", str(PAIRING_STATUS_POLL_INTERVAL)))
    started_at = time.time()
    last_status = None

    while time.time() - started_at < timeout_seconds:
        status, activation_token = _fetch_pairing_status(agent_id)
        if status != last_status:
            print(f"Pairing status for '{agent_id}': {status}")
            if on_status_update:
                on_status_update(status)
            last_status = status

        if status == "PAIRED":
            if not activation_token:
                raise RuntimeError("PAIRED status missing activation_token")
            return activation_token

        if status == "EXPIRED":
            raise PairingExpiredError("Pairing code expired; requesting a fresh session")

        if status == "REVOKED":
            raise PairingRevokedError("Pairing has been revoked; manual re-pair is required")

        time.sleep(max(1, poll_interval))

    raise TimeoutError(f"Timed out waiting for pairing after {timeout_seconds}s")


def _activate_registration(agent_id: str, activation_token: str) -> tuple[str, str | None]:
    config = get_config()
    vps_url = _normalise_vps_url(_require_env("VPS_URL"))
    activate_url = f"{vps_url.rstrip('/')}/agents/register/activate"
    payload = {
        "agent_id": agent_id,
        "activation_token": activation_token,
    }
    resp = requests.post(activate_url, json=payload, timeout=config.local_service_timeout)
    print(f"VPS register/activate status: {resp.status_code}")
    try:
        error_data = resp.json() if resp.status_code != 200 else {}
    except Exception:
        error_data = {}
    if resp.status_code != 200:
        if resp.status_code == 400 and error_data.get("message") == "invalid_activation_token":
            raise ActivationTokenInvalidError("register/activate failed: invalid_activation_token")
        if resp.status_code == 409 and error_data.get("message") == "secret_already_delivered":
            raise RuntimeError("register/activate failed: secret_already_delivered")
        raise RuntimeError(f"register/activate failed: {resp.status_code} {resp.text}")

    data = resp.json()
    credential = data.get("credential")
    if not credential:
        raise RuntimeError("register/activate response missing credential")
    return credential, data.get("relay_secret")


def _pairing_browser_enabled() -> bool:
    raw = os.getenv("PAIRING_BROWSER_UI", "true").strip().lower()
    return raw not in {"0", "false", "no"}


def _existing_registration_is_valid() -> bool:
    """Check whether current stored relay credentials can still mint ws tokens."""
    config = get_config()
    secret = (config.relay_secret or "").strip()
    agent_id = (config.agent_id or "").strip()
    if not secret or not agent_id.startswith("agt_"):
        return False
    try:
        refresh_ws_token()
        return True
    except Exception as exc:
        print(f"Stored relay credential validation failed: {exc}")
        return False


def ensure_agent_registration(
    force: bool = False,
    pairing_session_callback=None,
    pairing_status_callback=None,
    browser_ui: bool | None = None,
) -> None:
    config = get_config()
    if config.relay_secret and not force:
        if _existing_registration_is_valid():
            print("Stored relay credential is valid; skipping pairing.")
            return
        print("Stored relay credential is invalid or expired; re-pairing now.")
        reset_agent_credential()
    if force:
        reset_agent_credential()

    vps_url = _normalise_vps_url(_require_env("VPS_URL"))
    stable_agent_id = config.agent_id if (config.agent_id or "").startswith("agt_") else None

    while True:
        agent_id, pairing_code, pairing_pin, expires_in, qr_payload = _register_start(existing_agent_id=stable_agent_id)
        stable_agent_id = agent_id

        print("")
        print("=== Agent pairing required ===")
        print("Open the Android app and complete pairing with:")
        print(f"  VPS URL: {vps_url}")
        print(f"  Agent ID: {agent_id}")
        print(f"  Pairing Code: {pairing_code}")
        if pairing_pin:
            print(f"  Pairing PIN: {pairing_pin}")
        else:
            print("  Pairing PIN: not required by this VPS build")
        print(f"  Expires In: {expires_in}s")
        print(f"  QR Payload: {qr_payload}")
        print("==============================")
        print("")

        if pairing_session_callback:
            try:
                pairing_session_callback(
                    {
                        "vps_url": vps_url,
                        "agent_id": agent_id,
                        "pairing_code": pairing_code,
                        "pairing_pin": pairing_pin,
                        "pairing_expires_in": expires_in,
                        "qr_payload": qr_payload,
                        "status": "AWAITING_PAIR",
                    }
                )
            except Exception as callback_exc:
                print(f"Pairing session callback failed: {callback_exc}")

        on_status_update = None
        stop_ui = None
        should_use_browser_ui = _pairing_browser_enabled() if browser_ui is None else browser_ui
        if should_use_browser_ui:
            try:
                pairing_state = {
                    "status": "AWAITING_PAIR",
                    "agent_id": agent_id,
                    "pairing_code": pairing_code,
                    "pairing_pin": pairing_pin,
                    "pairing_expires_in": expires_in,
                    "qr_payload": qr_payload,
                    "vps_url": vps_url,
                    "started_at_epoch": int(time.time()),
                    "updated_at_epoch": int(time.time()),
                }
                ui_url, on_status_update, stop_ui = start_pairing_browser_ui(pairing_state)
                print(f"Pairing page: {ui_url}")
            except Exception as ui_exc:
                print(f"Could not start pairing browser UI: {ui_exc}")
        elif pairing_status_callback:
            on_status_update = pairing_status_callback

        if pairing_status_callback and on_status_update is not pairing_status_callback:
            base_update = on_status_update

            def combined_status_update(status: str) -> None:
                if base_update:
                    base_update(status)
                pairing_status_callback(status)

            on_status_update = combined_status_update

        try:
            activation_token = _wait_for_pairing(agent_id, on_status_update=on_status_update)
            try:
                credential, relay_secret = _activate_registration(agent_id, activation_token)
            except ActivationTokenInvalidError:
                # Contract: re-check status once; if still paired with token retry once.
                status, latest_activation_token = _fetch_pairing_status(agent_id)
                if status == "PAIRED" and latest_activation_token:
                    try:
                        credential, relay_secret = _activate_registration(agent_id, latest_activation_token)
                    except ActivationTokenInvalidError:
                        # Some VPS builds can race token issuance/rotation under load.
                        # Instead of failing the whole flow, request a fresh pairing session.
                        print("Activation token rotated again; restarting pairing session")
                        continue
                else:
                    print("Activation token invalid and no replacement token available; restarting pairing")
                    continue

            _persist_agent_credential(agent_id, credential, relay_secret=relay_secret)
            if on_status_update:
                on_status_update("ACTIVE")
            # Keep the page alive briefly so the user sees success.
            time.sleep(2)
            print(f"Agent '{agent_id}' paired and activated successfully.")
            return
        except PairingExpiredError:
            print("Pairing session expired; requesting a new pairing code")
            continue
        except PairingRevokedError:
            raise RuntimeError("Pairing revoked by VPS. Run `vela --setup` to re-onboard this device.")
        finally:
            if stop_ui:
                stop_ui()


def _get_vps_secret() -> str:
    config = get_config()
    secret = (config.relay_secret or config.agent_secret or "").strip()
    if not secret:
        raise RuntimeError("Cannot refresh ws_token: RELAY_SECRET not configured")
    return secret


def refresh_ws_token():
    """Get a fresh WebSocket token using the agent's secret.
    
    Uses POST /agents/{agent_id}/ws-token with X-Secret header.
    This is the preferred method for token refresh after initial registration.
    """
    config = get_config()
    vps_url = _normalise_vps_url(_require_env("VPS_URL"))
    agent_id = config.agent_id
    relay_secret = _get_vps_secret()

    url = f"{vps_url.rstrip('/')}/agents/{agent_id}/ws-token"
    headers = {"X-Secret": relay_secret}

    print(f"Refreshing ws_token for agent '{agent_id}'...")
    resp = requests.post(
        url,
        headers=headers,
        timeout=config.local_service_timeout,
    )

    print(f"VPS ws-token refresh status: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        return data.get("ws_token")

    raise Exception(f"Token refresh failed: {resp.text}")
