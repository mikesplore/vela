import asyncio
import subprocess

from app.agent.helpers import start_agent_loop


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
    args = parser.parse_args()

    if args.start:
        subprocess.run(["systemctl", "--user", "start", "vela-agent.service"], check=True)
        print("Started vela-agent.service.")
        return

    if args.stop:
        subprocess.run(["systemctl", "--user", "stop", "vela-agent.service"], check=True)
        print("Stopped vela-agent.service.")
        return

    asyncio.run(start_agent_loop())


if __name__ == "__main__":
    main()
