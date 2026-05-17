# Phase 2 Response Models

This file records the validated response structures for phase 2 endpoints in the Vela API.
It is updated whenever phase 2 endpoint behavior is confirmed.

## Summary

Phase 2 routes were verified against the local ASGI app and repository tests.
All HTTP endpoints returned `200 OK` for the current implementation.

## `/system` endpoints

### `GET /system/info`
A fully structured snapshot of the host system. The response includes nested objects and arrays for each subsystem.

```json
{
  "cpu": {
    "model": "Intel(R) Core(TM) i7-1165G7 CPU @ 2.80GHz",
    "physical_cores": 4,
    "logical_cores": 8,
    "base_freq_mhz": 2800.0,
    "architecture": "x86_64"
  },
  "ram": {
    "total": 17179869184,
    "available": 1234567890,
    "used": 9876543210,
    "percent": 57.5,
    "swap_total": 2147483648,
    "swap_used": 123456789,
    "swap_free": 2024026859,
    "swap_percent": 5.7
  },
  "gpu": [
    {
      "name": "NVIDIA GeForce GTX 1650",
      "vram_total_mb": 4096,
      "driver": "535.54",
      "vendor": "NVIDIA"
    }
  ],
  "disk": [
    {
      "mountpoint": "/",
      "total": 500000000000,
      "used": 220000000000,
      "free": 280000000000,
      "percent": 44.0,
      "filesystem": "ext4"
    }
  ],
  "os": {
    "os_name": "Linux",
    "os_version": "Ubuntu 24.04",
    "kernel": "6.5.0-25-generic",
    "hostname": "my-host",
    "user": "mike",
    "uptime_seconds": 123456
  },
  "usb": [
    {
      "bus": "001",
      "device": "002",
      "id": "abcd:1234",
      "description": "USB Keyboard"
    }
  ],
  "monitors": [
    {
      "name": "HDMI-1",
      "resolution": "1920x1080",
      "refresh_rate": 60.0
    }
  ],
  "bios": {
    "vendor": "TestVendor",
    "version": "1.0",
    "release_date": "2025-01-01",
    "motherboard": "TestBoard"
  }
}
```

### `GET /system/cpu`
```json
{
  "model": "Intel(R) Core(TM)...",
  "physical_cores": 4,
  "logical_cores": 8,
  "base_freq_mhz": 3400.0,
  "architecture": "x86_64"
}
```

### `GET /system/ram`
```json
{
  "total": 17179869184,
  "available": 1234567890,
  "used": 9876543210,
  "percent": 57.5,
  "swap_total": 2147483648,
  "swap_used": 123456789,
  "swap_free": 2024026859,
  "swap_percent": 5.7
}
```

### `GET /system/gpu`
```json
[]
```
or
```json
[
  {
    "name": "NVIDIA GeForce ...",
    "vram_total_mb": 8192,
    "driver": "535.54",
    "vendor": "NVIDIA"
  }
]
```

### `GET /system/disk`
```json
[
  {
    "mountpoint": "/",
    "total": 500000000000,
    "used": 220000000000,
    "free": 280000000000,
    "percent": 44.0,
    "filesystem": "ext4"
  }
]
```

### `GET /system/os`
```json
{
  "os_name": "Linux",
  "os_version": "#1 SMP ...",
  "kernel": "6.5.0",
  "hostname": "my-host",
  "user": "mike",
  "uptime_seconds": 123456
}
```

### `GET /system/usb`
```json
[
  {
    "bus": "001",
    "device": "002",
    "id": "abcd:1234",
    "description": "USB Device"
  }
]
```

### `GET /system/monitors`
```json
[
  {
    "name": "HDMI-1",
    "resolution": "1920x1080",
    "refresh_rate": 60.0
  }
]
```

### `GET /system/bios`
```json
{
  "vendor": "TestVendor",
  "version": "1.0",
  "release_date": "2025-01-01",
  "motherboard": "TestBoard"
}
```

## `/monitor` endpoints

