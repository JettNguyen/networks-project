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
    make_have,
    Message,
    MSG_CHOKE,
    MSG_UNCHOKE,
    bitfield_has_piece,
)


# Peer State
class PeerState:
    def __init__(self, peer_id, num_pieces, cfg, file_manager):
        self.peer_id = peer_id
        self.num_pieces = num_pieces
        self.cfg = cfg
        self.file_manager = file_manager

        self.lock = threading.Lock()

        self.neighbor_sockets = {}
        self.neighbor_bitfields = {}
        self.bitfield_received = set()

        self.interested_in_me = set()

        self.choked_by_me = set()
        self.choking_me = set()

        self.preferred_neighbors = set()
        self.optimistic_unchoked = None

        self.download_bytes = {}
        self.requested_pieces = set()

        self.peer_has_file = {}
        self.file_assembled = False

    def send_to(self, peer_id, msg):
        with self.lock:
            sock = self.neighbor_sockets.get(peer_id)

        if sock:
            try:
                sock.sendall(serialize_message(msg))
            except Exception:
                pass

    def broadcast_have(self, piece_index):
        with self.lock:
            sockets = dict(self.neighbor_sockets)
        for pid, sock in sockets.items():
            try:
                sock.sendall(serialize_message(make_have(piece_index)))
            except Exception:
                pass

    def all_peers_done(self):
        with self.lock:
            if not self.file_assembled:
                return False

            peers = [
                p.peer_id for p in self.cfg.peers.peer_list
                if p.peer_id != self.peer_id
            ]
            for p in peers:
                if self.peer_has_file.get(p, False):
                    continue
                bf = self.neighbor_bitfields.get(p)
                if bf is not None and all(
                    bitfield_has_piece(bf, i) for i in range(self.num_pieces)
                ):
                    self.peer_has_file[p] = True
                    continue
                return False
            return True


# Scheduler
def run_preferred_neighbor_scheduler(state, logger, shutdown_event):
    k = state.cfg.common.number_of_preferred_neighbors
    interval = state.cfg.common.unchoking_interval

    while not shutdown_event.is_set():
        time.sleep(interval)

        with state.lock:
            interested = list(state.interested_in_me)
            rates = dict(state.download_bytes)
            state.download_bytes = {}

        if not interested:
            continue

        random.shuffle(interested)
        ranked = sorted(interested, key=lambda p: rates.get(p, 0), reverse=True)
        new_pref = set(ranked[:k])

        with state.lock:
            old_pref = set(state.preferred_neighbors)
            state.preferred_neighbors = new_pref

        logger.preferred_neighbors(sorted(new_pref))

        # UNCHOKE new
        for pid in new_pref - old_pref:
            with state.lock:
                state.choked_by_me.discard(pid)
            state.send_to(pid, Message(MSG_UNCHOKE, b''))

        # CHOKE removed
        for pid in old_pref - new_pref:
            with state.lock:
                state.choked_by_me.add(pid)
            state.send_to(pid, Message(MSG_CHOKE, b''))


def run_optimistic_unchoke_scheduler(state, logger, shutdown_event):
    interval = state.cfg.common.optimistic_unchoking_interval

    while not shutdown_event.is_set():
        time.sleep(interval)

        with state.lock:
            candidates = [
                p for p in state.interested_in_me
                if p in state.choked_by_me
            ]

        if not candidates:
            continue

        new_opt = random.choice(candidates)

        with state.lock:
            old_opt = state.optimistic_unchoked
            state.optimistic_unchoked = new_opt

        logger.optimistically_unchoked(new_opt)

        if old_opt is not None:
            with state.lock:
                if old_opt not in state.preferred_neighbors:
                    state.choked_by_me.add(old_opt)
            state.send_to(old_opt, Message(MSG_CHOKE, b''))

        with state.lock:
            state.choked_by_me.discard(new_opt)

        state.send_to(new_opt, Message(MSG_UNCHOKE, b''))


def run_termination_checker(state, shutdown_event):
    while not shutdown_event.is_set():
        time.sleep(2)
        if state.all_peers_done():
            shutdown_event.set()
            break


# Accept Thread
def accept_connections(server_socket, logger, peer_id, state, shutdown_event):
    server_socket.settimeout(1.0)

    print("[ACCEPT THREAD STARTED]")

    while not shutdown_event.is_set():
        try:
            conn, addr = server_socket.accept()

            print(f"[ACCEPT] {addr}")

            threading.Thread(
                target=handle_connection,
                args=(conn, None, logger, peer_id, state),
                daemon=True
            ).start()

        except socket.timeout:
            continue
        except OSError:
            break
        except Exception as e:
            if not shutdown_event.is_set():
                print(f"[ACCEPT ERROR] {e}")


def main():
    peer_id = int(sys.argv[1])

    project_root = os.path.dirname(__file__)
    cfg = Config()

    self_peer = cfg.peers.peers[peer_id]

    file_manager = FileManager(
        peer_id,
        project_root,
        cfg.common.file_name,
        cfg.common.file_size,
        cfg.common.piece_size,
        cfg.num_pieces()
    )

    if self_peer.has_file:
        file_manager.load_initial_pieces()

    state = PeerState(peer_id, cfg.num_pieces(), cfg, file_manager)

    with state.lock:
        for p in cfg.peers.peer_list:
            if p.has_file:
                state.peer_has_file[p.peer_id] = True
        if self_peer.has_file:
            state.file_assembled = True

    logger = get_peer_logger(peer_id, project_root)

    shutdown_event = threading.Event()

    # Connect to earlier peers
    for p in cfg.peers.peer_list:
        if p.peer_id < peer_id:
            try:
                sock = socket.socket()
                sock.connect((p.host_name, p.port))
                sock.sendall(create_handshake(peer_id))

                threading.Thread(
                    target=handle_connection,
                    args=(sock, p.peer_id, logger, peer_id, state),
                    daemon=True
                ).start()

            except Exception as e:
                print(f"connect error {p.peer_id}: {e}")

    # Server
    server_socket = socket.socket()
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_socket.bind((self_peer.host_name, self_peer.port))
    server_socket.listen()

    print(f"Peer {peer_id} listening on {self_peer.host_name}:{self_peer.port}")

    threading.Thread(
        target=accept_connections,
        args=(server_socket, logger, peer_id, state, shutdown_event),
        daemon=True
    ).start()

    threading.Thread(
        target=run_preferred_neighbor_scheduler,
        args=(state, logger, shutdown_event),
        daemon=True
    ).start()

    threading.Thread(
        target=run_optimistic_unchoke_scheduler,
        args=(state, logger, shutdown_event),
        daemon=True
    ).start()

    threading.Thread(
        target=run_termination_checker,
        args=(state, shutdown_event),
        daemon=True
    ).start()

    # Shutdown
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down...")
        shutdown_event.set()

    try:
        server_socket.close()
    except:
        pass


if __name__ == "__main__":
    main()