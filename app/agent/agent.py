import asyncio
import os

from app.agent.helpers import start_agent_loop


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Vela Agent — connects to VPS relay")
    parser.add_argument(
        "--regenerate-secret",
        action="store_true",
        help="Re-register with the VPS to obtain a new agent secret (password change). "
             "Requires AGENT_SECRET to be set in the environment.",
    )
    args = parser.parse_args()

    if args.regenerate_secret:
        os.environ["REGENERATE_SECRET"] = "true"

    asyncio.run(start_agent_loop())


if __name__ == "__main__":
    main()
