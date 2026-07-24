from datetime import timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services import alert_delivery, alerts, scheduler as scheduler_module
from app.services import network


class _Scheduler:
    timezone = timezone.utc

    def __init__(self):
        self.jobs = []

    def add_job(self, func, **kwargs):
        self.jobs.append((func, kwargs))


def test_monitoring_schedule_uses_timezone_and_persistent_jobs(monkeypatch):
    fake_scheduler = _Scheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake_scheduler)

    alerts.setup_monitoring_schedule(
        daily_summary_time="07:30",
        alert_timezone="Africa/Nairobi",
        spike_check_interval_minutes=5,
    )

    jobs = {kwargs["id"]: (func, kwargs) for func, kwargs in fake_scheduler.jobs}
    spike_func, spike_job = jobs["vela_spike_monitor"]
    daily_func, daily_job = jobs["vela_daily_summary"]
    assert spike_func is alerts.scheduled_spike_check
    assert daily_func is alerts.scheduled_daily_summary
    assert spike_job.get("kwargs", {}) == {}
    assert "hour='7'" in str(daily_job["trigger"])
    assert "minute='30'" in str(daily_job["trigger"])
    assert daily_job["trigger"].timezone == ZoneInfo("Africa/Nairobi")


def test_scheduled_spike_check_collects_daily_metrics(monkeypatch):
    calls = {"collected": 0}
    monkeypatch.setattr(alerts, "collect_daily_stats", lambda: calls.__setitem__("collected", calls["collected"] + 1))
    monkeypatch.setattr(alerts, "check_and_send_spike_alert", lambda **_kwargs: None)

    alerts.scheduled_spike_check()

    assert calls["collected"] == 1


def test_daily_disk_metrics_use_a_daily_baseline(monkeypatch):
    alerts._daily_stats.clear()
    monkeypatch.setattr(alerts, "get_cpu_usage", lambda: SimpleNamespace(overall=20.0))
    monkeypatch.setattr(alerts, "get_ram_status", lambda: SimpleNamespace(percent=30.0))
    monkeypatch.setattr(network, "_vnstat_run", lambda _period: {"tx_bytes": 10, "rx_bytes": 20})
    readings = iter([
        SimpleNamespace(read_bytes=100, write_bytes=200),
        SimpleNamespace(read_bytes=145, write_bytes=260),
    ])
    monkeypatch.setattr(alerts.psutil, "disk_io_counters", lambda: next(readings))

    alerts.collect_daily_stats()
    stats = alerts.collect_daily_stats()

    assert stats["disk_read_bytes"] == 45
    assert stats["disk_write_bytes"] == 60
    assert stats["cpu_readings"] == [20.0, 20.0]


def test_check_and_send_spike_alert_dispatches_disk_alert(monkeypatch):
    alerts._last_spike_alerts.clear()
    monkeypatch.setattr(alerts, "get_cpu_usage", lambda: SimpleNamespace(overall=10.0))
    monkeypatch.setattr(alerts, "get_ram_status", lambda: SimpleNamespace(percent=20.0))
    monkeypatch.setattr(alerts, "_swap_usage_percent", lambda: None)
    monkeypatch.setattr(
        alerts,
        "_disk_usage_alerts",
        lambda threshold: [{"mountpoint": "/", "percent": 91.0, "filesystem": "ext4"}],
    )
    delivered = []
    monkeypatch.setattr(
        alert_delivery,
        "deliver_spike_alert",
        lambda **kwargs: delivered.append(kwargs) or {"email": {}, "push_delivered": 1},
    )
    monkeypatch.setattr(alerts, "_alert_settings", lambda: {
        "cpu_threshold": 85.0,
        "memory_threshold": 85.0,
        "disk_threshold": 80.0,
        "cooldown_minutes": 15,
    })
    monkeypatch.setattr(alert_delivery, "email_enabled", lambda: True)
    monkeypatch.setattr(alert_delivery, "push_enabled", lambda: True)

    result = alerts.check_and_send_spike_alert()

    assert result is not None
    assert result[0]["type"] == "disk_spike:/"
    assert delivered[0]["resource"] == "Disk /"


def test_alert_delivery_respects_runtime_email_config(monkeypatch):
    monkeypatch.setenv("RECIPIENT_EMAIL", "ops@example.com")
    monkeypatch.setattr(alert_delivery.emails, "is_configured", lambda: True)
    assert alert_delivery.recipient_email() == "ops@example.com"
    assert alert_delivery.email_enabled() is True


def test_get_monitoring_status_tolerates_jobs_without_next_run_time(monkeypatch):
    class _Job:
        id = "vela_spike_monitor"
        trigger = "interval[0:05:00]"

    monkeypatch.setattr(alerts, "get_monitoring_status", alerts.get_monitoring_status)
    from app.services import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: SimpleNamespace(get_jobs=lambda: [_Job()], running=True))
    monkeypatch.setattr("app.services.network._is_vnstat_available", lambda: False)

    status = alerts.get_monitoring_status()
    assert status["spike_monitor"] == {"next_run": None}
