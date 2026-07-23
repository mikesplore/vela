from typing import Optional, List

from pydantic import BaseModel, Field


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


class PortProcess(BaseModel):
    pid: int
    name: str
    cmdline: List[str] = Field(default_factory=list)
    exe: Optional[str] = None


class PortCheckResponse(BaseModel):
    port: int
    listening: bool
    processes: List[PortProcess] = Field(default_factory=list)


class HealthCheckResponse(BaseModel):
    url: str
    reachable: bool
    status_code: Optional[int] = None
    elapsed_ms: Optional[float] = None
    error: Optional[str] = None


class FirewallStatusResponse(BaseModel):
    available: bool
    active: Optional[bool] = None
    status: str


class VpnStatusResponse(BaseModel):
    connected: bool
    interfaces: List[str] = Field(default_factory=list)
    connections: List[str] = Field(default_factory=list)