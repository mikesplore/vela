"""Firebase Cloud Messaging delivery for registered Vela mobile devices."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select

from app.db.audit_log import ExternalAlertDeliveryModel, PushDeviceModel, get_audit_session
from app.utils.config import get_config

logger = logging.getLogger(__name__)
_firebase_initialized = False


def is_configured() -> bool:
    path = get_config().fcm_service_account_path
    return bool(path and Path(path).expanduser().is_file())


def register_device(*, user_id: str, token: str, installation_id: str | None = None) -> None:
    now = datetime.now(UTC)
    with get_audit_session() as session:
        device = session.scalar(select(PushDeviceModel).where(PushDeviceModel.token == token))
        if device:
            device.user_id = user_id
            device.installation_id = installation_id
            device.updated_at = now
        else:
            session.add(
                PushDeviceModel(
                    token=token,
                    user_id=user_id,
                    installation_id=installation_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()


def unregister_device(*, user_id: str, token: str) -> bool:
    with get_audit_session() as session:
        result = session.execute(
            delete(PushDeviceModel).where(
                PushDeviceModel.token == token,
                PushDeviceModel.user_id == user_id,
            )
        )
        session.commit()
    return bool(result.rowcount)


def send_push(*, title: str, body: str, data: dict[str, str], user_id: str | None = None) -> int:
    messaging = _get_messaging()
    if messaging is None:
        return 0
    with get_audit_session() as session:
        stmt = select(PushDeviceModel)
        if user_id:
            stmt = stmt.where(PushDeviceModel.user_id == user_id)
        devices = list(session.scalars(stmt))

    delivered = 0
    invalid_tokens: list[str] = []
    for device in devices:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={key: str(value) for key, value in data.items()},
                token=device.token,
            )
            messaging.send(message)
            delivered += 1
        except Exception as exc:
            code = getattr(exc, "code", None)
            if str(code) in {"NOT_FOUND", "UNREGISTERED"} or "registration-token-not-registered" in str(exc):
                invalid_tokens.append(device.token)
            else:
                logger.warning("FCM delivery failed for device %s: %s", device.id, exc)
    if invalid_tokens:
        with get_audit_session() as session:
            session.execute(delete(PushDeviceModel).where(PushDeviceModel.token.in_(invalid_tokens)))
            session.commit()
    return delivered


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


def _get_messaging():
    global _firebase_initialized
    path = get_config().fcm_service_account_path
    if not path:
        logger.info("FCM push is not configured: set VELA_FCM_SERVICE_ACCOUNT_PATH.")
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
    except ImportError:
        logger.warning("FCM push is unavailable: firebase-admin is not installed.")
        return None
    if not _firebase_initialized:
        credential_path = Path(path).expanduser()
        if not credential_path.is_file():
            logger.error("FCM service account file does not exist: %s", credential_path)
            return None
        firebase_admin.initialize_app(credentials.Certificate(str(credential_path)))
        _firebase_initialized = True
    return messaging
