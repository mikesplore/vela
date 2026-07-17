"""Traffic-independent cleanup for persisted Vela state."""
from __future__ import annotations

import logging

from apscheduler.triggers.interval import IntervalTrigger

from app.services.scheduler import get_scheduler
from app.utils.config import get_config

logger = logging.getLogger(__name__)


def run_maintenance() -> None:
    """Prune retained telemetry and expired approval records."""
    try:
        from app.db.pending_actions import cleanup_expired_actions
        from app.services.audit import maybe_prune

        maybe_prune()
        cleanup_expired_actions()
    except Exception:
        logger.exception("Scheduled maintenance failed")


def setup_maintenance_schedule() -> None:
    interval = max(5, get_config().maintenance_prune_interval_minutes)
    get_scheduler().add_job(
        run_maintenance,
        trigger=IntervalTrigger(minutes=interval),
        id="vela_maintenance",
        name="Vela telemetry maintenance",
        replace_existing=True,
    )
