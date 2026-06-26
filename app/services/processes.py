import psutil


def kill_processes_by_name(name: str) -> int:
    killed_count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info.get("name") and proc.info["name"].lower() == name.lower():
                proc.terminate()
                proc.wait(timeout=3)
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            continue
    return killed_count
