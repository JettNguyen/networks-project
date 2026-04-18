# P2P File Sharing Project
Developed by Dominic Ghizzoni, Jesus Lopez, Jett Nguyen, & Kelly Tran

## Peer process usage

Before starting, ensure `Common.cfg` and `PeerInfo.cfg` are in the project working directory.
The peer program is named `peerProcess` and takes a peer ID as its only argument.

1. Start peer processes in the order listed in `PeerInfo.cfg` (and on the hosts specified there).
2. Run each peer from the project working directory using its peer ID:
   - python peerProcess.py <peer_id>
   - Example: python peerProcess.py 1001

---

## Running Multiple Peers Locally

To test TCP connectivity between peers on the same machine:

---

### Step 1: Open two terminals

Make sure both terminals are in the project root (same directory as `peerProcess.py`).

---

### Terminal 1 (start Peer 1001)

Run:

```bash
python peerProcess.py 1001
```

You should see something like:

```text
peerProcess started (peer_id=1001, port=6008, has_file=1) | peers=2, pieces=10
Peer 1001 listening on localhost:6008
```

Keep this terminal running.

---

### Terminal 2 (start Peer 1002)

Run:

```bash
python peerProcess.py 1002
```

You should see something like:

```text
peerProcess started (peer_id=1002, port=6009, has_file=0) | peers=2, pieces=10
Connected to peer 1001 ...
```

---

## Logs

Each peer writes to its own log file in the project directory:

```text
log_peer_<peer_id>.log
```

Example:

```text
log_peer_1001.log
log_peer_1002.log
```

---

### To verify connections:

Run:

```bash
tail -n 10 log_peer_1001.log
tail -n 10 log_peer_1002.log
```

You should see entries similar to:

```text
[YYYY-MM-DD HH:MM:SS]: Peer 1002 makes a connection to Peer 1001.
[YYYY-MM-DD HH:MM:SS]: Peer 1001 accepted connection from ('127.0.0.1', <some_port>) (placeholder, handshake later)
```

---

### Stopping a peer

To stop a running peer process, press:

```text
CTRL + C
```

You should see:

```text
Shutting down...
```
