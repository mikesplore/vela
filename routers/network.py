import json
import re
import socket
import subprocess
import urllib.request
from typing import Any, Dict, List, Optional

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


def _run_command_input(cmd: list[str], input_text: str, timeout: int = 10) -> tuple[str, str, int]:
    """Run a command with stdin input (used for bluetoothctl interactive commands)."""
    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
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


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class IPResponse(BaseModel):
    local_ip: str
    public_ip: Optional[str]


class GeoLocation(BaseModel):
    status: str
    query: Optional[str]
    country: Optional[str]
    region: Optional[str]
    city: Optional[str]
    zip: Optional[str]
    timezone: Optional[str]
    isp: Optional[str]
    org: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    message: Optional[str]


class LocationResponse(BaseModel):
    local_ip: str
    public_ip: Optional[str]
    location: Optional[GeoLocation]


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
    connected: bool = False


class BluetoothDevicesResponse(BaseModel):
    """
    connected_devices  – devices with an active BT connection right now.
    paired_devices     – devices that are paired (trusted/known) but not currently connected.
    """
    connected_devices: List[BluetoothDevice]
    paired_devices: List[BluetoothDevice]


class BluetoothActionRequest(BaseModel):
    address: str


class BluetoothActionResponse(BaseModel):
    address: str
    action: str
    message: str


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


# ---------------------------------------------------------------------------
# Geo-location helper
# ---------------------------------------------------------------------------

