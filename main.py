import argparse
import ctypes
import json
import socket
import threading
import time
import uuid
import winsound
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


class ClipboardError(RuntimeError):
    pass


class WinClipboard:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._lock = threading.Lock()

        self._user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        self._user32.OpenClipboard.restype = ctypes.c_bool
        self._user32.CloseClipboard.argtypes = []
        self._user32.CloseClipboard.restype = ctypes.c_bool
        self._user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
        self._user32.IsClipboardFormatAvailable.restype = ctypes.c_bool
        self._user32.GetClipboardData.argtypes = [ctypes.c_uint]
        self._user32.GetClipboardData.restype = ctypes.c_void_p
        self._user32.EmptyClipboard.argtypes = []
        self._user32.EmptyClipboard.restype = ctypes.c_bool
        self._user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        self._user32.SetClipboardData.restype = ctypes.c_void_p

        self._kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        self._kernel32.GlobalAlloc.restype = ctypes.c_void_p
        self._kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        self._kernel32.GlobalLock.restype = ctypes.c_void_p
        self._kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        self._kernel32.GlobalUnlock.restype = ctypes.c_bool
        self._kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.GlobalFree.restype = ctypes.c_void_p

    def get_text(self) -> Optional[str]:
        with self._lock:
            if not self._user32.OpenClipboard(None):
                raise ClipboardError("Could not open clipboard.")
            try:
                if not self._user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    return None
                handle = self._user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                ptr = self._kernel32.GlobalLock(handle)
                if not ptr:
                    raise ClipboardError("Could not lock clipboard memory.")
                try:
                    text = ctypes.wstring_at(ptr)
                finally:
                    self._kernel32.GlobalUnlock(handle)
                return text
            finally:
                self._user32.CloseClipboard()

    def set_text(self, text: str) -> None:
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        with self._lock:
            if not self._user32.OpenClipboard(None):
                raise ClipboardError("Could not open clipboard.")
            try:
                if not self._user32.EmptyClipboard():
                    raise ClipboardError("Could not clear clipboard.")

                handle = self._kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                if not handle:
                    raise ClipboardError("Could not allocate clipboard memory.")

                ptr = self._kernel32.GlobalLock(handle)
                if not ptr:
                    self._kernel32.GlobalFree(handle)
                    raise ClipboardError("Could not lock allocated memory.")
                try:
                    ctypes.memmove(ptr, encoded, len(encoded))
                finally:
                    self._kernel32.GlobalUnlock(handle)

                result = self._user32.SetClipboardData(CF_UNICODETEXT, handle)
                if not result:
                    self._kernel32.GlobalFree(handle)
                    raise ClipboardError("Could not set clipboard data.")
            finally:
                self._user32.CloseClipboard()


@dataclass(frozen=True)
class Peer:
    host: str
    port: int


class ClipboardShareApp:
    def __init__(
        self,
        listen_port: int,
        peers: list[Peer],
        log_file: Path,
        poll_interval: float,
    ) -> None:
        self.listen_port = listen_port
        self.peers = peers
        self.log_file = log_file
        self.poll_interval = poll_interval
        self.node_id = str(uuid.uuid4())

        self.clipboard = WinClipboard()
        self.stop_event = threading.Event()
        self.last_seen_local: Optional[str] = None
        self.suppress_next_local: Optional[str] = None
        self.log_lock = threading.Lock()

    def run(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log("SYSTEM", f"Started node {self.node_id} on port {self.listen_port}")
        print(f"Node ID: {self.node_id}")
        print(f"Listening on 0.0.0.0:{self.listen_port}")
        if self.peers:
            print("Peers: " + ", ".join(f"{peer.host}:{peer.port}" for peer in self.peers))
        else:
            print("Peers: none")
        print("Press Ctrl+C to stop.")

        server_thread = threading.Thread(target=self._server_loop, daemon=True)
        monitor_thread = threading.Thread(target=self._clipboard_monitor_loop, daemon=True)
        server_thread.start()
        monitor_thread.start()

        try:
            while not self.stop_event.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            print("\nStopping...")
            self.stop_event.set()
        finally:
            self._log("SYSTEM", "Stopped")

    def _server_loop(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", self.listen_port))
            server.listen(5)
            server.settimeout(1.0)

            while not self.stop_event.is_set():
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()

    def _handle_connection(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        remote = f"{addr[0]}:{addr[1]}"
        with conn:
            conn.settimeout(2.0)
            data = b""
            try:
                while b"\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            except OSError:
                return

        if not data:
            return

        raw = data.split(b"\n", 1)[0]
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._log("ERROR", f"Invalid message from {remote}")
            return

        if payload.get("type") != "clipboard":
            return

        text = payload.get("text")
        origin = payload.get("origin", "unknown")
        if not isinstance(text, str):
            return
        if origin == self.node_id:
            return

        try:
            self.clipboard.set_text(text)
            self.suppress_next_local = text
            self.last_seen_local = text
            self._log("RECEIVED", f"from={remote} origin={origin} text={text!r}")
            print(f"[RECEIVED] {remote} -> clipboard updated")
            self._play_receive_alert()
        except ClipboardError as exc:
            self._log("ERROR", f"Clipboard set failed ({remote}): {exc}")

    def _clipboard_monitor_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                text = self.clipboard.get_text()
                if text and text != self.last_seen_local:
                    self.last_seen_local = text
                    if self.suppress_next_local == text:
                        self.suppress_next_local = None
                    else:
                        self._on_local_clipboard(text)
            except ClipboardError as exc:
                self._log("ERROR", f"Clipboard read failed: {exc}")
            time.sleep(self.poll_interval)

    def _on_local_clipboard(self, text: str) -> None:
        self._log("LOCAL_COPY", f"text={text!r}")
        for peer in self.peers:
            self._send_to_peer(peer, text)

    def _send_to_peer(self, peer: Peer, text: str) -> None:
        payload = {
            "type": "clipboard",
            "origin": self.node_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "text": text,
        }
        raw = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with socket.create_connection((peer.host, peer.port), timeout=2.0) as s:
                s.sendall(raw)
            self._log("SENT", f"to={peer.host}:{peer.port} text={text!r}")
        except OSError as exc:
            self._log("ERROR", f"Send failed to {peer.host}:{peer.port}: {exc}")

    def _log(self, event: str, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"[{timestamp}] {event}: {message}\n"
        with self.log_lock:
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(line)

    def _play_receive_alert(self) -> None:
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except RuntimeError as exc:
            self._log("ERROR", f"Alert sound failed: {exc}")


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

    args = parser.parse_args()

    if not (1 <= args.listen_port <= 65535):
        raise SystemExit("listen-port must be between 1 and 65535.")
    if args.poll_interval <= 0:
        raise SystemExit("poll-interval must be greater than 0.")

    app = ClipboardShareApp(
        listen_port=args.listen_port,
        peers=args.peer,
        log_file=Path(args.log_file),
        poll_interval=args.poll_interval,
    )
    app.run()


if __name__ == "__main__":
    main()