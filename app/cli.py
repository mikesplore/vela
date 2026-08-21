"""Vela CLI — service management and setup without loading the API stack."""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="Vela CLI")
    parser.add_argument("command", nargs="?", choices=["pair"], help="Interactive commands")
    parser.add_argument("--setup", action="store_true", help="Fresh-start setup: wipe creds, pair, restart services")
    parser.add_argument("--start", action="store_true", help="Start vela + vela-agent user services")
    parser.add_argument("--stop", action="store_true", help="Stop vela + vela-agent user services")
    parser.add_argument("--restart", action="store_true", help="Restart vela + vela-agent user services")
    parser.add_argument("--enable", action="store_true", help="Enable and start vela + vela-agent user services")
    parser.add_argument("--status", action="store_true", help="Show vela service status")
    parser.add_argument("--logs", action="store_true", help="Tail vela service logs")
    parser.add_argument("--dashboard", action="store_true", help="Open the local Operations dashboard")
    parser.add_argument(
        "--env",
        action="store_true",
        help="Open the active credentials .env (same file vela-agent loads)",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Create and print a scoped MCP connection for this agent",
    )
    parser.add_argument(
        "--mcp-revoke",
        metavar="CONNECTION_ID",
        help="Revoke a previously created MCP connection",
    )
    parser.add_argument(
        "--mcp-policy",
        choices=("strict", "read_only", "open"),
        help="Tool policy for the MCP connection (default: MCP_TOOL_POLICY or strict)",
    )
    args = parser.parse_args()

    services = ["vela.service", "vela-agent.service"]

    if args.command == "pair":
        from app.agent.pairing import complete_pairing
        from app.agent.envutil import _normalise_vps_url
        from app.utils.config import get_config

        configured_vps = (os.getenv("VPS_URL", "").strip() or get_config().vps_url.strip())
        vps_url = input(f"VPS URL [{configured_vps or 'https://relay.example.com'}]: ").strip()
        vps_url = _normalise_vps_url(vps_url or configured_vps)
        if not vps_url:
            raise SystemExit("VPS URL is required")
        pairing_code = input("Pairing code: ").strip()
        pairing_pin = getpass.getpass("Pairing PIN: ").strip()
        agent_label = input("Agent label (optional): ").strip() or None
        try:
            result = complete_pairing(vps_url, pairing_code, pairing_pin, agent_label)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Pairing submitted for agent {result.get('agent_id', 'unknown')}.")
        print("Return to the terminal running `vela --setup`; it will finish activation automatically.")
        return

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

    if args.dashboard:
        from app.utils.config import get_config

        config = get_config()
        host = "127.0.0.1" if config.host in {"0.0.0.0", "::", "::0"} else config.host
        url = f"http://{host}:{config.port}/admin/dashboard"
        if webbrowser.open(url):
            print(f"Opened Operations dashboard: {url}")
        else:
            print(f"Open the Operations dashboard in your browser: {url}")
        return

    if args.env:
        from app.utils.env_paths import open_dotenv_in_editor

        env_path = open_dotenv_in_editor()
        print(f"Active Vela .env: {env_path}")
        print("After saving changes, run: vela --restart")
        return

    if args.mcp:
        from app.utils.env_paths import resolve_active_dotenv_path
        from dotenv import dotenv_values
        import requests

        env_path = resolve_active_dotenv_path()
        values = dotenv_values(env_path) if env_path.exists() else {}
        agent_id = (values.get("AGENT_ID") or "").strip()
        relay_secret = (
            values.get("RELAY_SECRET") or values.get("AGENT_SECRET") or ""
        ).strip()
        mcp_server_url = (values.get("MCP_SERVER_URL") or "").strip()
        mcp_tool_policy = (args.mcp_policy or values.get("MCP_TOOL_POLICY") or "strict").strip().lower()

        if not agent_id or not relay_secret:
            print("No paired agent found. Run `vela --setup` to pair this machine first.")
            return

        if not mcp_server_url:
            print("Set MCP_SERVER_URL in the active .env to create an MCP connection.")
            return

        base = mcp_server_url.rstrip("/")
        if base.endswith("/mcp"):
            base = base[:-len("/mcp")].rstrip("/")
        try:
            response = requests.post(
                f"{base}/connections",
                json={
                    "agent_id": agent_id,
                    "approval_pin": (values.get("ASSISTANT_ACTION_PIN") or "").strip(),
                    "tool_policy": mcp_tool_policy,
                },
                headers={"X-Relay-Secret": relay_secret},
                timeout=15,
            )
            if response.status_code >= 400:
                print(f"Could not create MCP connection (HTTP {response.status_code}).")
                return
            data = response.json()
            connection_id = data.get("connection_id")
            mcp_url = data.get("mcp_url")
            mcp_credential = data.get("mcp_credential")
            if not connection_id or not mcp_url or not mcp_credential:
                print("MCP gateway returned an incomplete connection response.")
                return
        except (requests.RequestException, ValueError):
            print("Could not reach the MCP gateway or parse its response.")
            return

        print("MCP connection created.")
        print(f"connection_id: {connection_id}")
        print(f"MCP URL:       {mcp_url}")
        print(f"Authentication: Bearer {mcp_credential}")
        print("Keep this credential private; it is displayed only once.")
        return

    if args.mcp_revoke:
        from app.utils.env_paths import resolve_active_dotenv_path
        from dotenv import dotenv_values
        import requests

        env_path = resolve_active_dotenv_path()
        values = dotenv_values(env_path) if env_path.exists() else {}
        relay_secret = (values.get("RELAY_SECRET") or values.get("AGENT_SECRET") or "").strip()
        mcp_server_url = (values.get("MCP_SERVER_URL") or "").strip()
        if not relay_secret or not mcp_server_url:
            print("RELAY_SECRET and MCP_SERVER_URL are required to revoke an MCP connection.")
            return
        base = mcp_server_url.rstrip("/")
        if base.endswith("/mcp"):
            base = base[:-len("/mcp")].rstrip("/")
        try:
            response = requests.post(
                f"{base}/connections/{args.mcp_revoke}/revoke",
                headers={"X-Relay-Secret": relay_secret},
                timeout=15,
            )
        except requests.RequestException:
            print("Could not reach the MCP gateway.")
            return
        if response.status_code >= 400:
            print(f"Could not revoke MCP connection (HTTP {response.status_code}).")
            return
        print(f"MCP connection revoked: {args.mcp_revoke}")
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