def _geolocate_ip(ip: str) -> Optional[Dict[str, Any]]:
    if not ip:
        return None
    try:
        url = (
            f"http://ip-api.com/json/{ip}"
            "?fields=status,country,regionName,city,zip,timezone,isp,org,lat,lon,query,message"
        )
        with urllib.request.urlopen(url, timeout=5) as response:
            raw = response.read().decode().strip()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return {
            "status": data.get("status", "fail"),
            "query": data.get("query"),
            "country": data.get("country"),
            "region": data.get("regionName") or data.get("region"),
            "city": data.get("city"),
            "zip": data.get("zip"),
            "timezone": data.get("timezone"),
            "isp": data.get("isp"),
            "org": data.get("org"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "message": data.get("message"),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# IP / location endpoints
# ---------------------------------------------------------------------------

@router.get("/ip", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def network_ip() -> Any:
    """Return local and public IP addresses."""
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


@router.get("/location", response_model=LocationResponse, dependencies=[Depends(get_current_user)])
async def network_location() -> Any:
    """Return local and public IP addresses with geo-location information."""
    public_ip = _public_ip()
    location_data = _geolocate_ip(public_ip) if public_ip else None
    return LocationResponse(
        local_ip=_local_ip(),
        public_ip=public_ip or None,
        location=GeoLocation(**location_data) if location_data else None,
    )


# ---------------------------------------------------------------------------
# WiFi helpers
# ---------------------------------------------------------------------------

def _parse_nmcli_wifi_list(raw: str) -> List[WifiNetwork]:
    """
    Parse `nmcli --terse --escape no -f ACTIVE,SSID,SECURITY,SIGNAL device wifi list`.

    Using --escape no means colons inside SSIDs are NOT escaped, so we must
    split on the *first* 3 colons only to avoid breaking on SSIDs like
    "My:Home:Network".
    """
    networks: List[WifiNetwork] = []
    for line in raw.splitlines():
        # Split into at most 4 parts so an SSID with colons stays intact
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        active, ssid, security, signal = parts[0], parts[1], parts[2], parts[3]
        if not ssid:
            continue  # skip hidden networks with empty SSIDs
        networks.append(
            WifiNetwork(
                ssid=ssid,
                security=security.strip() or None,
                signal=int(signal) if signal.strip().isdigit() else None,
                active=active.lower() == "yes",
            )
        )
    return networks


def _active_wifi_device() -> Optional[str]:
    """Return the name of the Wi-Fi device that is currently connected, or None."""
    stdout, _, rc = _run_command(
        ["nmcli", "--terse", "--escape", "no", "-f", "DEVICE,TYPE,STATE", "device", "status"]
    )
    if rc != 0:
        return None
    for line in stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[1] == "wifi" and parts[2] == "connected":
            return parts[0]
    return None


def _current_wifi_status() -> WifiStatusResponse:
    stdout, stderr, rc = _run_command(
        ["nmcli", "--terse", "--escape", "no", "-f", "ACTIVE,SSID,SECURITY,SIGNAL", "device", "wifi", "list"]
    )
    if rc != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=stderr or "WiFi status unavailable",
        )
    networks = _parse_nmcli_wifi_list(stdout)
    active_network = next((n for n in networks if n.active), None)
    device = _active_wifi_device()
    return WifiStatusResponse(
        connected=bool(active_network),
        ssid=active_network.ssid if active_network else None,
        device=device,
        signal=active_network.signal if active_network else None,
        networks=networks,
    )


# ---------------------------------------------------------------------------
# WiFi endpoints
# ---------------------------------------------------------------------------

@router.get("/wifi/status", response_model=WifiStatusResponse, dependencies=[Depends(get_current_user)])
async def wifi_status() -> Any:
    """Return current WiFi connection status and all visible networks."""
    return _current_wifi_status()


@router.get("/wifi/list", response_model=WifiStatusResponse, dependencies=[Depends(get_current_user)])
async def wifi_list() -> Any:
    """List all available WiFi networks (triggers a fresh scan)."""
    # Trigger a rescan so the list is fresh, then return status
    _run_command(["nmcli", "device", "wifi", "rescan"])
    return _current_wifi_status()


@router.post("/wifi/connect", response_model=WifiStatusResponse, dependencies=[Depends(get_current_user)])
async def wifi_connect(request: WifiConnectRequest) -> Any:
    """Connect to a WiFi network by SSID (with optional password)."""
    cmd = ["nmcli", "device", "wifi", "connect", request.ssid]
    if request.password:
        cmd += ["password", request.password]
    stdout, stderr, rc = _run_command(cmd, timeout=30)
    if rc != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=stderr or stdout or "Could not connect to WiFi",
        )
    return _current_wifi_status()


@router.post("/wifi/disconnect", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def wifi_disconnect() -> Any:
    """Disconnect from the currently active WiFi network (radio stays on)."""
    # Find the active wifi device and disconnect it — this keeps the radio on
    # so the device can reconnect later, unlike `nmcli radio wifi off`.
    device = _active_wifi_device()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active WiFi connection to disconnect",
        )
    stdout, stderr, rc = _run_command(["nmcli", "device", "disconnect", device])
    if rc != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=stderr or stdout or "Could not disconnect WiFi",
        )
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


@router.post("/wifi/toggle", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def wifi_toggle(request: ToggleRequest) -> Any:
    """Enable or disable the WiFi radio entirely."""
    state = "on" if request.enabled else "off"
    stdout, stderr, rc = _run_command(["nmcli", "radio", "wifi", state])
    if rc != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=stderr or stdout or "Could not toggle WiFi",
        )
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


# ---------------------------------------------------------------------------
# Bluetooth helpers
# ---------------------------------------------------------------------------

_BT_ADDR_RE = re.compile(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.+)$")


def _parse_bluetooth_device_list(raw: str) -> List[BluetoothDevice]:
    """Parse output of `bluetoothctl devices [filter]`."""
    devices: List[BluetoothDevice] = []
    for line in raw.splitlines():
        match = _BT_ADDR_RE.match(line.strip())
        if match:
            devices.append(BluetoothDevice(address=match.group(1), name=match.group(2).strip()))
    return devices


def _get_connected_addresses() -> set[str]:
    """Return MAC addresses of devices that are currently connected."""
    stdout, _, rc = _run_command(["bluetoothctl", "devices", "Connected"])
    if rc != 0:
        return set()
    return {d.address for d in _parse_bluetooth_device_list(stdout)}


