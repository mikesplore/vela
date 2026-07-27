"""Push notification delivery via the Vela VPS relay (FCM lives on the VPS, not the PC)."""
from __future__ import annotations

import logging
import os
import platform
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.db.audit_log import ExternalAlertDeliveryModel, get_audit_session
from app.utils.config import get_config

logger = logging.getLogger(__name__)


def agent_label() -> str:
    """Human-readable agent name for notification copy."""
    name = os.environ.get("AGENT_NAME", "").strip()
    if name:
        return name
    return platform.node()


def format_push_title(title: str) -> str:
    """Prefix notification titles with this agent's label for multi-agent phones."""
    label = agent_label()
    prefix = f"Vela · {label}"
    if title.startswith(prefix):
        return title
    if title.startswith("Vela alert · "):
        return f"{prefix} · {title[len('Vela alert · '):]}"
    if title.startswith("Vela resolved · "):
        return f"{prefix} · {title[len('Vela resolved · '):]}"
    if title.startswith("Vela · "):
        rest = title[len("Vela · "):]
        if rest.startswith(label):
            return title
        return f"{prefix} · {rest}"
    if title.startswith(f"{label} · "):
        return title
    return f"{prefix} · {title}"


def _relay_credentials() -> tuple[str, str, str] | None:
    config = get_config()
    vps_url = (config.vps_url or "").strip().rstrip("/")
    agent_id = (config.agent_id or "").strip()
    secret = (config.relay_secret or config.agent_secret or "").strip()
    if not vps_url or not agent_id or not secret:
        return None
    return vps_url, agent_id, secret


def get_configuration_error() -> str | None:
    if _relay_credentials() is None:
        return "Push relay not configured (set VPS_URL, AGENT_ID, and RELAY_SECRET)"
    return None


def is_configured() -> bool:
    return get_configuration_error() is None


def register_device(*, user_id: str, token: str, installation_id: str | None = None) -> None:
    creds = _relay_credentials()
    if creds is None:
        logger.info("Skipping push device registration: VPS relay credentials missing")
        return
    vps_url, agent_id, secret = creds
    try:
        response = httpx.post(
            f"{vps_url}/relay/{agent_id}/push/devices",
            headers={"X-Secret": secret},
            json={"token": token, "installation_id": installation_id},
            timeout=20,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("VPS push device registration failed: %s", exc)
        raise


def unregister_device(*, user_id: str, token: str) -> bool:
    creds = _relay_credentials()
    if creds is None:
        return False
    vps_url, agent_id, secret = creds
    try:
        response = httpx.request(
            "DELETE",
            f"{vps_url}/relay/{agent_id}/push/devices",
            headers={"X-Secret": secret},
            json={"token": token},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("success"))
    except Exception as exc:
        logger.warning("VPS push device unregister failed: %s", exc)
        return False


def send_push(*, title: str, body: str, data: dict[str, str], user_id: str | None = None) -> int:
    creds = _relay_credentials()
    if creds is None:
        logger.info("Push send skipped: VPS relay credentials missing")
        return 0
    vps_url, agent_id, secret = creds
    try:
        response = httpx.post(
            f"{vps_url}/agents/{agent_id}/push/send",
            headers={"X-Secret": secret},
            json={"title": format_push_title(title), "body": body, "data": data},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return int(payload.get("delivered") or 0)
    except Exception as exc:
        logger.warning("VPS push send failed: %s", exc)
        return 0


def claim_external_alert(*, fingerprint: str, status: str) -> bool:
    """Return true only once per Alertmanager fingerprint/status pair."""
    with get_audit_session() as session:
        existing = session.scalar(
            select(ExternalAlertDeliveryModel).where(
                ExternalAlertDeliveryModel.fingerprint == fingerprint,
                ExternalAlertDeliveryModel.status == status,
            )
        )
        if existing:
            return False
        session.add(
            ExternalAlertDeliveryModel(
                fingerprint=fingerprint,
                status=status,
                received_at=datetime.now(UTC),
            )
        )
        session.commit()
    return True
