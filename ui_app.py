"""Launch the AOS Schedule Converter web UI (localhost only)."""
import argparse
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

DEFAULT_PORT = 8765


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="AOS Schedule Converter web UI")
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()

    if _port_in_use(args.port):
        print(
            f"ERROR: Port {args.port} is already in use.\n"
            f"  Stop the other process, or start on a different port:\n"
            f"  python ui_app.py --port {args.port + 1}",
            file=sys.stderr,
        )
        sys.exit(1)

    import uvicorn

    print(f"AOS Schedule Converter UI at http://127.0.0.1:{args.port}")
    uvicorn.run("ui.server:app", host="127.0.0.1", port=args.port, reload=False)


if __name__ == "__main__":
    main()
