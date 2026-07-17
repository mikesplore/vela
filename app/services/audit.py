"""Audit / metrics query and aggregation helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any

from sqlalchemy import func, select

from app.db.audit_log import (
    AuditEventModel,
    ToolCallEventModel,
    get_audit_session,
    prune_audit_events,
)
from app.utils.config import get_config


# Paths that poll frequently and would skew latency charts.
SKIP_PATH_PREFIXES = (
    "/health",
    "/ping",
    "/admin/",
)
MAX_LOOKBACK_MINUTES = 60 * 24 * 90


def should_audit_path(path: str) -> bool:
    if path in {"/health", "/ping", "/"}:
        return False
    return not any(path.startswith(prefix) for prefix in SKIP_PATH_PREFIXES)


def maybe_prune() -> None:
    cfg = get_config()
    now = datetime.now(UTC)
    audit_older_than = now - timedelta(days=max(1, cfg.audit_retention_days))
    relay_older_than = now - timedelta(days=max(1, cfg.relay_audit_retention_days))
    admin_action_older_than = now - timedelta(days=max(1, cfg.admin_action_retention_days))
    prune_audit_events(
        older_than=audit_older_than,
        relay_older_than=relay_older_than,
        admin_action_older_than=admin_action_older_than,
        keep_max=cfg.audit_max_rows,
        relay_keep_max=cfg.relay_audit_max_rows,
    )


def list_events(
    *,
    limit: int = 100,
    offset: int = 0,
    path_contains: str | None = None,
    status_min: int | None = None,
    since_minutes: int | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    with get_audit_session() as session:
        stmt = select(AuditEventModel).order_by(
            AuditEventModel.created_at.desc(),
            AuditEventModel.id.desc(),
        )
        if path_contains:
            stmt = stmt.where(AuditEventModel.path.contains(path_contains))
        if status_min is not None:
            stmt = stmt.where(AuditEventModel.status_code >= status_min)
        if since_minutes is not None and since_minutes > 0:
            since = datetime.now(UTC) - timedelta(minutes=since_minutes)
            stmt = stmt.where(AuditEventModel.created_at >= since)
        rows = session.scalars(stmt.offset(offset).limit(limit)).all()
        return [_row_to_dict(row) for row in rows]


def summary(*, since_minutes: int = 60) -> dict[str, Any]:
    since_minutes = max(1, min(since_minutes, MAX_LOOKBACK_MINUTES))
    since = datetime.now(UTC) - timedelta(minutes=since_minutes)

    with get_audit_session() as session:
        rows = list(
            session.scalars(
                select(AuditEventModel).where(AuditEventModel.created_at >= since)
            )
        )

    total = len(rows)
    errors = [r for r in rows if r.status_code >= 400]
    durations = [r.duration_ms for r in rows]
    by_path: dict[str, list[AuditEventModel]] = {}
    by_minute: dict[str, list[AuditEventModel]] = {}

    for row in rows:
        key = f"{row.method} {row.path}"
        by_path.setdefault(key, []).append(row)
        minute = row.created_at.astimezone(UTC).replace(second=0, microsecond=0).isoformat()
        by_minute.setdefault(minute, []).append(row)

    path_stats = []
    for key, items in by_path.items():
        durs = [i.duration_ms for i in items]
        err_count = sum(1 for i in items if i.status_code >= 400)
        path_stats.append(
            {
                "endpoint": key,
                "count": len(items),
                "errors": err_count,
                "error_rate": (err_count / len(items)) if items else 0.0,
                "median_ms": _percentile(durs, 50),
                "p95_ms": _percentile(durs, 95),
                "avg_ms": (sum(durs) / len(durs)) if durs else 0.0,
            }
        )
    path_stats.sort(key=lambda x: x["count"], reverse=True)

    timeline = []
    for minute in sorted(by_minute.keys()):
        bucket = by_minute[minute]
        durs = [i.duration_ms for i in bucket]
        timeline.append(
            {
                "minute": minute,
                "count": len(bucket),
                "errors": sum(1 for i in bucket if i.status_code >= 400),
                "median_ms": _percentile(durs, 50),
                "p95_ms": _percentile(durs, 95),
            }
        )

    return {
        "window_minutes": since_minutes,
        "total_requests": total,
        "error_count": len(errors),
        "error_rate": (len(errors) / total) if total else 0.0,
        "median_ms": _percentile(durations, 50),
        "p95_ms": _percentile(durations, 95),
        "avg_ms": (sum(durations) / len(durations)) if durations else 0.0,
        "by_endpoint": path_stats[:40],
        "timeline": timeline,
        "recent_errors": [_row_to_dict(r) for r in sorted(errors, key=lambda x: x.created_at, reverse=True)[:25]],
    }


def assistant_summary(*, since_minutes: int = 60) -> dict[str, Any]:
    since_minutes = max(1, min(since_minutes, MAX_LOOKBACK_MINUTES))
    since = datetime.now(UTC) - timedelta(minutes=since_minutes)
    with get_audit_session() as session:
        rows = list(
            session.scalars(
                select(ToolCallEventModel).where(ToolCallEventModel.created_at >= since)
            )
        )

    total = len(rows)
    failures = [row for row in rows if not row.succeeded]
    by_tool: dict[str, list[ToolCallEventModel]] = {}
    for row in rows:
        by_tool.setdefault(row.tool_name, []).append(row)

    tools = []
    for tool_name, items in by_tool.items():
        durations = [item.duration_ms for item in items]
        error_count = sum(1 for item in items if not item.succeeded)
        tools.append({
            "tool_name": tool_name,
            "count": len(items),
            "errors": error_count,
            "error_rate": error_count / len(items),
            "median_ms": _percentile(durations, 50),
            "p95_ms": _percentile(durations, 95),
        })
    tools.sort(key=lambda item: (item["errors"], item["count"]), reverse=True)

    return {
        "window_minutes": since_minutes,
        "total_tool_calls": total,
        "tool_error_count": len(failures),
        "tool_error_rate": (len(failures) / total) if total else 0.0,
        "by_tool": tools[:40],
        "recent_failures": [
            _tool_row_to_dict(row)
            for row in sorted(failures, key=lambda row: row.created_at, reverse=True)[:25]
        ],
    }


def list_tool_events(
    *,
    limit: int = 100,
    offset: int = 0,
    errors_only: bool = False,
    since_minutes: int | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    with get_audit_session() as session:
        stmt = select(ToolCallEventModel).order_by(
            ToolCallEventModel.created_at.desc(),
            ToolCallEventModel.id.desc(),
        )
        if errors_only:
            stmt = stmt.where(ToolCallEventModel.succeeded.is_(False))
        if since_minutes:
            stmt = stmt.where(
                ToolCallEventModel.created_at >= datetime.now(UTC) - timedelta(minutes=since_minutes)
            )
        rows = session.scalars(stmt.offset(max(0, offset)).limit(limit)).all()
        return [_tool_row_to_dict(row) for row in rows]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_vals = sorted(values)
    # statistics.quantiles needs n>=2; use nearest-rank for stability
    k = (pct / 100.0) * (len(sorted_vals) - 1)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def _row_to_dict(row: AuditEventModel) -> dict[str, Any]:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {
        "id": row.id,
        "request_id": row.request_id,
        "created_at": created.isoformat(),
        "method": row.method,
        "path": row.path,
        "status_code": row.status_code,
        "duration_ms": round(row.duration_ms, 2),
        "user_id": row.user_id,
        "client_ip": row.client_ip,
        "error": row.error,
    }


def _tool_row_to_dict(row: ToolCallEventModel) -> dict[str, Any]:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {
        "id": row.id,
        "request_id": row.request_id,
        "created_at": created.isoformat(),
        "tool_name": row.tool_name,
        "duration_ms": round(row.duration_ms, 2),
        "succeeded": row.succeeded,
        "user_id": row.user_id,
        "error": row.error,
    }


def count_events() -> int:
    with get_audit_session() as session:
        return int(session.scalar(select(func.count()).select_from(AuditEventModel)) or 0)


def count_tool_events() -> int:
    with get_audit_session() as session:
        return int(session.scalar(select(func.count()).select_from(ToolCallEventModel)) or 0)
