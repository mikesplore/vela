import asyncio
import os
import subprocess

from app.agent.helpers import ensure_agent_registration, start_agent_loop


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Vela Agent — connects to VPS relay")
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start vela-agent.service via systemctl --user",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop vela-agent.service via systemctl --user",
    )
    parser.add_argument(
        "--pair",
        action="store_true",
        help="Force browser pairing flow and persist a new credential",
    )
    parser.add_argument(
        "--regenerate-secret",
        action="store_true",
        help="Re-register with the VPS to obtain a new agent secret (password change). "
             "Requires AGENT_SECRET to be set in the environment.",
    )
    args = parser.parse_args()

    if args.start:
        subprocess.run(["systemctl", "--user", "start", "vela-agent.service"], check=True)
        print("Started vela-agent.service.")
        return

    if args.stop:
        subprocess.run(["systemctl", "--user", "stop", "vela-agent.service"], check=True)
        print("Stopped vela-agent.service.")
        return

    if args.pair:
        ensure_agent_registration(force=True)
        print("Pairing completed successfully.")
        return

    if args.regenerate_secret:
        os.environ["REGENERATE_SECRET"] = "true"

    asyncio.run(start_agent_loop())


if __name__ == "__main__":
    main()
