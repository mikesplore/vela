from app.utils import emails


class _FakeEmails:
    payload: dict | None = None

    @classmethod
    def send(cls, payload):
        cls.payload = payload
        return {"id": "email_123"}


class _FakeResend:
    Emails = _FakeEmails


def test_spike_alert_uses_dashboard_theme_and_escapes_content(monkeypatch):
    monkeypatch.setattr(emails, "is_configured", lambda: True)
    monkeypatch.setattr(emails, "resend", _FakeResend)

    emails.send_spike_alert(
        to="ops@example.com",
        device_name="<server>",
        cpu_percent=96.2,
        memory_percent=88.0,
        cpu_threshold=80,
        memory_threshold=85,
        top_process="<script>alert(1)</script>",
        uptime="2 days",
        os_info="Linux",
    )

    payload = _FakeEmails.payload
    assert payload is not None
    assert payload["subject"].startswith("Vela alert")
    assert "#F3F6FC" in payload["html"]
    assert "#171C26" in payload["html"]
    assert "Resource spike detected" in payload["html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in payload["html"]
    assert "<script>" not in payload["html"]


def test_daily_summary_renders_metrics_and_processes(monkeypatch):
    monkeypatch.setattr(emails, "is_configured", lambda: True)
    monkeypatch.setattr(emails, "resend", _FakeResend)

    emails.send_daily_summary(
        to="ops@example.com",
        device_name="Vela host",
        cpu_avg=12.0,
        cpu_peak=64.5,
        memory_avg=34.0,
        memory_peak=70.0,
        disk_read="1 GB",
        disk_write="2 GB",
        net_sent="3 GB",
        net_recv="4 GB",
        uptime="3 days",
        os_info="Linux",
        top_processes=[{"name": "python", "cpu": 19.4}],
        alerts_count=1,
        last_alert_time="12:30",
    )

    payload = _FakeEmails.payload
    assert payload is not None
    assert "Vela Operations" in payload["html"]
    assert "CPU average" in payload["html"]
    assert "python · 19.4%" in payload["html"]
