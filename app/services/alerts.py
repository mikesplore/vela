"""
Vela System Alerts Service
Handles CPU/memory spike detection and daily system usage reports.
Uses vnstat for network data usage tracking.
"""

import logging
import subprocess
import re
import platform
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

import psutil

from app.services.monitoring import get_cpu_usage, get_ram_status, get_top_processes, get_uptime
from app.services.system_info import get_os_info
from app.utils import emails

logger = logging.getLogger(__name__)

RESEND_AVAILABLE = emails.is_configured()
if not RESEND_AVAILABLE:
    logger.warning("RESEND_API_KEY not set in .env — email alerts will be disabled")

# Configuration defaults
DEFAULT_CPU_THRESHOLD = 80.0
DEFAULT_MEMORY_THRESHOLD = 85.0
DEFAULT_SPIKE_COOLDOWN_MINUTES = 15
DEFAULT_NETWORK_INTERFACE = "eth0"  # Will auto-detect if not set

# State tracking for spike cooldowns
_last_spike_alerts: Dict[str, datetime] = {}
_alert_history: List[Dict[str, Any]] = []
_daily_stats: Dict[str, Any] = {}


def _get_vnstat_data(interface: Optional[str] = None) -> Dict[str, Any]:
    """
    Get network usage data from vnstat.
    Returns dict with rx (received) and tx (transmitted) data for today.
    """
    try:
        # Auto-detect interface if not specified
        if not interface:
            interface = _get_default_interface()
        
        # Run vnstat for the specified interface
        result = subprocess.run(
            ["vnstat", "-i", interface, "--json", "2"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"vnstat failed for interface {interface}: {result.stderr}")
            return {"rx": 0, "tx": 0, "rx_bytes": 0, "tx_bytes": 0}
        
        import json
        data = json.loads(result.stdout)
        
        # Extract today's data
        if "interfaces" in data and len(data["interfaces"]) > 0:
            interface_data = data["interfaces"][0]
            if "days" in interface_data:
                today = datetime.now().strftime("%Y-%m-%d")
                for day in interface_data["days"]:
                    if day.get("date", {}).get("id") == today:
                        return {
                            "rx": day.get("rx", 0),
                            "tx": day.get("tx", 0),
                            "rx_bytes": day.get("rx", 0),
                            "tx_bytes": day.get("tx", 0),
                        }
        
        # Fallback to total if today's data not available
        if "interfaces" in data and len(data["interfaces"]) > 0:
            total = interface_data.get("summary", {})
            return {
                "rx": total.get("rx", 0),
                "tx": total.get("tx", 0),
                "rx_bytes": total.get("rx", 0),
                "tx_bytes": total.get("tx", 0),
            }
        
        return {"rx": 0, "tx": 0, "rx_bytes": 0, "tx_bytes": 0}
    
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"Failed to get vnstat data: {e}")
        return {"rx": 0, "tx": 0, "rx_bytes": 0, "tx_bytes": 0}


