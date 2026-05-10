import re
import socket
import subprocess
import urllib.request
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

try:
    import speedtest
except ImportError:  # pragma: no cover
    speedtest = None

from dependencies import get_current_user

router = APIRouter(prefix="/network", tags=["network"])


def _run_command(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def _local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _public_ip() -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
            return response.read().decode().strip()
    except Exception:
        return ""


class IPResponse(BaseModel):
    local_ip: str
    public_ip: Optional[str]


class WifiNetwork(BaseModel):
    ssid: str
    security: Optional[str]
    signal: Optional[int]
    active: bool


class WifiStatusResponse(BaseModel):
    connected: bool
    ssid: Optional[str]
    device: Optional[str]
    signal: Optional[int]
    networks: List[WifiNetwork]


class WifiConnectRequest(BaseModel):
    ssid: str
    password: Optional[str] = None


class BluetoothDevice(BaseModel):
    address: str
    name: str


class BluetoothDevicesResponse(BaseModel):
    devices: List[BluetoothDevice]


class ToggleRequest(BaseModel):
    enabled: bool


class PingRequest(BaseModel):
    host: str
    count: int = Field(4, ge=1, le=20)


class PingResponse(BaseModel):
    host: str
    packets_transmitted: int
    packets_received: int
    packet_loss: float
    avg_rtt_ms: Optional[float]


class SpeedTestResponse(BaseModel):
    download_mbps: float
    upload_mbps: float
    ping_ms: float


@router.get("/ip", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def network_ip() -> Any:
    """Return local and public IP addresses."""
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


def _parse_nmcli_wifi_list(raw: str) -> List[WifiNetwork]:
    networks: List[WifiNetwork] = []
    for line in raw.splitlines():
        fields = line.split(":")
        if len(fields) < 4:
            continue
        active, ssid, security, signal = fields[0], fields[1], fields[2], fields[3]
        networks.append(
            WifiNetwork(
                ssid=ssid,
                security=security or None,
                signal=int(signal) if signal.isdigit() else None,
                active=active == "yes",
            )
        )
    return networks


def _current_wifi_status() -> WifiStatusResponse:
    stdout, stderr, rc = _run_command(["nmcli", "-t", "-f", "ACTIVE,SSID,SECURITY,SIGNAL", "device", "wifi", "list"])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "WiFi status unavailable")
    networks = _parse_nmcli_wifi_list(stdout)
    active_network = next((item for item in networks if item.active), None)
    return WifiStatusResponse(
        connected=bool(active_network),
        ssid=active_network.ssid if active_network else None,
        device=None,
        signal=active_network.signal if active_network else None,
        networks=networks,
    )


@router.get("/wifi/status", response_model=WifiStatusResponse, dependencies=[Depends(get_current_user)])
async def wifi_status() -> Any:
    """Return WiFi status and available networks."""
    return _current_wifi_status()


@router.get("/wifi/list", response_model=WifiStatusResponse, dependencies=[Depends(get_current_user)])
async def wifi_list() -> Any:
    """List available WiFi networks."""
    return _current_wifi_status()


@router.post("/wifi/connect", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def wifi_connect(request: WifiConnectRequest) -> Any:
    """Connect to a WiFi network."""
    cmd = ["nmcli", "device", "wifi", "connect", request.ssid]
    if request.password:
        cmd += ["password", request.password]
    stdout, stderr, rc = _run_command(cmd)
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Could not connect to WiFi")
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


@router.post("/wifi/disconnect", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def wifi_disconnect() -> Any:
    """Disconnect from the current WiFi network."""
    stdout, stderr, rc = _run_command(["nmcli", "radio", "wifi", "off"])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Could not disconnect WiFi")
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


@router.post("/wifi/toggle", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def wifi_toggle(request: ToggleRequest) -> Any:
    """Enable or disable WiFi radio."""
    state = "on" if request.enabled else "off"
    stdout, stderr, rc = _run_command(["nmcli", "radio", "wifi", state])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Could not toggle WiFi")
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


@router.post("/bluetooth/toggle", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def bluetooth_toggle(request: ToggleRequest) -> Any:
    """Enable or disable Bluetooth."""
    command = ["rfkill", "unblock", "bluetooth"] if request.enabled else ["rfkill", "block", "bluetooth"]
    stdout, stderr, rc = _run_command(command)
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Could not toggle Bluetooth")
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


@router.get("/bluetooth/devices", response_model=BluetoothDevicesResponse, dependencies=[Depends(get_current_user)])
async def bluetooth_devices() -> Any:
    """List paired and available Bluetooth devices."""
    stdout, stderr, rc = _run_command(["bluetoothctl", "devices"])
    if rc != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Could not list Bluetooth devices")
    devices: List[BluetoothDevice] = []
    for line in stdout.splitlines():
        match = re.match(r"^Device\s+([0-9A-F:]+)\s+(.+)$", line)
        if match:
            devices.append(BluetoothDevice(address=match.group(1), name=match.group(2)))
    return BluetoothDevicesResponse(devices=devices)


@router.post("/ping", response_model=PingResponse, dependencies=[Depends(get_current_user)])
async def ping_host(request: PingRequest) -> Any:
    """Ping a host and return round-trip statistics."""
    stdout, stderr, rc = _run_command(["ping", "-c", str(request.count), request.host])
    if rc != 0 and not stdout:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Ping failed")
    transmitted = received = 0
    packet_loss = 100.0
    avg_rtt = None
    for line in stdout.splitlines():
        if "packets transmitted" in line:
            parts = line.split(",")
            try:
                transmitted = int(parts[0].split()[0])
                received = int(parts[1].split()[0])
                packet_loss = float(parts[2].strip().split()[0].replace("%", ""))
            except (ValueError, IndexError):
                pass
        if "min/avg/max" in line or "round-trip" in line:
            stats = line.split("=")[1].strip().split()[0].split("/")
            if len(stats) >= 2:
                try:
                    avg_rtt = float(stats[1])
                except ValueError:
                    pass
    return PingResponse(host=request.host, packets_transmitted=transmitted, packets_received=received, packet_loss=packet_loss, avg_rtt_ms=avg_rtt)


def _parse_speedtest_simple(raw: str) -> SpeedTestResponse:
    download = upload = ping = 0.0
    for line in raw.splitlines():
        if line.startswith("Ping:"):
            ping = float(line.split()[1])
        if line.startswith("Download:"):
            download = float(line.split()[1])
        if line.startswith("Upload:"):
            upload = float(line.split()[1])
    return SpeedTestResponse(download_mbps=download, upload_mbps=upload, ping_ms=ping)


def _run_speedtest_module() -> SpeedTestResponse:
    if speedtest is None:
        raise ImportError("Python speedtest module is unavailable")
    try:
        tester = speedtest.Speedtest()
        tester.get_best_server()
        download_mbps = tester.download() / 1_000_000
        upload_mbps = tester.upload() / 1_000_000
        ping_ms = float(getattr(tester.results, "ping", 0.0))
        return SpeedTestResponse(download_mbps=download_mbps, upload_mbps=upload_mbps, ping_ms=ping_ms)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/speed-test", response_model=SpeedTestResponse, dependencies=[Depends(get_current_user)])
async def speed_test() -> Any:
    """Run a network speed test and return upload/download metrics."""
    stdout, stderr, rc = _run_command(["speedtest-cli", "--simple"])
    if rc != 0:
        stdout, stderr, rc = _run_command(["speedtest", "--simple"])
    if rc == 0:
        return _parse_speedtest_simple(stdout)
    if speedtest is not None:
        return _run_speedtest_module()
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or stdout or "Speed test is unavailable")
