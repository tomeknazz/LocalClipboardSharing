# Local Clipboard Sharing (Windows)

Share **text clipboard content** between two (or more) Windows computers on the same local network.

The app:
- Watches local clipboard text (e.g., copied with `Ctrl+C`)
- Sends updates to configured peers over TCP
- Updates clipboard on receiving machines
- Logs local/sent/received/error events to a `.txt` log file on each machine
- Plays a Windows alert sound when remote clipboard content is received

## Requirements

- Windows
- Python 3.10+ (works with standard library only, no extra packages)
- Network access between PCs on chosen TCP port (default `5000`)

## Quick Start

Put `main.py` on both computers and run one instance on each.

### Example setup

- PC1 IP: `192.168.1.10`
- PC2 IP: `192.168.1.20`

Run:

**PC1**
```powershell
python main.py --listen-port 5000 --peer 192.168.1.20:5000 --log-file clipboard_log_pc1.txt
```

**PC2**
```powershell
python main.py --listen-port 5000 --peer 192.168.1.10:5000 --log-file clipboard_log_pc2.txt
```

## CLI Options

```text
--listen-port       TCP port to listen on (default: 5000)
--peer              Remote peer in HOST:PORT format (repeatable)
--log-file          Path to local log file (default: clipboard_log.txt)
--poll-interval     Clipboard poll interval in seconds (default: 0.4)
```

Example with multiple peers:

```powershell
python main.py --peer 192.168.1.20:5000 --peer 192.168.1.30:5000
```

## Firewall Note

Allow inbound TCP traffic on your chosen port (default `5000`) in Windows Firewall on each machine.

## Log File

The log file records:
- `LOCAL_COPY`
- `SENT`
- `RECEIVED`
- `ERROR`
- `SYSTEM`

This gives you a persistent clipboard history on each PC.
