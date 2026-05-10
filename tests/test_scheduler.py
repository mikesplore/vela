from datetime import datetime, timezone

import pytest
from auth import create_access_token
from routers import scheduler as scheduler_module


class FakeJob:
    def __init__(self, job_id, kwargs, next_run_time, trigger):
        self.id = job_id
        self.kwargs = kwargs
        self.next_run_time = next_run_time
        self.trigger = trigger


@pytest.mark.anyio
async def test_scheduler_create_list_cancel_and_run(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    fake_job = FakeJob(
        job_id="job-1",
        kwargs={"command": "echo", "args": ["hello"], "recurring": None},
        next_run_time=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        trigger="date",
    )

    def fake_add_job(func, **kwargs):
        return fake_job

    def fake_get_jobs():
        return [fake_job]

    def fake_get_job(job_id):
        return fake_job if job_id == "job-1" else None

    monkeypatch.setattr(scheduler_module.scheduler, "add_job", fake_add_job)
    monkeypatch.setattr(scheduler_module.scheduler, "get_jobs", fake_get_jobs)
    monkeypatch.setattr(scheduler_module.scheduler, "get_job", fake_get_job)
    monkeypatch.setattr(scheduler_module.scheduler, "remove_job", lambda job_id: None)

    create_response = await async_client.post(
        "/scheduler/create",
        json={
            "command": "echo",
            "args": ["hello"],
            "run_at": "2026-05-10T12:00:00Z",
            "recurring": None,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["message"] == "Scheduled job job-1"

    list_response = await async_client.get(
        "/scheduler/list",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["jobs"][0]["id"] == "job-1"

    cancel_response = await async_client.delete(
        "/scheduler/cancel/job-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["success"] is True

    run_response = await async_client.post(
        "/scheduler/run-now/job-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_response.status_code == 200
    assert "Triggered task job-1 immediately" in run_response.json()["message"]
