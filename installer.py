import argparse

from app.setup import run_setup


def main() -> None:
    parser = argparse.ArgumentParser(description="Vela setup entrypoint")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup (default behavior).",
    )
    parser.parse_args()
    run_setup()


if __name__ == "__main__":
    main()
