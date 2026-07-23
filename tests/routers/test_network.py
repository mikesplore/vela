import pytest
from app.auth import create_access_token
from app.routers import network as network_module


@pytest.mark.anyio
async def test_network_ip_and_speedtest(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(network_module, "local_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(network_module, "p_ip", lambda: "1.2.3.4")
    monkeypatch.setattr(network_module, "run_command", lambda cmd, timeout=10: ("Ping: 15.0 ms\nDownload: 100.00 Mbit/s\nUpload: 20.00 Mbit/s", "", 0) if "speedtest-cli" in cmd else ("", "", 1))

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

    def fakerun_command(cmd, timeout=10):
        if cmd[:8] == ["nmcli", "--terse", "--escape", "no", "-f", "ACTIVE,SSID,SECURITY,SIGNAL", "device", "wifi"]:
            return "yes:MyWifi:WPA2:70\nno:Other:WPA3:30", "", 0
        if cmd[:8] == ["nmcli", "--terse", "--escape", "no", "-f", "DEVICE,TYPE,STATE", "device", "status"]:
            return "wlan0:wifi:connected", "", 0
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
        if cmd[:3] == ["bluetoothctl", "devices", "Connected"]:
            return "Device AA:BB:CC:DD:EE:FF Test Device", "", 0
        if cmd[:3] == ["bluetoothctl", "devices", "Paired"]:
            return "Device 11:22:33:44:55:66 Spare Speaker", "", 0
        if cmd[:3] == ["bluetoothctl", "pair", "AA:BB:CC:DD:EE:FF"]:
            return "Pairing successful", "", 0
        if cmd[:3] == ["bluetoothctl", "remove", "AA:BB:CC:DD:EE:FF"]:
            return "Device has been removed", "", 0
        if cmd[:2] == ["ping", "-c"]:
            return "4 packets transmitted, 4 received, 0% packet loss\nrtt min/avg/max/mdev = 10.0/15.0/20.0/1.0 ms", "", 0
        return "", "", 0

    monkeypatch.setattr(network_module, "run_command", fakerun_command)
    monkeypatch.setattr(network_module, "local_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(network_module, "p_ip", lambda: "1.2.3.4")
    monkeypatch.setattr(network_module, "geolocate_ip", lambda ip: {
        "status": "success",
        "query": ip,
        "country": "United States",
        "region": "California",
        "city": "San Francisco",
        "zip": "94107",
        "timezone": "America/Los_Angeles",
        "isp": "Test ISP",
        "org": "Test Org",
        "lat": 37.78,
        "lon": -122.39,
        "message": None,
    })
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

    location_response = await async_client.get(
        "/network/location",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert location_response.status_code == 200
    assert location_response.json()["location"]["city"] == "San Francisco"

    bt_response = await async_client.get(
        "/network/bluetooth/devices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bt_response.status_code == 200
    assert bt_response.json()["devices"][0]["name"] == "Test Device"
    assert bt_response.json()["available_devices"][0]["name"] == "Spare Speaker"

    bt_pair_response = await async_client.post(
        "/network/bluetooth/pair",
        json={"address": "AA:BB:CC:DD:EE:FF"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bt_pair_response.status_code == 200
    assert bt_pair_response.json()["action"] == "pair"

    bt_unpair_response = await async_client.post(
        "/network/bluetooth/unpair",
        json={"address": "AA:BB:CC:DD:EE:FF"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bt_unpair_response.status_code == 200
    assert bt_unpair_response.json()["action"] == "remove"

    bt_toggle_response = await async_client.post(
        "/network/bluetooth/toggle",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bt_toggle_response.status_code == 200
    assert bt_toggle_response.json()["local_ip"] == "192.168.1.10"

    ping_response = await async_client.post(
        "/network/ping",
        json={"host": "8.8.8.8", "count": 4},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ping_response.status_code == 200
    assert ping_response.json()["packets_received"] == 4
    assert abs(ping_response.json()["avg_rtt_ms"] - 15.0) < 0.1
