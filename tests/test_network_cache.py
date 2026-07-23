from app.services import network as network_service
from app.utils.config import get_config


def test_public_ip_is_cached(monkeypatch):
    network_service._public_ip_cache = None
    monkeypatch.setattr(get_config(), "network_public_ip_cache_seconds", 120)

    calls = {"count": 0}

    def fake_fetch() -> str:
        calls["count"] += 1
        return f"1.2.3.{calls['count']}"

    monkeypatch.setattr(network_service, "_fetch_public_ip", fake_fetch)

    assert network_service.public_ip() == "1.2.3.1"
    assert network_service.public_ip() == "1.2.3.1"
    assert calls["count"] == 1

    assert network_service.public_ip(force_refresh=True) == "1.2.3.2"
    assert calls["count"] == 2


def test_wifi_status_does_not_trigger_rescan(monkeypatch):
    network_service._wifi_scan_cache = None
    seen: dict[str, bool] = {}

    def fake_run_command(cmd, timeout=10):
        if cmd[:4] == ["nmcli", "device", "wifi", "rescan"]:
            seen["rescan"] = True
            return "", "", 0
        if cmd[:8] == ["nmcli", "--terse", "--escape", "no", "-f", "ACTIVE,SSID,SECURITY,SIGNAL", "device", "wifi"]:
            return "yes:MyWifi:WPA2:70", "", 0
        if cmd[:8] == ["nmcli", "--terse", "--escape", "no", "-f", "DEVICE,TYPE,STATE", "device", "status"]:
            return "wlan0:wifi:connected", "", 0
        return "", "", 1

    monkeypatch.setattr(network_service, "run_command", fake_run_command)

    status = network_service.build_wifi_status(rescan=False)

    assert "rescan" not in seen
    assert status.connected is True
    assert status.ssid == "MyWifi"


def test_wifi_list_scan_is_cached(monkeypatch):
    network_service._wifi_scan_cache = None
    monkeypatch.setattr(get_config(), "network_wifi_list_cache_seconds", 60)
    calls = {"rescan": 0, "list": 0}

    def fake_run_command(cmd, timeout=10):
        if cmd[:4] == ["nmcli", "device", "wifi", "rescan"]:
            calls["rescan"] += 1
            return "", "", 0
        if cmd[:8] == ["nmcli", "--terse", "--escape", "no", "-f", "ACTIVE,SSID,SECURITY,SIGNAL", "device", "wifi"]:
            calls["list"] += 1
            return "yes:MyWifi:WPA2:70", "", 0
        if cmd[:8] == ["nmcli", "--terse", "--escape", "no", "-f", "DEVICE,TYPE,STATE", "device", "status"]:
            return "wlan0:wifi:connected", "", 0
        return "", "", 1

    monkeypatch.setattr(network_service, "run_command", fake_run_command)

    network_service.build_wifi_status(rescan=True)
    network_service.build_wifi_status(rescan=True)

    assert calls["rescan"] == 1
    assert calls["list"] == 1
