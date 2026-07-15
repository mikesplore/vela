import asyncio
import getpass
import platform
import os
import socket
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlparse, urlunparse

from dotenv import set_key
import requests
import json

from app.agent.tunnel import tunnel
from app.agent.pairing_ui import render_pairing_page

from app.utils.config import Config
config = Config()

_local_token: str | None = None
_local_token_expires = datetime.min.replace(tzinfo=timezone.utc)
PAIRING_STATUS_POLL_INTERVAL = 3
PAIRING_STATUS_TIMEOUT = 600


class PairingExpiredError(RuntimeError):
    pass


class PairingRevokedError(RuntimeError):
    pass


class ActivationTokenInvalidError(RuntimeError):
    pass


def parse_metadata() -> dict | None:
    """Parse METADATA environment variable as JSON."""
    if not config.metadata_raw:
        return None
    try:
        return json.loads(config.metadata_raw)
    except json.JSONDecodeError:
        print(f"Warning: METADATA is not valid JSON, ignoring: {config.metadata_raw}")
        return None


def agent_settings() -> tuple[str, str, str]:
    return (
        _normalise_vps_url(_require_env("VPS_URL")),
        config.agent_id,
        config.agent_secret,
    )


def parse_local_expiry(expires_at: str) -> datetime:
    dt = datetime.fromisoformat(expires_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_local_auth_token(retries: int = 3, delay: float = 2.0) -> str:
    global _local_token, _local_token_expires

    now = datetime.now(timezone.utc)

    # 1. Try in-memory token
    if _local_token and now + timedelta(seconds=30) < _local_token_expires:
        return _local_token

    # 2. Try environment/dotenv token
    if config.local_service_auth_token and config.local_service_auth_token_expires:
        try:
            expires = parse_local_expiry(config.local_service_auth_token_expires)
            if now + timedelta(seconds=30) < expires:
                _local_token = config.local_service_auth_token
                _local_token_expires = expires
                return _local_token
        except Exception as e:
            print(f"Error parsing config.local_service_auth_token_expires: {e}")

    # 3. Fallback for manually set token without expiry (if any)
    if config.local_service_auth_token and not config.local_service_auth_token_expires:
         return config.local_service_auth_token

    if not config.local_service_username or not config.local_service_password:
        raise RuntimeError(
            "config.local_service_username and config.local_service_password must be set to obtain a local auth token"
        )

    token_url = f"{config.local_service_url}{config.local_service_token_path}"

    last_exc = None
    for attempt in range(retries):
        print(f"Obtaining local auth token from {token_url} (attempt {attempt + 1}/{retries})")
        resp = None
        try:
            resp = requests.post(
                token_url,
                json={"username": config.local_service_username, "password": config.local_service_password},
                timeout=config.local_service_timeout,
            )
            print(f"Local auth response status: {resp.status_code}")
            resp.raise_for_status()

            data = resp.json()
            _local_token = data.get("access_token")
            expiry_str = data.get("expires_at")
            _local_token_expires = parse_local_expiry(expiry_str)

            # Persist to .env
            try:
                set_key(config.dotenv_path, "LOCAL_SERVICE_AUTH_TOKEN", _local_token)
                set_key(config.dotenv_path, "LOCAL_SERVICE_AUTH_TOKEN_EXPIRES", expiry_str)
                print(f"Persisted local auth token to {config.dotenv_path}")
            except Exception as env_exc:
                print(f"Failed to persist token to .env: {env_exc}")

            print(f"Obtained local auth token expiring at {_local_token_expires.isoformat()}")
            return _local_token
        except Exception as exc:
            last_exc = exc
            print(f"Local auth token request failed (attempt {attempt + 1}/{retries}): {exc}")
            if resp is not None:
                print(f"Local auth failure response: status={resp.status_code}")
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))  # Exponential backoff

    raise last_exc


async def async_get_local_auth_token(retries: int = 3) -> str:
    return await asyncio.to_thread(get_local_auth_token, retries=retries)


async def wait_for_local_service(timeout: int = 60):
    """Wait for the local FastAPI service to be ready."""
    start_time = asyncio.get_event_loop().time()
    health_url = f"{config.local_service_url}/health"
    print(f"Waiting for local service at {health_url}...")

    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            resp = await asyncio.to_thread(requests.get, health_url, timeout=2)
            if resp.status_code == 200:
                print("Local service is up and healthy.")
                return True
        except Exception:
            pass
        await asyncio.sleep(2)

    print(f"Warning: Local service at {config.local_service_url} not reached after {timeout}s")
    return False


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


def _register_start(existing_agent_id: str | None = None) -> tuple[str, str, str | None, int, str | None]:
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

    qr_payload = data.get("pairing_qr_payload")
    if qr_payload:
        print(f"Pairing QR payload: {qr_payload}")

    return agent_id, pairing_code, pairing_pin, pairing_expires_in, qr_payload


def _fetch_pairing_status(agent_id: str) -> tuple[str | None, str | None]:
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


def _persist_agent_credential(agent_id: str, credential: str, relay_secret: str | None = None) -> None:
    if not relay_secret:
        raise RuntimeError("register/activate response missing relay_secret")

    try:
        set_key(config.dotenv_path, "AGENT_ID", agent_id)
        # AGENT_SECRET is kept as a backwards-compatible alias for relay_secret.
        set_key(config.dotenv_path, "AGENT_SECRET", relay_secret)
        set_key(config.dotenv_path, "AGENT_CREDENTIAL", credential)
        set_key(config.dotenv_path, "RELAY_SECRET", relay_secret)
        print(f"Persisted AGENT_ID, RELAY_SECRET, and AGENT_CREDENTIAL to {config.dotenv_path}")
    except Exception as env_exc:
        print(f"Failed to persist AGENT credential to .env: {env_exc}")

    config.agent_id = agent_id
    config.agent_secret = credential
    config.relay_secret = relay_secret


