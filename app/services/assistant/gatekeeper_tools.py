"""Assistant tools that proxy to Gatekeeperd's admin API."""
from __future__ import annotations

from typing import Any

GATEKEEPER_SERVICE = "gatekeeper"

GATEKEEPER_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    # Project Management
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
    "gatekeeper_create_project": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/projects",
        "description": (
            "Create a new Gatekeeper project registration. "
            "PREREQUISITE: Docker container must already exist and be running (use gatekeeper_create_container first). "
            "DEPLOYMENT ORDER: This is step 2 of 4. "
            "1) gatekeeper_check_image_status → gatekeeper_create_container → ensure running "
            "2) gatekeeper_create_project (this step) "
            "3) gatekeeper_nginx_wizard_context → gatekeeper_nginx_enable "
            "4) gatekeeper_install_certificate. "
            "Use for onboarding new clients."
        ),
        "input": {
            "slug": "string",
            "name": "string",
            "domain": "string",
            "containerName": "string",
            "type": "string (frontend|backend)",
            "clientName": "string",
            "clientEmail": "string",
            "amountDue": "number",
            "currency": "string",
            "dueDate": "string (YYYY-MM-DD)",
            "gracePeriodDays": "integer?"
        },
    },
    "gatekeeper_update_project": {
        "service": GATEKEEPER_SERVICE,
        "method": "PATCH",
        "path": "/api/admin/projects/{slug}",
        "description": (
            "Update Gatekeeper project fields for an existing client project. "
            "PATCH semantics: provide slug to target the project plus ONLY the fields the user "
            "asked to change — every body field is optional but at least one is required. "
            "Editable fields: name, domain, containerName, type (frontend|backend), "
            "clientName, clientEmail, amountDue (number), currency (e.g. KES/USD), "
            "dueDate (YYYY-MM-DD, or null to clear), gracePeriodDays (integer). "
            "Do NOT send fields the user did not ask to change."
        ),
        "input": {
            "slug": "string (required — path parameter)",
            "name": "string?",
            "domain": "string?",
            "containerName": "string?",
            "type": "string? (frontend|backend)",
            "clientName": "string?",
            "clientEmail": "string?",
            "amountDue": "number?",
            "currency": "string? (e.g. KES, USD)",
            "dueDate": "string? (YYYY-MM-DD, or null to clear)",
            "gracePeriodDays": "integer?",
        },
        "body_input": True,
    },
    "gatekeeper_delete_project": {
        "service": GATEKEEPER_SERVICE,
        "method": "DELETE",
        "path": "/api/admin/projects/{slug}",
        "description": (
            "Archive a Gatekeeper project (soft delete). Preserves payments and audit log. "
            "Use when removing a client while keeping historical data."
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
            "Optional input: period (default month), months (default 6)."
        ),
        "input": {
            "period": "string? (month)",
            "months": "integer?"
        },
    },
    "gatekeeper_list_audit": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/audit",
        "query_input": True,
        "description": "Recent Gatekeeper audit log entries across all projects (block/unblock/payments).",
        "input": {"limit": "integer? (max 500)"},
    },
    "gatekeeper_get_project_audit": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/projects/{slug}/audit",
        "description": "Get audit log for a specific project.",
        "input": {"slug": "string"},
    },
    "gatekeeper_initialize_payment": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/projects/{slug}/payment/initialize",
        "description": (
            "Generate a Paystack payment link for a project. "
            "Requires slug and email. Creates a pending payment and returns a checkout URL."
        ),
        "input": {"slug": "string", "email": "string"},
    },
    # Block/Unblock
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
    # Nginx Management
    "gatekeeper_nginx_wizard_context": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/nginx/wizard/context/{slug}",
        "description": (
            "Wizard helper: fetch project + nginx context to drive a step-by-step UI "
            "(status, container hints, certificate options)."
        ),
        "input": {"slug": "string"},
    },
    "gatekeeper_nginx_validate": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/nginx/wizard/validate/{slug}",
        "description": (
            "Wizard helper: validate nginx enable inputs and return a config preview without applying changes."
        ),
        "input": {"slug": "string"},
        "body_input": True,
    },
    "gatekeeper_nginx_status": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/nginx/status/{slug}",
        "description": "Check if a project has an nginx site configured and enabled, and whether SSL is set up.",
        "input": {"slug": "string"},
    },
    "gatekeeper_nginx_enable": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/nginx/enable/{slug}",
        "description": (
            "Generate and enable an nginx site config for a project. "
            "PREREQUISITE: Project must exist and container must be running. "
            "DEPLOYMENT ORDER: This is step 3 of 4. "
            "Use gatekeeper_nginx_wizard_context first to fetch project details and validate. "
            "After enabling, proceed to gatekeeper_install_certificate for SSL."
        ),
        "input": {"slug": "string"},
        "body_input": True,
    },
    "gatekeeper_nginx_disable": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/nginx/disable/{slug}",
        "description": "Disable (unlink) an nginx site without removing the config file.",
        "input": {"slug": "string"},
    },
    "gatekeeper_nginx_remove": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/nginx/remove/{slug}",
        "description": "Remove an nginx site completely (both sites-available file and sites-enabled symlink).",
        "input": {"slug": "string"},
    },
    # SSL Certificate Management
    "gatekeeper_list_certificates": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/nginx/certificate/list",
        "description": "List installed SSL certificates found under /etc/letsencrypt/live.",
    },
    "gatekeeper_install_certificate": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/nginx/certificate/install",
        "description": (
            "Install an SSL certificate for a domain using certbot. "
            "DEPLOYMENT ORDER: This is step 4 of 4 — do this last. "
            "PREREQUISITE: nginx site must be enabled (use gatekeeper_nginx_enable first). "
            "Requires domain and email. This completes the deployment."
        ),
        "input": {"domain": "string", "email": "string"},
    },
    "gatekeeper_remove_certificate": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/nginx/certificate/remove/{domain}",
        "description": "Remove an SSL certificate for a domain.",
        "input": {"domain": "string"},
    },
    "gatekeeper_check_certificate_status": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/nginx/certificate/status/{domain}",
        "description": "Check whether an SSL certificate is installed for a domain.",
        "input": {"domain": "string"},
    },
    # Docker Container Management
    "gatekeeper_check_image_status": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/images/status",
        "description": "Wizard helper: check whether an image is available locally before attempting container creation.",
        "input": {"image": "string"},
    },
    "gatekeeper_create_container": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/containers/create",
        "description": (
            "Create and start a new Docker container with custom configuration. "
            "DEPLOYMENT ORDER: This is step 1 of 4 — do this first. "
            "Requires image. Optional: name, projectSlug, ports, env, network, volumes, restartPolicy. "
            "If the user provides .env variables, pass them in the env field. "
            "If the user says the env vars are already in a local .env file on the Docker host, prefer passing "
            "envFilePath (absolute path) so Gatekeeperd can load it server-side. "
            "After creation, verify the container is running before proceeding to project creation."
        ),
        "input": {
            "image": "string",
            "name": "string?",
            "projectSlug": "string?",
            "ports": (
                "array? (examples: [9921] for host=container same port, "
                "or [{\"host\":9921,\"container\":9921,\"protocol\":\"tcp\"}])"
            ),
            "env": "object? (key/value map of env vars)",
            "envFilePath": "string? (absolute path to .env on host)",
            "network": "string? (docker network name)",
            "volumes": "array? (binds/volumes; Gatekeeperd-specific shape)",
            "restartPolicy": "string? (e.g. always|unless-stopped|no)",
        },
        "body_input": True,
    },
    "gatekeeper_containers_wizard_context": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/containers/wizard/context",
        "description": "Wizard helper: fetch Docker container-creation context (networks + internal network info).",
    },
    "gatekeeper_containers_wizard_ports_check": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/containers/wizard/ports/check",
        "description": "Wizard helper: check whether host ports are already in use on the Docker host.",
        "input": {"hostPorts": "array of integers"},
    },
    "gatekeeper_containers_wizard_validate": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/containers/wizard/validate",
        "description": "Wizard helper: validate and normalize a CreateContainerRequest without applying changes.",
        "body_input": True,
    },
    "gatekeeper_list_containers": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/containers",
        "description": "List all Docker containers visible to Gatekeeperd on the host.",
    },
    "gatekeeper_get_container": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/containers/{name}",
        "description": "Get details for a single container by name or ID prefix.",
        "input": {"name": "string"},
    },
    "gatekeeper_start_container": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/containers/{name}/start",
        "description": "Start a stopped container.",
        "input": {"name": "string"},
    },
    "gatekeeper_stop_container": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/containers/{name}/stop",
        "description": "Stop a running container.",
        "input": {"name": "string"},
    },
    "gatekeeper_restart_container": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/containers/{name}/restart",
        "description": "Restart a container.",
        "input": {"name": "string"},
    },
    "gatekeeper_delete_container": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/containers/{name}/delete",
        "description": "Delete a container permanently.",
        "input": {"name": "string"},
    },
    "gatekeeper_get_container_health": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/containers/{name}/health",
        "description": "Get container health/running state.",
        "input": {"name": "string"},
    },
    "gatekeeper_list_networks": {
        "service": GATEKEEPER_SERVICE,
        "method": "GET",
        "path": "/api/admin/networks",
        "description": "List Docker networks.",
    },
    "gatekeeper_pull_image": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/images/pull",
        "description": "Pull a Docker image from a registry.",
        "input": {"image": "string", "tag": "string?", "pullViaCli": "boolean?"},
    },
    "gatekeeper_delete_image": {
        "service": GATEKEEPER_SERVICE,
        "method": "POST",
        "path": "/api/admin/images/delete",
        "description": "Delete a Docker image from the local Docker host.",
        "input": {"image": "string", "tag": "string?", "force": "boolean?"},
    },
}