# ---------------------------------------------------------------------------
# Bluetooth endpoints
# ---------------------------------------------------------------------------

@router.post("/bluetooth/toggle", response_model=IPResponse, dependencies=[Depends(get_current_user)])
async def bluetooth_toggle(request: ToggleRequest) -> Any:
    """Enable or disable the Bluetooth adapter via rfkill."""
    command = ["rfkill", "unblock", "bluetooth"] if request.enabled else ["rfkill", "block", "bluetooth"]
    stdout, stderr, rc = _run_command(command)
    if rc != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=stderr or stdout or "Could not toggle Bluetooth",
        )
    return IPResponse(local_ip=_local_ip(), public_ip=_public_ip() or None)


@router.get("/bluetooth/devices", response_model=BluetoothDevicesResponse, dependencies=[Depends(get_current_user)])
async def bluetooth_devices() -> Any:
    """
    List Bluetooth devices.

    - **connected_devices**: devices with an active connection right now.
    - **paired_devices**: devices that are paired/known but *not* currently connected
      (i.e. available to connect without re-pairing).
    """
    # Connected devices
    connected_stdout, connected_stderr, connected_rc = _run_command(["bluetoothctl", "devices", "Connected"])
    if connected_rc != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=connected_stderr or "Could not list connected Bluetooth devices",
        )
    connected_devices = _parse_bluetooth_device_list(connected_stdout)
    connected_addresses = {d.address for d in connected_devices}

    # All paired devices
    paired_stdout, paired_stderr, paired_rc = _run_command(["bluetoothctl", "devices", "Paired"])
    if paired_rc != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=paired_stderr or "Could not list paired Bluetooth devices",
        )
    all_paired = _parse_bluetooth_device_list(paired_stdout)

    # Separate: paired-but-not-connected (available to connect)
    paired_not_connected = [d for d in all_paired if d.address not in connected_addresses]

    return BluetoothDevicesResponse(
        connected_devices=[d.model_copy(update={"connected": True}) for d in connected_devices],
        paired_devices=paired_not_connected,
    )


def _bluetoothctl_action(action: str, address: str, timeout: int = 20) -> BluetoothActionResponse:
    """Run a single-shot bluetoothctl action (pair / connect / disconnect / remove)."""
    # Feed commands via stdin so bluetoothctl runs non-interactively
    stdin_cmds = f"{action} {address}\nquit\n"
    stdout, stderr, rc = _run_command_input(["bluetoothctl"], stdin_cmds, timeout=timeout)

    # bluetoothctl rarely sets a non-zero exit code on failure; check output too
    failure_indicators = ("failed", "error", "not available")
    output_lower = (stdout + stderr).lower()
    if rc != 0 or any(ind in output_lower for ind in failure_indicators):
        detail = stderr or stdout or f"Could not {action} Bluetooth device {address}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)

    return BluetoothActionResponse(
        address=address,
        action=action,
        message=stdout or f"Bluetooth {action} successful for {address}",
    )


@router.post("/bluetooth/pair", response_model=BluetoothActionResponse, dependencies=[Depends(get_current_user)])
async def bluetooth_pair(request: BluetoothActionRequest) -> Any:
    """Pair with a nearby Bluetooth device (device must be in discoverable mode)."""
    return _bluetoothctl_action("pair", request.address)


@router.post("/bluetooth/connect", response_model=BluetoothActionResponse, dependencies=[Depends(get_current_user)])
async def bluetooth_connect(request: BluetoothActionRequest) -> Any:
    """Connect to a previously paired Bluetooth device."""
    return _bluetoothctl_action("connect", request.address)


