"""Vela CLI — service management and setup without loading the API stack."""

from __future__ import annotations

import argparse
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description="Vela CLI")
    parser.add_argument("--setup", action="store_true", help="Fresh-start setup: wipe creds, pair, restart services")
    parser.add_argument("--start", action="store_true", help="Start vela + vela-agent user services")
    parser.add_argument("--stop", action="store_true", help="Stop vela + vela-agent user services")
    parser.add_argument("--restart", action="store_true", help="Restart vela + vela-agent user services")
    parser.add_argument("--enable", action="store_true", help="Enable and start vela + vela-agent user services")
    parser.add_argument("--status", action="store_true", help="Show vela service status")
    parser.add_argument("--logs", action="store_true", help="Tail vela service logs")
    args = parser.parse_args()

    services = ["vela.service", "vela-agent.service"]

    if args.setup:
        from app.setup import run_setup

        run_setup()
        return

    if args.start:
        subprocess.run(["systemctl", "--user", "start", *services], check=True)
        print("Started vela services.")
        return

    if args.stop:
        subprocess.run(["systemctl", "--user", "stop", *services], check=True)
        print("Stopped vela services.")
        return

    if args.restart:
        subprocess.run(["systemctl", "--user", "restart", *services], check=True)
        print("Restarted vela services.")
        return

    if args.enable:
        subprocess.run(["systemctl", "--user", "enable", "--now", *services], check=True)
        print("Enabled and started vela services.")
        return

    if args.status:
        for service in services:
            proc = subprocess.run(
                ["systemctl", "--user", "is-active", service],
                capture_output=True,
                text=True,
                check=False,
            )
            state = (proc.stdout or "").strip() or "unknown"
            print(f"{service}: {state}")
        return

    if args.logs:
        subprocess.run(
            ["journalctl", "--user", "-u", "vela.service", "-u", "vela-agent.service", "-f"],
            check=True,
        )
        return

    # Default: run the local API server (imports app stack only now).
    import uvicorn
    from app.utils.config import get_config

    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