GATEKEEPER_TOOL_DISPLAY_NAMES: dict[str, str] = {
    # Project Management
    "gatekeeper_list_projects": "Listing Gatekeeper projects",
    "gatekeeper_get_project": "Fetching Gatekeeper project details",
    "gatekeeper_create_project": "Creating Gatekeeper project",
    "gatekeeper_update_project": "Updating Gatekeeper project",
    "gatekeeper_delete_project": "Archiving Gatekeeper project",
    "gatekeeper_list_overdue": "Checking overdue Gatekeeper clients",
    "gatekeeper_list_payments": "Listing Gatekeeper payments",
    "gatekeeper_revenue_report": "Fetching Gatekeeper revenue report",
    "gatekeeper_list_audit": "Reading Gatekeeper audit log",
    "gatekeeper_get_project_audit": "Reading project audit log",
    "gatekeeper_initialize_payment": "Initializing payment for project",
    # Block/Unblock
    "gatekeeper_block_project": "Blocking Gatekeeper client project",
    "gatekeeper_unblock_project": "Unblocking Gatekeeper client project",
    # Nginx Management
    "gatekeeper_nginx_wizard_context": "Fetching nginx wizard context",
    "gatekeeper_nginx_validate": "Validating nginx configuration",
    "gatekeeper_nginx_status": "Checking nginx status",
    "gatekeeper_nginx_enable": "Enabling nginx site",
    "gatekeeper_nginx_disable": "Disabling nginx site",
    "gatekeeper_nginx_remove": "Removing nginx site",
    # SSL Certificates
    "gatekeeper_list_certificates": "Listing SSL certificates",
    "gatekeeper_install_certificate": "Installing SSL certificate",
    "gatekeeper_remove_certificate": "Removing SSL certificate",
    "gatekeeper_check_certificate_status": "Checking SSL certificate status",
    # Docker Management
    "gatekeeper_check_image_status": "Checking Docker image status",
    "gatekeeper_create_container": "Creating Docker container",
    "gatekeeper_containers_wizard_context": "Fetching container wizard context",
    "gatekeeper_containers_wizard_ports_check": "Checking port availability",
    "gatekeeper_containers_wizard_validate": "Validating container creation request",
    "gatekeeper_list_containers": "Listing Gatekeeper Docker containers",
    "gatekeeper_get_container": "Fetching container details",
    "gatekeeper_start_container": "Starting container",
    "gatekeeper_stop_container": "Stopping container",
    "gatekeeper_restart_container": "Restarting container",
    "gatekeeper_delete_container": "Deleting container",
    "gatekeeper_get_container_health": "Checking container health",
    "gatekeeper_list_networks": "Listing Docker networks",
    "gatekeeper_pull_image": "Pulling Docker image",
    "gatekeeper_delete_image": "Deleting Docker image",
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
    (
        frozenset({"gatekeeper_block_project"}),
        "manually block a client → gatekeeper_block_project (confirmation gate)",
    ),
    (
        frozenset({"gatekeeper_create_project"}),
        "onboard new client → gatekeeper_create_project (container must exist)",
    ),
    (
        frozenset({"gatekeeper_delete_project"}),
        "remove/archive client → gatekeeper_delete_project (preserves history)",
    ),
    (
        frozenset({"gatekeeper_initialize_payment"}),
        "generate payment link → gatekeeper_initialize_payment",
    ),
    (
        frozenset({"gatekeeper_list_containers", "gatekeeper_get_container", "gatekeeper_start_container", 
                    "gatekeeper_stop_container", "gatekeeper_restart_container", "gatekeeper_delete_container",
                    "gatekeeper_get_container_health"}),
        "Docker container management → gatekeeper_list_containers / gatekeeper_get_container / etc.",
    ),
    (
        frozenset({"gatekeeper_nginx_enable", "gatekeeper_nginx_disable", "gatekeeper_remove", 
                    "gatekeeper_nginx_status"}),
        "nginx site management → gatekeeper_nginx_enable / gatekeeper_nginx_status / etc.",
    ),
    (
        frozenset({"gatekeeper_install_certificate", "gatekeeper_list_certificates", 
                    "gatekeeper_check_certificate_status"}),
        "SSL certificate management → gatekeeper_install_certificate / gatekeeper_list_certificates",
    ),
    # ── Deployment workflow hint ──
    (
        frozenset({
            "gatekeeper_check_image_status",
            "gatekeeper_create_container",
            "gatekeeper_create_project",
            "gatekeeper_nginx_enable",
            "gatekeeper_install_certificate",
        }),
        "deploy a new client app → full deployment workflow in order: "
        "1) gatekeeper_check_image_status → 2) gatekeeper_create_container (with .env if provided) → "
        "3) gatekeeper_create_project → 4) gatekeeper_nginx_wizard_context → gatekeeper_nginx_enable → "
        "5) gatekeeper_install_certificate. Ask user for any missing prerequisites (image, domain, email, envFilePath).",
    ),
]