def _pairing_browser_enabled() -> bool:
    raw = os.getenv("PAIRING_BROWSER_UI", "true").strip().lower()
    return raw not in {"0", "false", "no"}


def _start_pairing_browser_ui(
    vps_url: str,
    agent_id: str,
    pairing_code: str,
    pairing_pin: str | None,
    expires_in: int,
    qr_payload: str | None,
):
    pair_complete_url = f"{vps_url.rstrip('/')}/pair/complete"
    qr_scan_payload = json.dumps(
        {
            "pair_url": pair_complete_url,
            "vps_url": vps_url,
            "pairing_code": pairing_code,
            "pairing_pin": pairing_pin,
        },
        separators=(",", ":"),
    )
    if not pairing_pin:
        qr_scan_payload = json.dumps(
            {
                "pair_url": pair_complete_url,
                "vps_url": vps_url,
                "pairing_code": pairing_code,
            },
            separators=(",", ":"),
        )

    state = {
        "status": "AWAITING_PAIR",
        "agent_id": agent_id,
        "pairing_code": pairing_code,
        "pairing_pin": pairing_pin,
        "pairing_expires_in": expires_in,
        "qr_payload": qr_scan_payload,
        "vps_url": vps_url,
        "started_at_epoch": int(time.time()),
        "updated_at_epoch": int(time.time()),
    }

    class PairingHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in {"/", "/index.html"}:
                page = render_pairing_page(state)
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path in {"/status", "/state"}:
                payload = json.dumps(state).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), PairingHandler)
    host, port = server.server_address
    url = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def update_status(new_status: str) -> None:
        state["status"] = new_status
        state["updated_at_epoch"] = int(time.time())

    def stop() -> None:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass

    return url, update_status, stop


def reset_agent_credential() -> None:
    """Clear persisted agent credential to force re-pairing."""
    try:
        set_key(config.dotenv_path, "AGENT_SECRET", "")
        set_key(config.dotenv_path, "AGENT_CREDENTIAL", "")
        set_key(config.dotenv_path, "RELAY_SECRET", "")
    except Exception as env_exc:
        print(f"Failed to clear agent credential in .env: {env_exc}")
    config.agent_secret = ""
    config.relay_secret = ""


def ensure_agent_registration(force: bool = False) -> None:
    if config.relay_secret and not force:
        return
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
        if qr_payload:
            print(f"  QR Payload: {qr_payload}")
        print("==============================")
        print("")

        on_status_update = None
        stop_ui = None
        if _pairing_browser_enabled():
            try:
                ui_url, on_status_update, stop_ui = _start_pairing_browser_ui(
                    vps_url=vps_url,
                    agent_id=agent_id,
                    pairing_code=pairing_code,
                    pairing_pin=pairing_pin,
                    expires_in=expires_in,
                    qr_payload=qr_payload,
                )
                print(f"Pairing page: {ui_url}")
                webbrowser.open(ui_url)
            except Exception as ui_exc:
                print(f"Could not start pairing browser UI: {ui_exc}")

        try:
            activation_token = _wait_for_pairing(agent_id, on_status_update=on_status_update)
            try:
                credential, relay_secret = _activate_registration(agent_id, activation_token)
            except ActivationTokenInvalidError:
                # Contract: re-check status once; if still paired with token retry once.
                status, latest_activation_token = _fetch_pairing_status(agent_id)
                if status == "PAIRED" and latest_activation_token:
                    credential, relay_secret = _activate_registration(agent_id, latest_activation_token)
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
            raise RuntimeError("Pairing revoked by VPS. Run `vela --pair` to re-onboard this device.")
        finally:
            if stop_ui:
                stop_ui()


def _get_vps_secret() -> str:
    secret = (config.relay_secret or config.agent_secret or "").strip()
    if not secret:
        raise RuntimeError("Cannot refresh ws_token: RELAY_SECRET not configured")
    return secret


def refresh_ws_token():
    """Get a fresh WebSocket token using the agent's secret.
    
    Uses POST /agents/{agent_id}/ws-token with X-Secret header.
    This is the preferred method for token refresh after initial registration.
    """
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



async def start_agent_loop() -> None:
    """Main agent loop.
    
    Expects the device to be paired (AGENT_ID + RELAY_SECRET in .env).
    Uses the refresh token endpoint (POST /agents/{id}/ws-token) for connection.
    
    The /register endpoint should only be used by setup.sh for initial registration.
    """
    await wait_for_local_service()

    if not config.vps_url:
        raise RuntimeError("VPS_URL must be set before starting vela-agent")

    if not config.relay_secret:
        raise RuntimeError(
            "Agent is not paired yet. Run `vela --pair` (or `vela --setup`) to complete pairing."
        )

    backoff = 5
    max_backoff = 60

    while True:
        try:
            token = await asyncio.to_thread(refresh_ws_token)
            print(f"Refreshed ws_token: {token[:10]}...")
            await tunnel(token)
            # Tunnel exited cleanly — reset backoff
            backoff = 5
        except Exception as exc:
            print(f"Agent loop error: {exc}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set by setup before starting vela-agent")
    return value


def _default_agent_id() -> str:
    user = getpass.getuser() or "user"
    host = socket.gethostname() or "host"
    return f"{user}-{host}"


def _normalise_vps_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("VPS_URL must include http:// or https:// and a host")
    return raw_url.rstrip("/")


def websocket_tunnel_url(vps_url: str, agent_id: str, token: str) -> str:
    parsed = urlparse(vps_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = urlencode({"agent_id": agent_id, "token": token})
    return urlunparse((scheme, parsed.netloc, "/tunnel", "", query, ""))