"""Vela CLI — service management and setup without loading the API stack."""

from __future__ import annotations

import argparse
import subprocess
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="Vela CLI")
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
        help="Print the MCP connection link for this agent (agent_id + relay_secret)",
    )
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

        env_path = resolve_active_dotenv_path()
        values = dotenv_values(env_path) if env_path.exists() else {}
        agent_id = (values.get("AGENT_ID") or "").strip()
        relay_secret = (
            values.get("RELAY_SECRET") or values.get("AGENT_SECRET") or ""
        ).strip()
        mcp_server_url = (values.get("MCP_SERVER_URL") or "").strip()

        if not agent_id or not relay_secret:
            print("No paired agent found. Run `vela --setup` to pair this machine first.")
            return

        print(f"agent_id:     {agent_id}")
        print(f"relay_secret: {relay_secret}")
        if mcp_server_url:
            # Normalize: accept either "https://mcp.example.com" or
            # "https://mcp.example.com/mcp" as the server base.
            base = mcp_server_url.rstrip("/")
            if base.endswith("/mcp"):
                base = base[:-len("/mcp")].rstrip("/")
            # Claude.ai only accepts a URL (no headers), so the secret goes in
            # the path: /mcp/{agent_id}:{relay_secret}
            claude_url = f"{base}/mcp/{agent_id}:{relay_secret}"
            print(f"mcp_link:     {claude_url}")
            print()
            print("Paste this into Claude.ai → Connectors → Remote MCP server URL:")
            print(f"  {claude_url}")
            print()
            print("For local clients (Cline/Claude Desktop) that accept headers:")
            print(f"  url:     {base}/mcp/{agent_id}")
            print(f"  headers: {{ \"Authorization\": \"Bearer {relay_secret}\" }}")
        else:
            print()
            print("Set MCP_SERVER_URL in the active .env to also print a ready-to-paste link.")
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
