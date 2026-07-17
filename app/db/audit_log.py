"""SQLite persistence for API audit / request metrics."""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(index=True)
    method: Mapped[str]
    path: Mapped[str] = mapped_column(index=True)
    status_code: Mapped[int] = mapped_column(index=True)
    duration_ms: Mapped[float]
    user_id: Mapped[str | None] = mapped_column(nullable=True)
    client_ip: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)


class ToolCallEventModel(Base):
    """One assistant tool execution, linked to its parent HTTP request."""
    __tablename__ = "assistant_tool_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(index=True)
    tool_name: Mapped[str] = mapped_column(index=True)
    duration_ms: Mapped[float]
    succeeded: Mapped[bool] = mapped_column(index=True)
    user_id: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)


class RelayConnectionEventModel(Base):
    """A relay tunnel lifecycle event emitted by the local agent."""
    __tablename__ = "relay_connection_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(index=True)
    detail: Mapped[str | None] = mapped_column(nullable=True)


class AdminActionEventModel(Base):
    """Administrative actions retained separately from clearable monitoring data."""
    __tablename__ = "admin_action_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(index=True)
    actor: Mapped[str | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(index=True)
    detail: Mapped[str | None] = mapped_column(nullable=True)


db_path = Path.cwd() / "audit_log.sqlite"
engine = create_engine(
    f"sqlite:///{db_path}",
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 5},
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    """Allow the API and tunnel agent to write telemetry concurrently."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def init_audit_db() -> None:
    Base.metadata.create_all(engine)


def get_audit_session() -> Session:
    return Session(engine)


def insert_audit_event(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    user_id: str | None = None,
    client_ip: str | None = None,
    error: str | None = None,
    created_at: datetime | None = None,
) -> None:
    with get_audit_session() as session:
        session.add(
            AuditEventModel(
                request_id=request_id,
                created_at=created_at or datetime.now(UTC),
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                user_id=user_id,
                client_ip=client_ip,
                error=error,
            )
        )
        session.commit()


def insert_tool_call_event(
    *,
    request_id: str,
    tool_name: str,
    duration_ms: float,
    succeeded: bool,
    user_id: str | None = None,
    error: str | None = None,
    created_at: datetime | None = None,
) -> None:
    with get_audit_session() as session:
        session.add(
            ToolCallEventModel(
                request_id=request_id,
                created_at=created_at or datetime.now(UTC),
                tool_name=tool_name,
                duration_ms=duration_ms,
                succeeded=succeeded,
                user_id=user_id,
                error=error,
            )
        )
        session.commit()


def insert_relay_connection_event(
    *,
    event_type: str,
    detail: str | None = None,
    created_at: datetime | None = None,
) -> None:
    with get_audit_session() as session:
        session.add(
            RelayConnectionEventModel(
                created_at=created_at or datetime.now(UTC),
                event_type=event_type,
                detail=detail,
            )
        )
        session.commit()


def insert_admin_action_event(*, actor: str | None, action: str, detail: str | None = None) -> None:
    with get_audit_session() as session:
        session.add(
            AdminActionEventModel(
                created_at=datetime.now(UTC),
                actor=actor,
                action=action,
                detail=detail,
            )
        )
        session.commit()


def prune_audit_events(
    *,
    older_than: datetime | None = None,
    relay_older_than: datetime | None = None,
    admin_action_older_than: datetime | None = None,
    keep_max: int | None = None,
    relay_keep_max: int | None = None,
) -> int:
    """Delete old / excess rows. Returns number of deleted rows."""
    deleted = 0
    with get_audit_session() as session:
        if older_than is not None:
            result = session.execute(delete(AuditEventModel).where(AuditEventModel.created_at < older_than))
            deleted += result.rowcount or 0
            result = session.execute(delete(ToolCallEventModel).where(ToolCallEventModel.created_at < older_than))
            deleted += result.rowcount or 0
        if relay_older_than is not None:
            result = session.execute(
                delete(RelayConnectionEventModel).where(RelayConnectionEventModel.created_at < relay_older_than)
            )
            deleted += result.rowcount or 0
        if keep_max is not None and keep_max > 0:
            # Keep newest keep_max rows
            ids_to_keep = list(
                session.scalars(
                    select(AuditEventModel.id)
                    .order_by(AuditEventModel.created_at.desc(), AuditEventModel.id.desc())
                    .limit(keep_max)
                )
            )
            if ids_to_keep:
                result = session.execute(
                    delete(AuditEventModel).where(AuditEventModel.id.notin_(ids_to_keep))
                )
                deleted += result.rowcount or 0
            tool_ids_to_keep = list(
                session.scalars(
                    select(ToolCallEventModel.id)
                    .order_by(ToolCallEventModel.created_at.desc(), ToolCallEventModel.id.desc())
                    .limit(keep_max)
                )
            )
            if tool_ids_to_keep:
                result = session.execute(
                    delete(ToolCallEventModel).where(ToolCallEventModel.id.notin_(tool_ids_to_keep))
                )
                deleted += result.rowcount or 0
        if admin_action_older_than is not None:
            result = session.execute(
                delete(AdminActionEventModel).where(AdminActionEventModel.created_at < admin_action_older_than)
            )
            deleted += result.rowcount or 0
        if relay_keep_max is not None and relay_keep_max > 0:
            relay_ids_to_keep = list(
                session.scalars(
                    select(RelayConnectionEventModel.id)
                    .order_by(RelayConnectionEventModel.created_at.desc(), RelayConnectionEventModel.id.desc())
                    .limit(relay_keep_max)
                )
            )
            if relay_ids_to_keep:
                result = session.execute(
                    delete(RelayConnectionEventModel).where(
                        RelayConnectionEventModel.id.notin_(relay_ids_to_keep)
                    )
                )
                deleted += result.rowcount or 0
        session.commit()
    return deleted


def clear_monitoring_history() -> int:
    """Remove monitoring data while retaining administrative-action records."""
    with get_audit_session() as session:
        deleted = 0
        for model in (AuditEventModel, ToolCallEventModel, RelayConnectionEventModel):
            result = session.execute(delete(model))
            deleted += result.rowcount or 0
        session.commit()
    return deleted
