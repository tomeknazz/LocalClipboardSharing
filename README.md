# Local Clipboard Sharing for Windows

Share your clipboard text with other computers on your local network. This tool offers both a headless command-line interface and a user-friendly graphical interface with automatic network discovery.

<img width="638" height="731" alt="image" src="https://github.com/user-attachments/assets/a962b0e8-3c83-4ba2-9976-4ccd3fb03e35" />

---

## Features

- **Dual Mode:** Run the application in either a headless CLI mode or with a full graphical user interface (GUI).
- **Automatic Peer Discovery:** Automatically scans the local network to find other devices running the application, making setup a breeze.
- **Manual Peer Management:** Add, edit, and remove peers directly through the GUI.
- **Active Peer Toggling:** Easily activate or deactivate clipboard sharing for specific peers without removing them from your list.
- **Real-time Status:** The GUI displays the connection status for each configured peer.
- **Event Logging:** All clipboard activities (local copy, sent, received) and system events are logged to a text file for a persistent history.
- **Audio Alerts:** Get an audible notification when new clipboard content is received from another peer.

## Requirements

- **OS:** Windows
- **Python:** 3.10+
- **Network:** All computers must be on the same local network. Your firewall must allow inbound/outbound traffic on the chosen TCP/UDP ports.

## Quick Start

### GUI Mode (Recommended)

1.  Run the application with the `--gui` flag.
    ```powershell
    python main.py --gui
    ```
2.  The application window will open. Click **Start**.
3.  The app will automatically begin discovering other devices on the network, which will appear in the "Discovered Peers" list.
4.  Select a device from the discovered list and click **Add Selected Peer**. It will be added to your main "Peers" list as inactive.
5.  To start sharing with a peer, select it from the main list and click **Toggle Active**.

### Headless (CLI) Mode

If you prefer to run without a GUI, you can specify peers manually.

**Example Setup:**
- PC1 IP: `192.168.1.10`
- PC2 IP: `192.168.1.20`

Run the following commands on each machine:

**On PC1:**
```powershell
python main.py --peer 192.168.1.20:5000
```

**On PC2:**
```powershell
python main.py --peer 192.168.1.10:5000
```

Now, any text copied on one machine will appear in the other's clipboard.

## Command-Line Options

```text
--gui               Run the application with the graphical user interface.
--listen-port       TCP port for clipboard sharing (default: 5000).
--peer              Remote peer in HOST:PORT format. Can be used multiple times.
--log-file          Path to the log file (default: clipboard_log.txt).
--poll-interval     Clipboard poll interval in seconds (default: 0.4).
```

## Firewall Configuration

For the application to function correctly, you must allow it through your firewall.
- **Clipboard Sharing (TCP):** Allow inbound/outbound traffic on the TCP port specified by `--listen-port` (default `5000`).
- **Discovery (UDP):** Allow inbound/outbound traffic on UDP port `5001` for the network discovery feature.

## Log File

The log file (`clipboard_log.txt` by default) records the following events, providing a persistent history of your clipboard activity:
- `SYSTEM`: Application start/stop events.
- `LOCAL_COPY`: Text copied on the local machine.
- `SENT`: Text successfully sent to a peer.
- `RECEIVED`: Text received from a peer.
- `ERROR`: Any errors that occur during operation.
