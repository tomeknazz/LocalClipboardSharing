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
from typing import Optional, List, Dict, Tuple


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

DISCOVERY_PORT = 5001
DISCOVERY_MAGIC = "clipboard-share-v1"
BROADCAST_INTERVAL = 5  # seconds
PEER_TIMEOUT = 15  # seconds


class ClipboardError(RuntimeError):
    pass


class WinClipboard:
    # ... (WinClipboard class remains the same)
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


@dataclass(frozen=True, eq=True)
class Peer:
    host: str
    port: int

class ClipboardShareApp:
    """
    Manages the core logic for clipboard sharing between peers.
    ...
    """
    def __init__(
        self,
        listen_port: int,
        peers: List[Peer],
        log_file: Path,
        poll_interval: float,
        gui_callback=None,
    ) -> None:
        self.listen_port = listen_port
        self.peers = peers
        self.log_file = log_file
        self.poll_interval = poll_interval
        self.node_id = str(uuid.uuid4())
        self.gui_callback = gui_callback

        self.clipboard = WinClipboard()
        self.stop_event = threading.Event()
        self.last_seen_local: Optional[str] = None
        self.suppress_next_local: Optional[str] = None
        self.log_lock = threading.Lock()
        self.peer_lock = threading.Lock()
        self.discovery_lock = threading.Lock()

        self.discovered_peers: Dict[Peer, float] = {}
        
        with self.peer_lock:
            self.connection_status: Dict[Peer, str] = {peer: "Disconnected" for peer in self.peers}
            self.active_peers = set(self.peers)

    def run(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log("SYSTEM", f"Started node {self.node_id} on port {self.listen_port}")
        
        server_thread = threading.Thread(target=self._server_loop, daemon=True)
        monitor_thread = threading.Thread(target=self._clipboard_monitor_loop, daemon=True)
        discovery_listener = threading.Thread(target=self._discovery_listener_loop, daemon=True)
        discovery_broadcaster = threading.Thread(target=self._discovery_broadcaster_loop, daemon=True)

        server_thread.start()
        monitor_thread.start()
        discovery_listener.start()
        discovery_broadcaster.start()

        if not self.gui_callback:
            # ... (headless mode remains the same)
            pass

    def stop(self):
        self.stop_event.set()
        self._log("SYSTEM", "Stopped")

    def _discovery_listener_loop(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind(("", DISCOVERY_PORT))
            s.settimeout(1.0)

            while not self.stop_event.is_set():
                try:
                    data, addr = s.recvfrom(1024)
                except socket.timeout:
                    continue
                
                try:
                    payload = json.loads(data.decode("utf-8"))
                    if payload.get("magic") != DISCOVERY_MAGIC or payload.get("node_id") == self.node_id:
                        continue
                    
                    peer = Peer(host=addr[0], port=payload["port"])
                    
                    with self.discovery_lock:
                        is_new = peer not in self.discovered_peers
                        self.discovered_peers[peer] = time.time()

                    if is_new and self.gui_callback:
                        self.gui_callback("UPDATE_DISCOVERED_PEERS", None)

                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

    def _discovery_broadcaster_loop(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            message = json.dumps({
                "magic": DISCOVERY_MAGIC,
                "node_id": self.node_id,
                "port": self.listen_port,
            }).encode("utf-8")

            while not self.stop_event.is_set():
                s.sendto(message, ('<broadcast>', DISCOVERY_PORT))
                
                # Prune stale discovered peers
                with self.discovery_lock:
                    now = time.time()
                    stale_peers = [p for p, t in self.discovered_peers.items() if now - t > PEER_TIMEOUT]
                    changed = bool(stale_peers)
                    for p in stale_peers:
                        del self.discovered_peers[p]
                
                if changed and self.gui_callback:
                    self.gui_callback("UPDATE_DISCOVERED_PEERS", None)

                time.sleep(BROADCAST_INTERVAL)
    
    def get_discovered_peers(self) -> List[Peer]:
        with self.discovery_lock:
            # Exclude peers that are already in the main list
            with self.peer_lock:
                return [p for p in self.discovered_peers if p not in self.peers]

    def add_peer(self, peer: Peer, is_active: bool = True):
        with self.peer_lock:
            if peer not in self.peers:
                self.peers.append(peer)
                self.connection_status[peer] = "Disconnected"
                if is_active:
                    self.active_peers.add(peer)
                if self.gui_callback:
                    self.gui_callback("UPDATE_PEERS", None)
                return True
            return False

    # ... (the rest of the ClipboardShareApp class remains the same)
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
            if self.gui_callback:
                self.gui_callback("RECEIVED", f"{remote} -> clipboard updated")
            else:
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
        with self.peer_lock:
            peers_to_send = list(self.active_peers)
        for peer in peers_to_send:
            self._send_to_peer(peer, text)

    def _send_to_peer(self, peer: Peer, text: str) -> None:
        payload = {
            "type": "clipboard",
            "origin": self.node_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "text": text,
        }
        raw = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        status_to_set = "Connected"
        try:
            with socket.create_connection((peer.host, peer.port), timeout=2.0) as s:
                s.sendall(raw)
            self._log("SENT", f"to={peer.host}:{peer.port} text={text!r}")
        except OSError as exc:
            self._log("ERROR", f"Send failed to {peer.host}:{peer.port}: {exc}")
            status_to_set = f"Failed: {exc}"
        
        with self.peer_lock:
            self.connection_status[peer] = status_to_set
            
        if self.gui_callback:
            self.gui_callback("UPDATE_STATUS", None)

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

    def remove_peer(self, peer_to_remove: Peer):
        with self.peer_lock:
            self.peers = [p for p in self.peers if p != peer_to_remove]
            self.active_peers.discard(peer_to_remove)
            self.connection_status.pop(peer_to_remove, None)
        if self.gui_callback:
            self.gui_callback("UPDATE_PEERS", None)

    def update_peer(self, old_peer: Peer, new_peer: Peer):
        with self.peer_lock:
            if old_peer in self.peers:
                index = self.peers.index(old_peer)
                self.peers[index] = new_peer
                
                self.connection_status.pop(old_peer, None)
                self.connection_status[new_peer] = "Disconnected"
                
                if old_peer in self.active_peers:
                    self.active_peers.remove(old_peer)
                    self.active_peers.add(new_peer)

        if self.gui_callback:
            self.gui_callback("UPDATE_PEERS", None)

    def toggle_peer_active(self, peer: Peer):
        with self.peer_lock:
            if peer in self.active_peers:
                self.active_peers.remove(peer)
            else:
                self.active_peers.add(peer)
        if self.gui_callback:
            self.gui_callback("UPDATE_PEERS", None)

    def is_peer_active(self, peer: Peer) -> bool:
        with self.peer_lock:
            return peer in self.active_peers

    def get_peer_info_for_gui(self) -> List[Tuple[Peer, str, bool]]:
        with self.peer_lock:
            return [
                (p, self.connection_status.get(p, "N/A"), p in self.active_peers)
                for p in self.peers
            ]

