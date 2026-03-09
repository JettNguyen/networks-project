import os
import sys
import socket
import threading
import time
from src.logger import get_peer_logger
from src.messages import (
    handle_connection,
    create_handshake
)
from src.config import Config


def accept_connections(server_socket, logger, peer_id):
    """Accept incoming TCP connections and log them (midpoint skeleton)."""
    while True:
        conn, addr = server_socket.accept()

        logger._log(f"Peer {peer_id} accepted connection from {addr}")

        neighbor_id = addr

        threading.Thread(
            target=handle_connection,
            args=(conn, neighbor_id, logger, peer_id),
            daemon=True
        ).start()


def main():

    # peerProcess takes peer ID as its parameter
    if len(sys.argv) != 2:
        print("Usage: python peerProcess.py <peer_id>")
        sys.exit(1)
    peer_id = int(sys.argv[1])

    # All executables and configuration files for running peer processes must be in the working project directory
    project_root = os.path.abspath(os.path.dirname(__file__))

    # Load configuration (Common.cfg + PeerInfo.cfg)
    cfg = Config()

    # Validate that this peer_id exists in PeerInfo.cfg
    if peer_id not in cfg.peers.peers:
        print(f"Error: Peer ID {peer_id} not found in PeerInfo.cfg")
        sys.exit(1)

    # Extract this peer's configuration
    self_peer = cfg.peers.peers[peer_id]
    self_host = self_peer.host_name
    self_port = self_peer.port
    self_has_file = self_peer.has_file
    
    # Useful derived values
    total_peers = len(cfg.peers.peers)
    num_pieces = cfg.num_pieces()

    # Each peer writes its log into the log file ‘log_peer_[peerID].log’ at the working directory
    logger = get_peer_logger(peer_id, working_dir=project_root)

    print(
        f"peerProcess started (peer_id={peer_id}, port={self_port}, "
        f"has_file={int(self_has_file)}) | peers={total_peers}, pieces={num_pieces}"
    )

    # Each peer stores files in its own directory: peer_<peer_id>/
    peer_dir = os.path.join(project_root, f"peer_{peer_id}")
    os.makedirs(peer_dir, exist_ok=True)

    # Neighbor connections (peer_id -> socket)
    neighbors = {}

    # Determine peers with smaller peer IDs (we initiate connection to them)
    smaller_peers = [
        p for p in cfg.peers.peer_list
        if p.peer_id < peer_id
    ]

    # Connect to all peers that started before me (smaller peer_id)
    for p in smaller_peers:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((p.host_name, p.port))

            neighbors[p.peer_id] = sock

            logger.connect_to(p.peer_id)

            print(f"Connected to peer {p.peer_id} at {p.host_name}:{p.port}")

            # Send handshake immediately after connection
            sock.sendall(create_handshake(peer_id))

            threading.Thread(
                target=handle_connection,
                args=(sock, p.peer_id, logger, peer_id),
                daemon=True
            ).start()

        except Exception as e:
            print(f"Failed to connect to peer {p.peer_id} at {p.host_name}:{p.port}: {e}")

    # Create TCP server socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((self_host, self_port))
    server_socket.listen()

    # Start server accept thread
    accept_thread = threading.Thread(
        target=accept_connections,
        args=(server_socket, logger, peer_id),
        daemon=True
    )
    accept_thread.start()

    print(f"Peer {peer_id} listening on {self_host}:{self_port}")

    # Keep process alive (temporary for midpoint testing)
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()