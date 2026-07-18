from datetime import timezone
from types import SimpleNamespace

from app.services import alerts, scheduler as scheduler_module
from app.services import network


class _Scheduler:
    timezone = timezone.utc

    def __init__(self):
        self.jobs = []

    def add_job(self, func, **kwargs):
        self.jobs.append((func, kwargs))


def test_monitoring_schedule_uses_module_level_persistent_jobs(monkeypatch):
    fake_scheduler = _Scheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake_scheduler)

    alerts.setup_monitoring_schedule(daily_summary_time="07:30")

    jobs = {kwargs["id"]: (func, kwargs) for func, kwargs in fake_scheduler.jobs}
    spike_func, spike_job = jobs["vela_spike_monitor"]
    daily_func, daily_job = jobs["vela_daily_summary"]
    assert spike_func is alerts.scheduled_spike_check
    assert daily_func is alerts.scheduled_daily_summary
    assert spike_job["kwargs"] == {
        "cpu_threshold": alerts.DEFAULT_CPU_THRESHOLD,
        "memory_threshold": alerts.DEFAULT_MEMORY_THRESHOLD,
    }
    assert "hour='7'" in str(daily_job["trigger"])
    assert "minute='30'" in str(daily_job["trigger"])


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