def _get_default_interface() -> str:
    """Auto-detect the primary network interface."""
    try:
        # Try to get the default route interface
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout:
            match = re.search(r'dev\s+(\w+)', result.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass
    
    # Fallback to common interface names
    for iface in ["eth0", "enp0s3", "ens33", "wlan0"]:
        if psutil.net_if_stats().get(iface):
            return iface
    
    # Last resort: return first non-loopback interface
    interfaces = psutil.net_if_stats()
    for name, stats in interfaces.items():
        if name != "lo" and stats.isup:
            return name
    
    return "eth0"


def _format_bytes(bytes_value: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(bytes_value) < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def _is_in_cooldown(alert_type: str, cooldown_minutes: int) -> bool:
    """Check if an alert type is in cooldown period."""
    if alert_type in _last_spike_alerts:
        elapsed = (datetime.now() - _last_spike_alerts[alert_type]).total_seconds() / 60
        return elapsed < cooldown_minutes
    return False


def _update_cooldown(alert_type: str):
    """Update the last alert time for an alert type."""
    _last_spike_alerts[alert_type] = datetime.now()


def _get_top_process_info() -> Tuple[str, float]:
    """Get the top CPU-consuming process."""
    try:
        processes = get_top_processes(limit=1)
        if processes.by_cpu:
            top_proc = processes.by_cpu[0]
            return top_proc.name, top_proc.cpu_percent
    except Exception as e:
        logger.warning(f"Failed to get top process: {e}")
    return "unknown", 0.0


def _get_os_info_string() -> str:
    """Get a formatted OS info string."""
    try:
        os_info = get_os_info()
        return f"{os_info.os_name} {os_info.os_version} (Kernel: {os_info.kernel})"
    except Exception:
        return f"{platform.system()} {platform.release()}"


def _get_uptime_string() -> str:
    """Get formatted uptime string."""
    try:
        uptime_info = get_uptime()
        return uptime_info.formatted
    except Exception:
        return "unknown"


def check_and_send_spike_alert(
    recipient_email: str,
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD,
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD,
    cooldown_minutes: int = DEFAULT_SPIKE_COOLDOWN_MINUTES,
    network_interface: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Check current CPU and memory usage against thresholds and send alerts if exceeded.
    
    Args:
        recipient_email: Email address to send alerts to
        cpu_threshold: CPU usage percentage threshold (default: 80%)
        memory_threshold: Memory usage percentage threshold (default: 85%)
        cooldown_minutes: Minutes to wait before sending another alert of same type
        network_interface: Network interface for vnstat (auto-detected if None)
    
    Returns:
        Dict with alert details if alert was sent, None otherwise
    """
    if not RESEND_AVAILABLE:
        logger.error("resend package not available. Cannot send email alerts.")
        return None
    
    alerts_sent = []
    
    # Check CPU usage
    cpu_usage = get_cpu_usage()
    if cpu_usage.overall >= cpu_threshold:
        alert_key = "cpu_spike"
        if not _is_in_cooldown(alert_key, cooldown_minutes):
            try:
                top_process, _ = _get_top_process_info()
                os_info_str = _get_os_info_string()
                uptime_str = _get_uptime_string()
                
                # Import the send function from the user's module
                from app.utils.emails import send_spike_alert
                
                result = send_spike_alert(
                    to=recipient_email,
                    device_name=platform.node(),
                    cpu_percent=cpu_usage.overall,
                    memory_percent=get_ram_status().percent,
                    cpu_threshold=cpu_threshold,
                    memory_threshold=memory_threshold,
                    top_process=top_process,
                    uptime=uptime_str,
                    os_info=os_info_str,
                )
                
                _update_cooldown(alert_key)
                alerts_sent.append({
                    "type": "cpu_spike",
                    "value": cpu_usage.overall,
                    "threshold": cpu_threshold,
                    "result": result,
                })
                
                logger.info(f"CPU spike alert sent: {cpu_usage.overall}% >= {cpu_threshold}%")
                
            except Exception as e:
                logger.error(f"Failed to send CPU spike alert: {e}")
    
    # Check Memory usage
    ram_status = get_ram_status()
    if ram_status.percent >= memory_threshold:
        alert_key = "memory_spike"
        if not _is_in_cooldown(alert_key, cooldown_minutes):
            try:
                top_process, _ = _get_top_process_info()
                os_info_str = _get_os_info_string()
                uptime_str = _get_uptime_string()
                
                from app.utils.emails import send_spike_alert
                
                result = send_spike_alert(
                    to=recipient_email,
                    device_name=platform.node(),
                    cpu_percent=cpu_usage.overall,
                    memory_percent=ram_status.percent,
                    cpu_threshold=cpu_threshold,
                    memory_threshold=memory_threshold,
                    top_process=top_process,
                    uptime=uptime_str,
                    os_info=os_info_str,
                )
                
                _update_cooldown(alert_key)
                alerts_sent.append({
                    "type": "memory_spike",
                    "value": ram_status.percent,
                    "threshold": memory_threshold,
                    "result": result,
                })
                
                logger.info(f"Memory spike alert sent: {ram_status.percent}% >= {memory_threshold}%")
                
            except Exception as e:
                logger.error(f"Failed to send memory spike alert: {e}")
    
    return alerts_sent if alerts_sent else None


def collect_daily_stats() -> Dict[str, Any]:
    """
    Collect daily system statistics for the daily summary report.
    This should be called periodically throughout the day to accumulate data.
    """
    cpu_usage = get_cpu_usage()
    ram_status = get_ram_status()
    network_data = _get_vnstat_data()
    
    # Initialize or update daily stats
    today = datetime.now().strftime("%Y-%m-%d")
    if today not in _daily_stats:
        _daily_stats[today] = {
            "cpu_readings": [],
            "memory_readings": [],
            "disk_read_bytes": 0,
            "disk_write_bytes": 0,
            "net_sent_bytes": 0,
            "net_recv_bytes": 0,
            "alerts_count": 0,
            "last_alert_time": None,
        }
    
    stats = _daily_stats[today]
    stats["cpu_readings"].append(cpu_usage.overall)
    stats["memory_readings"].append(ram_status.percent)
    
    # Get disk I/O (sample over 1 second)
    try:
        disk_io = psutil.disk_io_counters()
        if disk_io:
            # This is a simplified approach - in production you'd want to track deltas
            stats["disk_read_bytes"] = disk_io.read_bytes
            stats["disk_write_bytes"] = disk_io.write_bytes
    except Exception:
        pass
    
    # Network data from vnstat
    stats["net_sent_bytes"] = network_data.get("tx_bytes", 0)
    stats["net_recv_bytes"] = network_data.get("rx_bytes", 0)
    
    return stats


def send_daily_summary(
    recipient_email: str,
    network_interface: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Send daily system usage summary via email.
    
    Args:
        recipient_email: Email address to send summary to
        network_interface: Network interface for vnstat (auto-detected if None)
    
    Returns:
        Dict with send result if successful, None otherwise
    """
    if not RESEND_AVAILABLE:
        logger.error("resend package not available. Cannot send daily summary.")
        return None
    
    try:
        # Collect current stats
        stats = collect_daily_stats()
        
        # Calculate averages and peaks
        cpu_readings = stats.get("cpu_readings", [0])
        memory_readings = stats.get("memory_readings", [0])
        
        cpu_avg = sum(cpu_readings) / len(cpu_readings) if cpu_readings else 0
        cpu_peak = max(cpu_readings) if cpu_readings else 0
        memory_avg = sum(memory_readings) / len(memory_readings) if memory_readings else 0
        memory_peak = max(memory_readings) if memory_readings else 0
        
        # Get network data from vnstat
        network_data = _get_vnstat_data(network_interface)
        net_sent = _format_bytes(network_data.get("tx_bytes", 0))
        net_recv = _format_bytes(network_data.get("rx_bytes", 0))
        
        # Get disk I/O (simplified - total bytes for the day)
        disk_read = _format_bytes(stats.get("disk_read_bytes", 0))
        disk_write = _format_bytes(stats.get("disk_write_bytes", 0))
        
        # Get top processes
        try:
            top_procs = get_top_processes(limit=3)
            top_processes = [
                {"name": p.name, "cpu": round(p.cpu_percent, 1)}
                for p in top_procs.by_cpu[:3]
            ]
        except Exception:
            top_processes = []
        
        # Get system info
        os_info_str = _get_os_info_string()
        uptime_str = _get_uptime_string()
        
        # Get alert count for today
        alerts_count = len([a for a in _alert_history if a.get("date") == datetime.now().strftime("%Y-%m-%d")])
        last_alert_time = "Never"
        if _alert_history:
            last_alert = _alert_history[-1]
            last_alert_time = last_alert.get("time", "Unknown")
        
        # Import the send function
        from app.utils.emails import send_daily_summary as send_summary_email
        
        result = send_summary_email(
            to=recipient_email,
            device_name=platform.node(),
            cpu_avg=round(cpu_avg, 1),
            cpu_peak=round(cpu_peak, 1),
            memory_avg=round(memory_avg, 1),
            memory_peak=round(memory_peak, 1),
            disk_read=disk_read,
            disk_write=disk_write,
            net_sent=net_sent,
            net_recv=net_recv,
            uptime=uptime_str,
            os_info=os_info_str,
            top_processes=top_processes,
            alerts_count=alerts_count,
            last_alert_time=last_alert_time,
        )
        
        logger.info("Daily summary sent successfully")
        return result
        
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")
        return None


def setup_monitoring_schedule(
    recipient_email: str,
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD,
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD,
    spike_check_interval_minutes: int = 5,
    daily_summary_time: str = "18:00",  # 6 PM by default
    network_interface: Optional[str] = None,
):
    """
    Set up scheduled tasks for system monitoring.
    
    Args:
        recipient_email: Email address for alerts and summaries
        cpu_threshold: CPU usage threshold for spike alerts
        memory_threshold: Memory usage threshold for spike alerts
        spike_check_interval_minutes: How often to check for spikes
        daily_summary_time: Time to send daily summary (HH:MM format)
        network_interface: Network interface for vnstat (auto-detected if None)
    """
    from app.services.scheduler import get_scheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    
    scheduler = get_scheduler()
    
    # Schedule spike monitoring
    def spike_check_job():
        try:
            result = check_and_send_spike_alert(
                recipient_email=recipient_email,
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
                network_interface=network_interface,
            )
            if result:
                for alert in result:
                    _alert_history.append({
                        "type": alert["type"],
                        "value": alert["value"],
                        "threshold": alert["threshold"],
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "time": datetime.now().strftime("%H:%M"),
                    })
        except Exception as e:
            logger.error(f"Error in spike check job: {e}")
    
    scheduler.add_job(
        spike_check_job,
        trigger=IntervalTrigger(minutes=spike_check_interval_minutes),
        id="vela_spike_monitor",
        name="Vela System Spike Monitor",
        replace_existing=True,
    )
    
    # Schedule daily summary
    hour, minute = map(int, daily_summary_time.split(":"))
    
    def daily_summary_job():
        try:
            send_daily_summary(
                recipient_email=recipient_email,
                network_interface=network_interface,
            )
        except Exception as e:
            logger.error(f"Error in daily summary job: {e}")
    
    scheduler.add_job(
        daily_summary_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="vela_daily_summary",
        name="Vela Daily System Summary",
        replace_existing=True,
    )
    
    logger.info(f"Monitoring scheduled: spike checks every {spike_check_interval_minutes}min, "
                f"daily summary at {daily_summary_time}")


def get_monitoring_status() -> Dict[str, Any]:
    """Get current monitoring status and configuration."""
    from app.services.scheduler import get_scheduler
    
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    
    spike_job = None
    summary_job = None
    
    for job in jobs:
        if job.id == "vela_spike_monitor":
            spike_job = {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        elif job.id == "vela_daily_summary":
            summary_job = {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
    
    return {
        "spike_monitor": spike_job,
        "daily_summary": summary_job,
        "alerts_today": len([a for a in _alert_history if a.get("date") == datetime.now().strftime("%Y-%m-%d")]),
        "vnstat_available": _is_vnstat_available(),
    }


def _is_vnstat_available() -> bool:
    """Check if vnstat is installed and functional."""
    try:
        result = subprocess.run(
            ["vnstat", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# Convenience function to check vnstat installation
def check_vnstat_installation() -> Dict[str, Any]:
    """
    Check if vnstat is properly installed and configured.
    Returns status information.
    """
    status = {
        "installed": False,
        "version": None,
        "interfaces": [],
        "default_interface": None,
        "errors": [],
    }
    
    try:
        # Check version
        result = subprocess.run(
            ["vnstat", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            status["installed"] = True
            status["version"] = result.stdout.strip().split('\n')[0] if result.stdout else "unknown"
        
        # List interfaces
        result = subprocess.run(
            ["vnstat", "--json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            if "interfaces" in data:
                status["interfaces"] = [iface["name"] for iface in data["interfaces"]]
                status["default_interface"] = _get_default_interface()
    
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        status["errors"].append(str(e))
    
    return status