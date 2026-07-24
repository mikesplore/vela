"""SQLite persistence for runtime capability probes."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class CapabilityModel(Base):
    """One probed capability (module, subfeature, or assistant tool)."""

    __tablename__ = "capabilities"

    key: Mapped[str] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(index=True)
    available: Mapped[bool] = mapped_column(index=True)
    reason: Mapped[str | None] = mapped_column(nullable=True)
    checked_at: Mapped[datetime] = mapped_column(index=True)
    metadata_json: Mapped[str | None] = mapped_column(nullable=True)


db_path = Path.cwd() / "capabilities.sqlite"
engine = create_engine(f"sqlite:///{db_path}", echo=False)


def init_capabilities_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def replace_capabilities(rows: list[dict]) -> datetime:
    """Replace the full capability snapshot atomically."""
    checked_at = datetime.now(UTC)
    with get_session() as session:
        session.execute(delete(CapabilityModel))
        for row in rows:
            metadata = row.get("metadata")
            session.add(
                CapabilityModel(
                    key=row["key"],
                    category=row["category"],
                    available=row["available"],
                    reason=row.get("reason"),
                    checked_at=checked_at,
                    metadata_json=json.dumps(metadata) if metadata else None,
                )
            )
        session.commit()
    return checked_at


def load_capabilities() -> tuple[datetime | None, list[CapabilityModel]]:
    with get_session() as session:
        rows = list(session.scalars(select(CapabilityModel).order_by(CapabilityModel.key)).all())
        if not rows:
            return None, []
        return rows[0].checked_at, rows
