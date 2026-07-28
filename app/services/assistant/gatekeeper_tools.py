"""Assistant tools that proxy to Gatekeeperd's admin API."""
from __future__ import annotations

from typing import Any

GATEKEEPER_SERVICE = "gatekeeper"

GATEKEEPER_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "gatekeeper_list_projects": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/projects",
        "description": (
            "List all Gatekeeper client projects (slug, name, domain, status, due date, amount due). "
            "Use for billing/access overview across hosted clients."
        ),
    },
    "gatekeeper_get_project": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/projects/{slug}",
        "description": (
            "Get one Gatekeeper project with payment history and audit log. "
            "Use when the user asks about a specific client site or slug."
        ),
        "input": {"slug": "string"},
    },
    "gatekeeper_list_overdue": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/projects/overdue",
        "description": (
            "List active Gatekeeper projects past their due date, sorted by days overdue. "
            "Use for payment triage — who is late and when auto-block kicks in."
        ),
    },
    "gatekeeper_list_payments": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/payments",
        "query_input": True,
        "description": (
            "List payments across all Gatekeeper projects with optional filters: "
            "status (pending/success/failed/abandoned/reversed), project_slug, from/to dates, limit, offset."
        ),
        "input": {
            "status": "string?",
            "project_slug": "string?",
            "from": "string? (YYYY-MM-DD)",
            "to": "string? (YYYY-MM-DD)",
            "limit": "integer?",
            "offset": "integer?",
        },
    },
    "gatekeeper_revenue_report": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/revenue",
        "query_input": True,
        "description": (
            "Gatekeeper revenue summary: total this month, last month, and monthly breakdown. "
            "Optional input: months (default 6)."
        ),
        "input": {"months": "integer?"},
    },
    "gatekeeper_list_audit": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/audit",
        "query_input": True,
        "description": "Recent Gatekeeper audit log entries across all projects (block/unblock/payments).",
        "input": {"limit": "integer? (max 500)"},
    },
    "gatekeeper_list_containers": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/containers",
        "description": "List Docker containers visible to Gatekeeperd on the host.",
    },
    "gatekeeper_block_project": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/projects/{slug}/block",
        "description": (
            "Manually block a Gatekeeper client project (gates their site/API). "
            "Requires slug and a non-empty reason. Confirmation gate applies."
        ),
        "input": {"slug": "string", "reason": "string"},
    },
    "gatekeeper_unblock_project": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/projects/{slug}/unblock",
        "description": (
            "Manually unblock a Gatekeeper client project after payment or agreement. "
            "Requires slug and a non-empty reason. Confirmation gate applies."
        ),
        "input": {"slug": "string", "reason": "string"},
    },
}

GATEKEEPER_TOOL_DISPLAY_NAMES: dict[str, str] = {
    "gatekeeper_list_projects": "Listing Gatekeeper projects",
    "gatekeeper_get_project": "Fetching Gatekeeper project details",
    "gatekeeper_list_overdue": "Checking overdue Gatekeeper clients",
    "gatekeeper_list_payments": "Listing Gatekeeper payments",
    "gatekeeper_revenue_report": "Fetching Gatekeeper revenue report",
    "gatekeeper_list_audit": "Reading Gatekeeper audit log",
    "gatekeeper_list_containers": "Listing Gatekeeper Docker containers",
    "gatekeeper_block_project": "Blocking Gatekeeper client project",
    "gatekeeper_unblock_project": "Unblocking Gatekeeper client project",
}

GATEKEEPER_TOOL_HINTS: list[tuple[frozenset[str], str]] = [
    (
        frozenset({"gatekeeper_list_overdue"}),
        "who is overdue on Gatekeeper / late payments → gatekeeper_list_overdue",
    ),
    (
        frozenset({"gatekeeper_list_payments"}),
        "payment status / failed charges → gatekeeper_list_payments with status filter",
    ),
    (
        frozenset({"gatekeeper_revenue_report"}),
        "Gatekeeper revenue / MRR → gatekeeper_revenue_report",
    ),
    (
        frozenset({"gatekeeper_get_project"}),
        "specific client site by slug → gatekeeper_get_project",
    ),
    (
        frozenset({"gatekeeper_unblock_project"}),
        "unblock client after payment → gatekeeper_unblock_project (confirmation gate)",
    ),
]
