"""Persist and query alert delivery history for verification."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, UTC
from typing import Any

from sqlalchemy import func, select

from app.db.audit_log import AlertDeliveryEventModel, get_audit_session, insert_alert_delivery_event

logger = logging.getLogger(__name__)

MAX_LOOKBACK_MINUTES = 60 * 24 * 90


def _resend_id(email_result: dict[str, Any] | None) -> str | None:
    if not email_result:
        return None
    provider_id = email_result.get("id")
    return str(provider_id) if provider_id else None


def _delivery_status(
    *,
    email_attempted: bool,
    email_result: dict[str, Any] | None,
    email_error: str | None,
    push_attempted: bool,
    push_delivered: int,
    push_error: str | None,
) -> str:
    email_ok = email_attempted and email_result is not None and not email_error
    push_ok = push_attempted and push_delivered > 0 and not push_error
    email_failed = email_attempted and not email_ok
    push_failed = push_attempted and not push_ok

    if email_ok or push_ok:
        if (email_failed and push_ok) or (push_failed and email_ok):
            return "partial"
        return "sent"
    if email_attempted or push_attempted:
        return "failed"
    return "skipped"


def _channel_label(*, email_attempted: bool, push_attempted: bool) -> str:
    if email_attempted and push_attempted:
        return "both"
    if email_attempted:
        return "email"
    if push_attempted:
        return "push"
    return "none"


def record_delivery(
    *,
    alert_kind: str,
    title: str | None = None,
    body: str | None = None,
    email_to: str | None = None,
    email_result: dict[str, Any] | None = None,
    email_error: str | None = None,
    email_attempted: bool = False,
    push_attempted: bool = False,
    push_delivered: int = 0,
    push_error: str | None = None,
    alert_type: str | None = None,
    value: float | None = None,
    threshold: float | None = None,
    resource: str | None = None,
    fingerprint: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    """Persist one delivery attempt. Returns row id, or None if storage failed."""
    status = _delivery_status(
        email_attempted=email_attempted,
        email_result=email_result,
        email_error=email_error,
        push_attempted=push_attempted,
        push_delivered=push_delivered,
        push_error=push_error,
    )
    channel = _channel_label(email_attempted=email_attempted, push_attempted=push_attempted)
    errors = [msg for msg in (email_error, push_error) if msg]
    try:
        return insert_alert_delivery_event(
            alert_kind=alert_kind,
            channel=channel,
            status=status,
            title=title,
            body=body,
            email_to=email_to,
            email_provider_id=_resend_id(email_result),
            push_delivered=push_delivered,
            alert_type=alert_type,
            value=value,
            threshold=threshold,
            resource=resource,
            fingerprint=fingerprint,
            metadata_json=json.dumps(metadata, separators=(",", ":")) if metadata else None,
            error="; ".join(errors)[:1_000] if errors else None,
        )
    except Exception as exc:
        logger.debug("Alert delivery history write skipped: %s", exc)
        return None


def _row_to_dict(row: AlertDeliveryEventModel) -> dict[str, Any]:
    metadata = None
    if row.metadata_json:
        try:
            metadata = json.loads(row.metadata_json)
        except json.JSONDecodeError:
            metadata = {"raw": row.metadata_json}
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "alert_kind": row.alert_kind,
        "channel": row.channel,
        "status": row.status,
        "title": row.title,
        "body": row.body,
        "email_to": row.email_to,
        "email_provider_id": row.email_provider_id,
        "push_delivered": row.push_delivered,
        "alert_type": row.alert_type,
        "value": row.value,
        "threshold": row.threshold,
        "resource": row.resource,
        "fingerprint": row.fingerprint,
        "error": row.error,
        "metadata": metadata,
    }


def list_deliveries(
    *,
    limit: int = 100,
    offset: int = 0,
    since_minutes: int | None = None,
    alert_kind: str | None = None,
    channel: str | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    with get_audit_session() as session:
        stmt = select(AlertDeliveryEventModel).order_by(
            AlertDeliveryEventModel.created_at.desc(),
            AlertDeliveryEventModel.id.desc(),
        )
        if since_minutes is not None and since_minutes > 0:
            since = datetime.now(UTC) - timedelta(minutes=min(since_minutes, MAX_LOOKBACK_MINUTES))
            stmt = stmt.where(AlertDeliveryEventModel.created_at >= since)
        if alert_kind:
            stmt = stmt.where(AlertDeliveryEventModel.alert_kind == alert_kind)
        if channel:
            stmt = stmt.where(AlertDeliveryEventModel.channel == channel)
        rows = session.scalars(stmt.offset(offset).limit(limit)).all()
        return [_row_to_dict(row) for row in rows]


def count_deliveries() -> int:
    with get_audit_session() as session:
        return int(session.scalar(select(func.count()).select_from(AlertDeliveryEventModel)) or 0)


def count_today(*, alert_kind: str | None = None) -> int:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with get_audit_session() as session:
        stmt = select(func.count()).select_from(AlertDeliveryEventModel).where(
            AlertDeliveryEventModel.created_at >= start,
            AlertDeliveryEventModel.status.in_(("sent", "partial")),
        )
        if alert_kind:
            stmt = stmt.where(AlertDeliveryEventModel.alert_kind == alert_kind)
        return int(session.scalar(stmt) or 0)


def last_delivery_time_today() -> str | None:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with get_audit_session() as session:
        row = session.scalar(
            select(AlertDeliveryEventModel)
            .where(
                AlertDeliveryEventModel.created_at >= start,
                AlertDeliveryEventModel.status.in_(("sent", "partial")),
            )
            .order_by(AlertDeliveryEventModel.created_at.desc(), AlertDeliveryEventModel.id.desc())
            .limit(1)
        )
    if row is None:
        return None
    local = row.created_at.astimezone()
    return local.strftime("%H:%M")
