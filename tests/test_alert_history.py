from datetime import UTC, datetime

import pytest

from app.db import audit_log
from app.services import alert_delivery, alert_history


@pytest.fixture(autouse=True)
def isolated_alert_history_db(tmp_path, monkeypatch):
    db_file = tmp_path / "audit_log.sqlite"
    monkeypatch.setattr(audit_log, "db_path", db_file)
    monkeypatch.setattr(
        audit_log,
        "engine",
        audit_log.create_engine(
            f"sqlite:///{db_file}",
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 5},
        ),
    )
    audit_log.init_audit_db()
    yield


def test_record_delivery_and_list():
    alert_history.record_delivery(
        alert_kind="spike",
        title="Vela alert · CPU spike",
        body="CPU is 92.0% (threshold 85.0%).",
        email_to="ops@example.com",
        email_result={"id": "resend_123"},
        email_attempted=True,
        push_attempted=True,
        push_delivered=2,
        alert_type="cpu_spike",
        value=92.0,
        threshold=85.0,
        resource="CPU",
        metadata={"cpu_percent": 92.0},
    )

    rows = alert_history.list_deliveries(limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row["alert_kind"] == "spike"
    assert row["channel"] == "both"
    assert row["status"] == "sent"
    assert row["email_provider_id"] == "resend_123"
    assert row["push_delivered"] == 2
    assert row["metadata"]["cpu_percent"] == 92.0
    assert alert_history.count_deliveries() == 1
    assert alert_history.count_today(alert_kind="spike") == 1


def test_record_delivery_partial_when_email_fails():
    alert_history.record_delivery(
        alert_kind="spike",
        title="Vela alert · Memory spike",
        body="Memory is high.",
        email_attempted=True,
        email_error="smtp down",
        push_attempted=True,
        push_delivered=1,
    )

    row = alert_history.list_deliveries(limit=1)[0]
    assert row["status"] == "partial"
    assert "smtp down" in (row["error"] or "")


def test_deliver_spike_alert_records_history(monkeypatch):
    monkeypatch.setenv("RECIPIENT_EMAIL", "ops@example.com")
    monkeypatch.setattr(alert_delivery.emails, "is_configured", lambda: True)
    monkeypatch.setattr(alert_delivery, "push_enabled", lambda: True)
    monkeypatch.setattr(
        alert_delivery.emails,
        "send_spike_alert",
        lambda **kwargs: {"id": "email_abc"},
    )
    monkeypatch.setattr(
        "app.services.push.send_push",
        lambda **kwargs: 3,
    )

    alert_delivery.deliver_spike_alert(
        resource="CPU",
        value=91.0,
        threshold=85.0,
        cpu_percent=91.0,
        memory_percent=40.0,
        cpu_threshold=85.0,
        memory_threshold=85.0,
        top_process="chrome",
        uptime="2 days",
        os_info="Linux",
        alert_type="cpu_spike",
    )

    row = alert_history.list_deliveries(limit=1)[0]
    assert row["email_provider_id"] == "email_abc"
    assert row["push_delivered"] == 3
    assert row["metadata"]["email_subject"].startswith("Vela alert · Spike detected on")


def test_prune_removes_old_alert_history():
    old = datetime(2020, 1, 1, tzinfo=UTC)
    audit_log.insert_alert_delivery_event(
        alert_kind="spike",
        channel="email",
        status="sent",
        title="old",
        created_at=old,
    )
    alert_history.record_delivery(
        alert_kind="spike",
        title="new",
        email_attempted=True,
        email_result={"id": "x"},
    )

    deleted = audit_log.prune_audit_events(older_than=datetime(2024, 1, 1, tzinfo=UTC))
    assert deleted >= 1
    rows = alert_history.list_deliveries(limit=10)
    assert len(rows) == 1
    assert rows[0]["title"] == "new"
