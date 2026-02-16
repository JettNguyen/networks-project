# P2P File Sharing Project

## Peer process usage
Before starting, ensure `Common.cfg` and `PeerInfo.cfg` are in the project working directory.
The peer program is named `peerProcess` and takes a peer ID as its only argument.

1. Start peer processes in the order listed in `PeerInfo.cfg` (and on the hosts specified there).
2. Run each peer from the project working directory using its peer ID:
   - python peerProcess.py <peer_id>
   - Example: python peerProcess.py 1001