@router.post("/bluetooth/disconnect", response_model=BluetoothActionResponse, dependencies=[Depends(get_current_user)])
async def bluetooth_disconnect(request: BluetoothActionRequest) -> Any:
    """Disconnect a currently connected Bluetooth device (keeps it paired)."""
    return _bluetoothctl_action("disconnect", request.address)


@router.post("/bluetooth/unpair", response_model=BluetoothActionResponse, dependencies=[Depends(get_current_user)])
async def bluetooth_unpair(request: BluetoothActionRequest) -> Any:
    """Remove / unpair a Bluetooth device."""
    return _bluetoothctl_action("remove", request.address)


# ---------------------------------------------------------------------------
# Ping endpoint
# ---------------------------------------------------------------------------

@router.post("/ping", response_model=PingResponse, dependencies=[Depends(get_current_user)])
async def ping_host(request: PingRequest) -> Any:
    """Ping a host and return round-trip statistics."""
    stdout, stderr, rc = _run_command(["ping", "-c", str(request.count), request.host])
    if rc != 0 and not stdout:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=stderr or "Ping failed")
    transmitted = received = 0
    packet_loss = 100.0
    avg_rtt: Optional[float] = None
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
            try:
                stats = line.split("=")[1].strip().split()[0].split("/")
                if len(stats) >= 2:
                    avg_rtt = float(stats[1])
            except (ValueError, IndexError):
                pass
    return PingResponse(
        host=request.host,
        packets_transmitted=transmitted,
        packets_received=received,
        packet_loss=packet_loss,
        avg_rtt_ms=avg_rtt,
    )


# ---------------------------------------------------------------------------
# Speed-test helpers
# ---------------------------------------------------------------------------

def _parse_speedtest_simple(raw: str) -> Optional[SpeedTestResponse]:
    """
    Parse `speedtest-cli --simple` output:
        Ping:  12.345 ms
        Download:  98.76 Mbit/s
        Upload:  45.67 Mbit/s
    Returns None if any value could not be parsed.
    """
    download = upload = ping = None
    for line in raw.splitlines():
        try:
            if line.startswith("Ping:"):
                ping = float(line.split()[1])
            elif line.startswith("Download:"):
                download = float(line.split()[1])
            elif line.startswith("Upload:"):
                upload = float(line.split()[1])
        except (ValueError, IndexError):
            pass
    if download is None or upload is None or ping is None:
        return None
    return SpeedTestResponse(download_mbps=download, upload_mbps=upload, ping_ms=ping)


def _parse_speedtest_json(raw: str) -> Optional[SpeedTestResponse]:
    """
    Parse Ookla `speedtest --format=json` output.
    Speeds are in bits/s; convert to Mbit/s.
    """
    try:
        data = json.loads(raw)
        download_mbps = data["download"]["bandwidth"] * 8 / 1_000_000
        upload_mbps = data["upload"]["bandwidth"] * 8 / 1_000_000
        ping_ms = float(data["ping"]["latency"])
        return SpeedTestResponse(download_mbps=download_mbps, upload_mbps=upload_mbps, ping_ms=ping_ms)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/speed-test", response_model=SpeedTestResponse, dependencies=[Depends(get_current_user)])
async def speed_test() -> Any:
    """Run a network speed test and return upload/download/ping metrics."""

    # 1. Try Ookla CLI with JSON output (most reliable parsing)
    stdout, _, rc = _run_command(["speedtest", "--format=json", "--accept-license", "--accept-gdpr"], timeout=60)
    if rc == 0:
        result = _parse_speedtest_json(stdout)
        if result:
            return result

    # 2. Try speedtest-cli (pip package) with --simple
    stdout, _, rc = _run_command(["speedtest-cli", "--simple"], timeout=60)
    if rc == 0:
        result = _parse_speedtest_simple(stdout)
        if result:
            return result

    # 3. Fall back to Python speedtest module
    if speedtest is not None:
        return _run_speedtest_module()

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="No speed test tool available. Install speedtest-cli (`pip install speedtest-cli`) or the Ookla CLI.",
    )