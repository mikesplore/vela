from datetime import datetime, UTC

import pytest
from app.auth import create_access_token
from app.db import audit_log
from app.services import audit as audit_service
from app.services.assistant import tool_exec


def _auth_headers() -> dict[str, str]:
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _isolated_audit_db(tmp_path, monkeypatch):
    db_file = tmp_path / "audit_test.sqlite"
    monkeypatch.setattr(audit_log, "db_path", db_file)
    monkeypatch.setattr(
        audit_log,
        "engine",
        audit_log.create_engine(
            f"sqlite:///{db_file}",
            echo=False,
            connect_args={"check_same_thread": False},
        ),
    )
    audit_log.init_audit_db()
    yield


def test_should_skip_health_and_admin_paths():
    assert audit_service.should_audit_path("/health") is False
    assert audit_service.should_audit_path("/ping") is False
    assert audit_service.should_audit_path("/admin/summary") is False
    assert audit_service.should_audit_path("/network/location") is True


def test_summary_aggregates_endpoints():
    now = datetime.now(UTC)
    for i, (path, status, ms) in enumerate(
        [
            ("/network/location", 200, 40.0),
            ("/network/location", 200, 60.0),
            ("/network/location", 500, 120.0),
            ("/fs/list", 200, 10.0),
        ]
    ):
        audit_log.insert_audit_event(
            request_id=f"r{i}",
            method="GET",
            path=path,
            status_code=status,
            duration_ms=ms,
            created_at=now,
        )

    summary = audit_service.summary(since_minutes=60)
    assert summary["total_requests"] == 4
    assert summary["error_count"] == 1
    assert summary["error_rate"] == 0.25
    endpoints = {row["endpoint"]: row for row in summary["by_endpoint"]}
    assert endpoints["GET /network/location"]["count"] == 3
    assert endpoints["GET /network/location"]["errors"] == 1
    assert summary["median_ms"] > 0


@pytest.mark.anyio
async def test_audited_tool_execution_persists_failure(monkeypatch):
    async def failing_tool(*_args, **_kwargs):
        return {"tool": "get_network_location", "result": {}, "error": "lookup timed out"}

    monkeypatch.setattr(tool_exec, "execute_tool_safe", failing_tool)
    result = await tool_exec.execute_tool_audited(
        app=None,  # The test double does not use the FastAPI instance.
        tool_name="get_network_location",
        tool_input={},
        auth_header=None,
        request_id="tool-request",
        user_id="admin",
    )

    assert result["error"] == "lookup timed out"
    summary = audit_service.assistant_summary(since_minutes=60)
    assert summary["total_tool_calls"] == 1
    assert summary["tool_error_count"] == 1
    assert summary["by_tool"][0]["tool_name"] == "get_network_location"
    assert summary["recent_failures"][0]["error"] == "lookup timed out"


@pytest.mark.anyio
async def test_admin_summary_requires_auth(async_client):
    response = await async_client.get("/admin/summary")
    assert response.status_code in {401, 403}


@pytest.mark.anyio
async def test_admin_summary_and_events(async_client):
    audit_log.insert_audit_event(
        request_id="abc",
        method="GET",
        path="/system/info",
        status_code=200,
        duration_ms=12.5,
        user_id="admin",
    )
    headers = _auth_headers()
    summary = await async_client.get("/admin/summary?since_minutes=60", headers=headers)
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_requests"] >= 1

    events = await async_client.get("/admin/events?limit=10", headers=headers)
    assert events.status_code == 200
    body = events.json()
    assert body["total_stored"] >= 1
    assert any(e["path"] == "/system/info" for e in body["events"])


@pytest.mark.anyio
async def test_admin_assistant_audit_endpoints(async_client):
    audit_log.insert_tool_call_event(
        request_id="assistant-abc",
        tool_name="get_network_location",
        duration_ms=456.0,
        succeeded=False,
        user_id="admin",
        error="lookup timed out",
    )
    headers = _auth_headers()
    summary = await async_client.get("/admin/assistant/summary?since_minutes=60", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["tool_error_count"] == 1

    events = await async_client.get("/admin/assistant/events?errors_only=true", headers=headers)
    assert events.status_code == 200
    assert events.json()["events"][0]["tool_name"] == "get_network_location"


@pytest.mark.anyio
async def test_admin_dashboard_html(async_client):
    response = await async_client.get("/admin/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Chart.js" in response.text or "chart.js" in response.text
