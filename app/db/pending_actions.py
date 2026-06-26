"""Database management for pending actions."""
from __future__ import annotations

from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.models import PendingAction


class Base(DeclarativeBase):
    pass


class PendingActionModel(Base):
    """Database model for pending actions."""
    __tablename__ = "pending_actions"

    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(index=True)
    session_id: Mapped[str] = mapped_column(index=True)
    user_message: Mapped[str]
    tool_calls: Mapped[str]  # JSON string
    prompt: Mapped[str]
    requires_auth: Mapped[bool]
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    pin_attempts: Mapped[int] = mapped_column(default=0)

    @classmethod
    def from_pending_action(cls, pending: PendingAction) -> PendingActionModel:
        """Create a database model from a PendingAction dataclass."""
        import json
        return cls(
            id=pending.action_id,
            user_id=pending.user_id,
            session_id=pending.session_id,
            user_message=pending.user_message,
            tool_calls=json.dumps(pending.tool_calls),
            prompt=pending.prompt,
            requires_auth=pending.requires_auth,
            created_at=pending.created_at,
            expires_at=pending.expires_at,
            pin_attempts=pending.pin_attempts,
        )

    def to_pending_action(self) -> PendingAction:
        """Convert database model to PendingAction dataclass."""
        import json
        return PendingAction(
            action_id=self.id,
            user_id=self.user_id,
            session_id=self.session_id,
            user_message=self.user_message,
            tool_calls=json.loads(self.tool_calls),
            prompt=self.prompt,
            requires_auth=self.requires_auth,
            created_at=self.created_at,
            expires_at=self.expires_at,
            pin_attempts=self.pin_attempts,
        )


# Initialize database
db_path = Path.cwd() / "pending_actions.sqlite"
engine = create_engine(f"sqlite:///{db_path}", echo=False)


def init_db():
    """Create database tables if they don't exist."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Get a database session."""
    return Session(engine)


# Database operations
def save_pending_action(pending: PendingAction) -> None:
    """Save or update a pending action in the database."""
    with get_session() as session:
        model = PendingActionModel.from_pending_action(pending)
        session.merge(model)
        session.commit()


def get_pending_action_from_db(user_id: str, session_id: str) -> PendingAction | None:
    """Get a pending action from the database."""
    key = f"{user_id}|{session_id}"
    with get_session() as session:
        stmt = select(PendingActionModel).where(
            PendingActionModel.user_id == user_id,
            PendingActionModel.session_id == session_id,
        )
        result = session.execute(stmt).scalar_one_or_none()
        if not result:
            return None
        
        # Check if expired (handle both naive and aware datetimes)
        expires_at = result.expires_at
        if expires_at.tzinfo is None:
            # If stored as naive, assume UTC
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            delete_pending_action(user_id, session_id)
            return None
        
        return result.to_pending_action()


def delete_pending_action(user_id: str, session_id: str) -> None:
    """Delete a pending action from the database."""
    with get_session() as session:
        stmt = delete(PendingActionModel).where(
            PendingActionModel.user_id == user_id,
            PendingActionModel.session_id == session_id,
        )
        session.execute(stmt)
        session.commit()


def cleanup_expired_actions() -> int:
    """Remove all expired pending actions from the database.
    
    Returns:
        Number of expired actions removed.
    """
    now = datetime.now(UTC)
    with get_session() as session:
        stmt = delete(PendingActionModel).where(
            PendingActionModel.expires_at <= now
        )
        result = session.execute(stmt)
        session.commit()
        return result.rowcount