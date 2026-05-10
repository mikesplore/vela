import pytest

from auth import create_access_token
from routers import system_info as system_info_module


@pytest.mark.anyio
async def test_system_info_snapshot_returns_data(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    monkeypatch.setattr(
        system_info_module,
        "_get_cpu_info",
        lambda: system_info_module.CPUInfo(
            model="Intel Core i9",
            physical_cores=8,
            logical_cores=16,
            base_freq_mhz=3600.0,
            architecture="x86_64",
        ),
    )
    monkeypatch.setattr(
        system_info_module,
        "_get_ram_info",
        lambda: system_info_module.RAMInfo(
            total=16_000_000_000,
            available=8_000_000_000,
            used=8_000_000_000,
            percent=50.0,
            swap_total=2_000_000_000,
            swap_used=500_000_000,
            swap_free=1_500_000_000,
            swap_percent=25.0,
        ),
    )
    monkeypatch.setattr(system_info_module, "_get_gpu_info", lambda: [system_info_module.GPUInfo(name="TestGPU", vram_total_mb=8192, driver="nvidia", vendor="NVIDIA")])
    monkeypatch.setattr(system_info_module, "_get_disk_info", lambda: [system_info_module.DiskPartitionInfo(mountpoint="/", total=100_000_000_000, used=50_000_000_000, free=50_000_000_000, percent=50.0, filesystem="ext4")])
    monkeypatch.setattr(system_info_module, "_get_os_info", lambda: system_info_module.OSInfo(os_name="Linux", os_version="5.15", kernel="5.15.0", hostname="test-host", user="testuser", uptime_seconds=10000))
    monkeypatch.setattr(system_info_module, "_get_usb_devices", lambda: [system_info_module.USBDevice(bus="001", device="002", id="abcd:1234", description="Test USB Device")])
    monkeypatch.setattr(system_info_module, "_get_monitors", lambda: [system_info_module.MonitorInfo(name="HDMI-1", resolution="1920x1080", refresh_rate=60.0)])
    monkeypatch.setattr(system_info_module, "_get_bios_info", lambda: system_info_module.BIOSInfo(vendor="TestVendor", version="1.0", release_date="2025-01-01", motherboard="TestBoard"))

    response = await async_client.get(
        "/system/info",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["cpu"]["model"] == "Intel Core i9"
    assert data["os"]["hostname"] == "test-host"
    assert data["gpu"][0]["name"] == "TestGPU"
    assert data["disk"][0]["filesystem"] == "ext4"
    assert data["monitors"][0]["resolution"] == "1920x1080"


@pytest.mark.anyio
async def test_system_info_os_endpoint_returns_data(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    monkeypatch.setattr(system_info_module, "_get_os_info", lambda: system_info_module.OSInfo(os_name="Linux", os_version="5.15", kernel="5.15.0", hostname="test-host", user="testuser", uptime_seconds=10000))

    response = await async_client.get(
        "/system/os",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["os_name"] == "Linux"
    assert payload["hostname"] == "test-host"
