"""Live and historical health information for the local relay tunnel."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.db.audit_log import (
    RelayConnectionEventModel,
    get_audit_session,
    insert_relay_connection_event,
)
_state: dict[str, Any] = {
    "status": "not_configured",
    "connected_since": None,
    "last_connected_at": None,
    "last_disconnected_at": None,
    "last_message_at": None,
    "last_persisted_message_at": None,
    "last_error": None,
    "has_connected": False,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _record(event_type: str, detail: str | None = None) -> None:
    try:
        insert_relay_connection_event(event_type=event_type, detail=detail)
    except Exception:
        # Tunnel availability must never depend on diagnostic storage.
        pass


def mark_connecting() -> None:
    _state["status"] = "reconnecting" if _state["has_connected"] else "connecting"


def mark_connected() -> None:
    now = _now()
    reconnected = _state["has_connected"]
    _state.update(
        status="connected",
        connected_since=now,
        last_connected_at=now,
        last_error=None,
        has_connected=True,
    )
    _record("reconnected" if reconnected else "connected")


def mark_message_received() -> None:
    now = _now()
    _state["last_message_at"] = now
    last_persisted = _state["last_persisted_message_at"]
    # Persist a lightweight liveness marker at most every five minutes. This
    # lets the dashboard observe an already-open tunnel across processes
    # without growing the event table on every relay heartbeat.
    if last_persisted is None or (now - last_persisted).total_seconds() >= 300:
        _state["last_persisted_message_at"] = now
        _record("heartbeat")


def mark_disconnected(error: Exception | str) -> None:
    now = _now()
    detail = str(error)[:500]
    _state.update(
        status="disconnected",
        connected_since=None,
        last_disconnected_at=now,
        last_error=detail,
    )
    _record("disconnected", detail)


def summary(*, since_minutes: int = 60) -> dict[str, Any]:
    since_minutes = max(1, min(since_minutes, 60 * 24 * 90))
    since = _now() - timedelta(minutes=since_minutes)
    with get_audit_session() as session:
        events = list(
            session.scalars(
                select(RelayConnectionEventModel)
                .where(RelayConnectionEventModel.created_at >= since)
                .order_by(RelayConnectionEventModel.created_at.desc())
                .limit(25)
            )
        )
        last_event = session.scalar(
            select(RelayConnectionEventModel)
            .order_by(RelayConnectionEventModel.created_at.desc())
            .limit(1)
        )
        last_connection = session.scalar(
            select(RelayConnectionEventModel)
            .where(RelayConnectionEventModel.event_type.in_(("connected", "reconnected")))
            .order_by(RelayConnectionEventModel.created_at.desc())
            .limit(1)
        )
        last_disconnection = session.scalar(
            select(RelayConnectionEventModel)
            .where(RelayConnectionEventModel.event_type == "disconnected")
            .order_by(RelayConnectionEventModel.created_at.desc())
            .limit(1)
        )
        last_liveness = session.scalar(
            select(RelayConnectionEventModel)
            .where(RelayConnectionEventModel.event_type.in_(("connected", "reconnected", "heartbeat")))
            .order_by(RelayConnectionEventModel.created_at.desc())
            .limit(1)
        )

    if last_event is None:
        status = "unknown"
        connected_since = None
    elif last_event.event_type == "disconnected":
        status = "disconnected"
        connected_since = None
    else:
        status = "connected"
        connected_since = _as_utc(last_connection.created_at) if last_connection else None
    return {
        # The FastAPI dashboard and relay agent are separate processes. A
        # persisted event is the only reliable cross-process configuration
        # signal, so avoid consulting the dashboard process's environment.
        "configured": last_event is not None,
        "status": status,
        "connected_since": connected_since.isoformat() if connected_since else None,
        "last_connected_at": _iso(last_connection.created_at) if last_connection else None,
        "last_disconnected_at": _iso(last_disconnection.created_at) if last_disconnection else None,
        "last_message_at": _iso(last_liveness.created_at) if last_liveness else None,
        "last_error": last_disconnection.detail if last_event and last_event.event_type == "disconnected" else None,
        "connected_seconds": round((_now() - connected_since).total_seconds()) if connected_since else None,
        "disconnect_count": sum(event.event_type == "disconnected" for event in events),
        "reconnect_count": sum(event.event_type == "reconnected" for event in events),
        "recent_events": [
            {
                "created_at": event.created_at.replace(tzinfo=UTC).isoformat()
                if event.created_at.tzinfo is None
                else event.created_at.isoformat(),
                "event_type": event.event_type,
                "detail": event.detail,
            }
            for event in events
        ],
    }


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value else None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