### `GET /monitor/snapshot`
Response shape:
```json
{
  "cpu": { ... },
  "ram": { ... },
  "gpu": [ ... ],
  "disk_io": [ ... ],
  "network_io": [ ... ],
  "temperatures": [ ... ],
  "fans": [ ... ],
  "battery": { ... },
  "processes": { ... }
}
```

### `GET /monitor/cpu`
```json
{
  "overall": 12.5,
  "per_core": [10.0, 15.0, 12.0, 13.5]
}
```

### `GET /monitor/ram`
Same schema as `/system/ram`.

### `GET /monitor/gpu`
```json
[]
```
or a list of GPU usage objects.

### `GET /monitor/disk-io`
```json
[
  {
    "device": "sda",
    "read_bytes_per_sec": 10240.0,
    "write_bytes_per_sec": 5120.0
  }
]
```

### `GET /monitor/network-io`
```json
[
  {
    "interface": "eth0",
    "bytes_sent_per_sec": 1250.4,
    "bytes_recv_per_sec": 2048.7
  }
]
```

### `GET /monitor/temperatures`
```json
[
  {
    "sensor": "coretemp",
    "label": "Package id 0",
    "current": 49.0,
    "high": 100.0,
    "critical": 100.0
  }
]
```

### `GET /monitor/fans`
```json
[
  {
    "sensor": "fan1",
    "speed_rpm": 1200
  }
]
```

### `GET /monitor/battery`
```json
{
  "percent": 87.0,
  "plugged_in": true,
  "secs_left": 7200
}
```

### `GET /monitor/processes`
```json
{
  "top_by_cpu": [
    {
      "pid": 1234,
      "name": "python",
      "username": "mike",
      "cpu_percent": 5.0,
      "memory_percent": 1.2,
      "memory_rss": 12345678
    }
  ],
  "top_by_memory": [ ... ]
}
```

### `WS /monitor/stream`
- This is a WebSocket endpoint, not an HTTP GET endpoint.
- It streams the same snapshot object as `/monitor/snapshot` every `interval` seconds.
- Example payload shape is identical to `/monitor/snapshot`.

## Kotlin models

```kotlin
data class CPUInfo(
    val model: String,
    val physical_cores: Int,
    val logical_cores: Int,
    val base_freq_mhz: Double?,
    val architecture: String
)

data class RAMInfo(
    val total: Long,
    val available: Long,
    val used: Long,
    val percent: Double,
    val swap_total: Long,
    val swap_used: Long,
    val swap_free: Long,
    val swap_percent: Double
)

data class GPUInfo(
    val name: String,
    val vram_total_mb: Int?,
    val driver: String?,
    val vendor: String?
)

data class DiskPartitionInfo(
    val mountpoint: String,
    val total: Long,
    val used: Long,
    val free: Long,
    val percent: Double,
    val filesystem: String
)

data class OSInfo(
    val os_name: String,
    val os_version: String,
    val kernel: String,
    val hostname: String,
    val user: String,
    val uptime_seconds: Int
)

data class MonitorInfo(
    val name: String,
    val resolution: String,
    val refresh_rate: Double?
)

data class BIOSInfo(
    val vendor: String?,
    val version: String?,
    val release_date: String?,
    val motherboard: String?
)

data class CPUUsage(
    val overall: Double,
    val per_core: List<Double>
)

data class DiskIOMetric(
    val device: String,
    val read_bytes_per_sec: Double,
    val write_bytes_per_sec: Double
)

data class NetworkIOMetric(
    val interface: String,
    val bytes_sent_per_sec: Double,
    val bytes_recv_per_sec: Double
)

data class TemperatureEntry(
    val sensor: String,
    val label: String,
    val current: Double,
    val high: Double?,
    val critical: Double?
)

data class FanEntry(
    val sensor: String,
    val speed_rpm: Int?
)

data class BatteryInfo(
    val percent: Double?,
    val plugged_in: Boolean?,
    val secs_left: Int?
)

data class ProcessInfo(
    val pid: Int,
    val name: String,
    val username: String?,
    val cpu_percent: Double,
    val memory_percent: Double,
    val memory_rss: Long
)

data class ProcessMetrics(
    val top_by_cpu: List<ProcessInfo>,
    val top_by_memory: List<ProcessInfo>
)
```
