import os
import sys
import socket
import threading
import time
import random

from src.logger import get_peer_logger
from src.config import Config
from src.file_manager import FileManager
from src.messages import (
    handle_connection,
    create_handshake,
    serialize_message,
    Message,
)

# Message type constants
MSG_CHOKE = 0
MSG_UNCHOKE = 1
MSG_INTERESTED = 2
MSG_NOT_INTERESTED = 3
MSG_HAVE = 4
MSG_BITFIELD = 5
MSG_REQUEST = 6
MSG_PIECE = 7


class PeerState:
    def __init__(self, peer_id, num_pieces, cfg, file_manager):
        self.peer_id = peer_id
        self.num_pieces = num_pieces
        self.cfg = cfg
        self.file_manager = file_manager
        self.lock = threading.Lock()
        self.neighbor_sockets = {}
        self.neighbor_bitfields = {}
        self.interested_in_me = set()
        self.i_am_interested_in = set()
        self.choked_by_me = set()
        self.choking_me = set()
        self.preferred_neighbors = set()
        self.optimistic_unchoked = None
        self.download_bytes = {}
        self.requested_pieces = set()
        self.peer_has_file = {}
        self._self_complete = file_manager.has_complete_file()

    def send_to(self, peer_id, msg):
        with self.lock:
            sock = self.neighbor_sockets.get(peer_id)
        if sock:
            try:
                sock.sendall(serialize_message(msg))
            except Exception:
                pass

    def broadcast_have(self, piece_index):
        payload = piece_index.to_bytes(4, 'big')
        msg = Message(msg_type=MSG_HAVE, payload=payload)
        with self.lock:
            peers = list(self.neighbor_sockets.keys())
        for pid in peers:
            self.send_to(pid, msg)

    def all_peers_done(self):
        with self.lock:
            if not self._self_complete:
                return False
            all_peers = [p.peer_id for p in self.cfg.peers.peer_list if p.peer_id != self.peer_id]
            return all(self.peer_has_file.get(pid, False) for pid in all_peers)


def run_preferred_neighbor_scheduler(state, logger):
    k = state.cfg.common.number_of_preferred_neighbors
    interval = state.cfg.common.unchoking_interval

    while True:
        time.sleep(interval)

        with state.lock:
            interested = list(state.interested_in_me)

        if not interested:
            continue

        if state.file_manager.has_complete_file():
            new_preferred = set(random.sample(interested, min(k, len(interested))))
        else:
            with state.lock:
                rates = dict(state.download_bytes)
            interested_with_rates = [(pid, rates.get(pid, 0)) for pid in interested]
            random.shuffle(interested_with_rates)
            interested_with_rates.sort(key=lambda x: x[1], reverse=True)
            new_preferred = set(pid for pid, _ in interested_with_rates[:k])

        with state.lock:
            for pid in state.download_bytes:
                state.download_bytes[pid] = 0
            old_preferred = set(state.preferred_neighbors)
            state.preferred_neighbors = new_preferred

        logger.preferred_neighbors(sorted(new_preferred))

        for pid in new_preferred - old_preferred:
            with state.lock:
                state.choked_by_me.discard(pid)
            state.send_to(pid, Message(MSG_UNCHOKE, b''))

        with state.lock:
            opt = state.optimistic_unchoked
        for pid in old_preferred - new_preferred:
            if pid != opt:
                with state.lock:
                    state.choked_by_me.add(pid)
                state.send_to(pid, Message(MSG_CHOKE, b''))


def run_optimistic_unchoke_scheduler(state, logger):
    interval = state.cfg.common.optimistic_unchoking_interval

    while True:
        time.sleep(interval)

        with state.lock:
            candidates = [
                pid for pid in state.interested_in_me
                if pid in state.choked_by_me
            ]

        if not candidates:
            continue

        new_opt = random.choice(candidates)

        with state.lock:
            old_opt = state.optimistic_unchoked
            state.optimistic_unchoked = new_opt

        if old_opt is not None and old_opt != new_opt:
            with state.lock:
                is_preferred = old_opt in state.preferred_neighbors
            if not is_preferred:
                with state.lock:
                    state.choked_by_me.add(old_opt)
                state.send_to(old_opt, Message(MSG_CHOKE, b''))

        with state.lock:
            state.choked_by_me.discard(new_opt)
        state.send_to(new_opt, Message(MSG_UNCHOKE, b''))
        logger.optimistically_unchoked(new_opt)


def run_termination_checker(state, shutdown_event):
    while True:
        time.sleep(3)
        if state.all_peers_done():
            shutdown_event.set()
            break


def accept_connections(server_socket, logger, peer_id):
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
    if len(sys.argv) != 2:
        print("Usage: python peerProcess.py <peer_id>")
        sys.exit(1)
    peer_id = int(sys.argv[1])

    project_root = os.path.abspath(os.path.dirname(__file__))
    cfg = Config()

    if peer_id not in cfg.peers.peers:
        print(f"Error: Peer ID {peer_id} not found in PeerInfo.cfg")
        sys.exit(1)

    self_peer = cfg.peers.peers[peer_id]
    self_host = self_peer.host_name
    self_port = self_peer.port
    self_has_file = self_peer.has_file
    num_pieces = cfg.num_pieces()

    logger = get_peer_logger(peer_id, working_dir=project_root)
    print(f"peerProcess started (peer_id={peer_id}, port={self_port}, has_file={int(self_has_file)}) | peers={len(cfg.peers.peers)}, pieces={num_pieces}")

    peer_dir = os.path.join(project_root, f"peer_{peer_id}")
    os.makedirs(peer_dir, exist_ok=True)

    file_manager = FileManager(
        peer_id=peer_id,
        project_root=project_root,
        file_name=cfg.common.file_name,
        file_size=cfg.common.file_size,
        piece_size=cfg.common.piece_size,
        num_pieces=num_pieces,
    )

    if self_has_file:
        file_manager.load_initial_pieces()

    state = PeerState(
        peer_id=peer_id,
        num_pieces=num_pieces,
        cfg=cfg,
        file_manager=file_manager,
    )

    for p in cfg.peers.peer_list:
        state.peer_has_file[p.peer_id] = p.has_file

    smaller_peers = [p for p in cfg.peers.peer_list if p.peer_id < peer_id]
    for p in smaller_peers:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((p.host_name, p.port))
            logger.connect_to(p.peer_id)
            print(f"Connected to peer {p.peer_id} at {p.host_name}:{p.port}")
            sock.sendall(create_handshake(peer_id))
            threading.Thread(
                target=handle_connection,
                args=(sock, p.peer_id, logger, peer_id),
                daemon=True
            ).start()
        except Exception as e:
            print(f"Failed to connect to peer {p.peer_id}: {e}")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((self_host, self_port))
    server_socket.listen()
    print(f"Peer {peer_id} listening on {self_host}:{self_port}")

    threading.Thread(target=accept_connections, args=(server_socket, logger, peer_id), daemon=True).start()
    threading.Thread(target=run_preferred_neighbor_scheduler, args=(state, logger), daemon=True).start()
    threading.Thread(target=run_optimistic_unchoke_scheduler, args=(state, logger), daemon=True).start()

    shutdown_event = threading.Event()
    threading.Thread(target=run_termination_checker, args=(state, shutdown_event), daemon=True).start()

    try:
        shutdown_event.wait()
        print(f"Peer {peer_id}: all peers done. Shutting down.")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server_socket.close()


if __name__ == "__main__":
    main()