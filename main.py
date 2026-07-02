import argparse
from pathlib import Path
from clipboard_logic import Peer, ClipboardShareApp

def parse_peer(value: str) -> Peer:
    if ":" not in value:
        raise argparse.ArgumentTypeError("Peer must be in HOST:PORT format.")
    host, port_raw = value.rsplit(":", 1)
    if not host:
        raise argparse.ArgumentTypeError("Peer host cannot be empty.")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Peer port must be an integer.") from exc
    if not (1 <= port <= 65535):
        raise argparse.ArgumentTypeError("Peer port must be between 1 and 65535.")
    return Peer(host=host, port=port)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Share text clipboard between Windows machines on the same network."
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=5000,
        help="TCP port to listen on (default: 5000).",
    )
    parser.add_argument(
        "--peer",
        action="append",
        type=parse_peer,
        default=[],
        help="Remote peer in HOST:PORT format. Use multiple --peer options for multiple machines.",
    )
    parser.add_argument(
        "--log-file",
        default="clipboard_log.txt",
        help="Path to local clipboard log file (default: clipboard_log.txt).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.4,
        help="Clipboard poll interval in seconds (default: 0.4).",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Run the application with a graphical user interface.",
    )

    args = parser.parse_args()

    if not (1 <= args.listen_port <= 65535):
        raise SystemExit("listen-port must be between 1 and 65535.")
    if args.poll_interval <= 0:
        raise SystemExit("poll-interval must be greater than 0.")

    if args.gui:
        from gui import run_gui
        run_gui(args)
    else:
        app = ClipboardShareApp(
            listen_port=args.listen_port,
            peers=args.peer,
            log_file=Path(args.log_file),
            poll_interval=args.poll_interval,
        )
        app.run()


if __name__ == "__main__":
    main()
