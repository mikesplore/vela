import pytest
from auth import create_access_token
from routers import network as network_module


@pytest.mark.anyio
async def test_network_ip_and_speedtest(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(network_module, "_local_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(network_module, "_public_ip", lambda: "1.2.3.4")
    monkeypatch.setattr(network_module, "_run_command", lambda cmd, timeout=10: ("Ping: 15.0 ms\nDownload: 100.00 Mbit/s\nUpload: 20.00 Mbit/s", "", 0) if "speedtest-cli" in cmd else ("", "", 1))

    ip_response = await async_client.get(
        "/network/ip",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ip_response.status_code == 200
    assert ip_response.json()["local_ip"] == "192.168.1.10"
    assert ip_response.json()["public_ip"] == "1.2.3.4"

    speed_response = await async_client.get(
        "/network/speed-test",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert speed_response.status_code == 200
    assert speed_response.json()["download_mbps"] == 100.0
    assert speed_response.json()["upload_mbps"] == 20.0


@pytest.mark.anyio
async def test_network_wifi_bluetooth_and_ping(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        if cmd[:5] == ["nmcli", "-t", "-f", "ACTIVE,SSID,SECURITY,SIGNAL", "device"]:
            return "yes:MyWifi:WPA2:70\nno:Other:WPA3:30", "", 0
        if cmd[:5] == ["nmcli", "device", "wifi", "connect", "MyWifi"]:
            return "Device 'MyWifi' successfully activated", "", 0
        if cmd[:4] == ["nmcli", "radio", "wifi", "off"]:
            return "Wi-Fi disabled", "", 0
        if cmd[:3] == ["nmcli", "radio", "wifi"]:
            return "Wi-Fi enabled" if cmd[-1] == "on" else "Wi-Fi disabled", "", 0
        if cmd[:2] == ["rfkill", "unblock"]:
            return "", "", 0
        if cmd[:2] == ["rfkill", "block"]:
            return "", "", 0
        if cmd[:2] == ["bluetoothctl", "devices"]:
            return "Device AA:BB:CC:DD:EE:FF Test Device", "", 0
        if cmd[:2] == ["ping", "-c"]:
            return "4 packets transmitted, 4 received, 0% packet loss\nrtt min/avg/max/mdev = 10.0/15.0/20.0/1.0 ms", "", 0
        return "", "", 0

    monkeypatch.setattr(network_module, "_run_command", fake_run_command)
    monkeypatch.setattr(network_module, "_local_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(network_module, "_public_ip", lambda: "1.2.3.4")
    monkeypatch.setattr(network_module, "speedtest", None)

    status_response = await async_client.get(
        "/network/wifi/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["connected"] is True
    assert status_response.json()["ssid"] == "MyWifi"

    connect_response = await async_client.post(
        "/network/wifi/connect",
        json={"ssid": "MyWifi", "password": "pass"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert connect_response.status_code == 200

    disconnect_response = await async_client.post(
        "/network/wifi/disconnect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disconnect_response.status_code == 200

    toggle_response = await async_client.post(
        "/network/wifi/toggle",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert toggle_response.status_code == 200

    bt_response = await async_client.get(
        "/network/bluetooth/devices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bt_response.status_code == 200
    assert bt_response.json()["devices"][0]["name"] == "Test Device"

    ping_response = await async_client.post(
        "/network/ping",
        json={"host": "8.8.8.8", "count": 4},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ping_response.status_code == 200
    assert ping_response.json()["packets_received"] == 4
    assert abs(ping_response.json()["avg_rtt_ms"] - 15.0) < 0.1
