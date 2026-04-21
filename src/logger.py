from dataclasses import dataclass
import logging
import os
from typing import Iterable


def get_peer_logger(peer_id, working_dir):
    peer_id = int(peer_id)

    # Log file must be log_peer_[peerID].log in the working directory
    base_dir = os.path.abspath(working_dir)
    os.makedirs(base_dir, exist_ok=True)
    log_file = os.path.join(base_dir, f"log_peer_{peer_id}.log")

    # Create a dedicated logger instance for the peer
    logger = logging.getLogger(f"peer_{peer_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handlers_to_remove = []
    has_correct_handler = False

    # For each file handler, verify that it points to the correct log file
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler):
            if os.path.abspath(getattr(h, "baseFilename", "")) == os.path.abspath(log_file):
                has_correct_handler = True

            # Otherwise, remove the stale handler before attaching the correct one
            else:
                handlers_to_remove.append(h)

    for h in handlers_to_remove:
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    # Attach a FileHandler to write log messages to its log file
    if not has_correct_handler:
        handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")

        # Add the required [Time] prefix (date, hour, minute, sec) to every log message automatically
        handler.setFormatter(logging.Formatter(
            fmt="[%(asctime)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)

    # Return a helper with the project log functions
    return PeerLogger(peer_id=peer_id, _logger=logger)


@dataclass
class PeerLogger:
    peer_id: int
    _logger: logging.Logger

    # Log the message body
    def _log(self, msg):
        self._logger.info(msg)

    # Whenever a peer makes a TCP connection to other peer, it generates the following log:
    # [Time]: Peer [peer_ID 1] makes a connection to Peer [peer_ID 2].
    def connect_to(self, peer_id2):
        self._log(f"Peer {self.peer_id} makes a connection to Peer {peer_id2}.")

    # Whenever a peer is connected from another peer, it generates the following log:
    # [Time]: Peer [peer_ID 1] is connected from Peer [peer_ID 2].
    def connect_from(self, peer_id2):
        self._log(f"Peer {self.peer_id} is connected from Peer {peer_id2}.")

    # Whenever a peer changes its preferred neighbors, it generates the following log:
    # [Time]: Peer [peer_ID] has the preferred neighbors [preferred neighbor ID list].
    def preferred_neighbors(self, neighbor_ids):
        # [preferred neighbor list] is the list of peer IDs separated by comma ','
        neighbor_list = ", ".join(str(x) for x in neighbor_ids)
        self._log(f"Peer {self.peer_id} has the preferred neighbors [{neighbor_list}].")

    # Whenever a peer changes its optimistically unchoked neighbor, it generates the following log:
    # [Time]: Peer [peer_ID] has the optimistically unchoked neighbor [optimistically unchoked neighbor ID].
    def optimistically_unchoked(self, neighbor_id):
        self._log(f"Peer {self.peer_id} has the optimistically unchoked neighbor [{neighbor_id}].")

    # Whenever a peer is unchoked by a neighbor (a peer receives an unchoking message from a neighbor), it generates the following log:
    # [Time]: Peer [peer_ID 1] is unchoked by [peer_ID 2].
    def unchoked_by(self, peer_id2):
        self._log(f"Peer {self.peer_id} is unchoked by {peer_id2}.")

    # Whenever a peer is choked by a neighbor (which means when a peer receives a choking message from a neighbor), it generates the following log:
    # [Time]: Peer [peer_ID 1] is choked by [peer_ID 2].
    def choked_by(self, peer_id2):
        self._log(f"Peer {self.peer_id} is choked by {peer_id2}.")

    # Whenever a peer receives a ‘have’ message, it generates the following log:
    # [Time]: Peer [peer_ID 1] received the ‘have’ message from [peer_ID 2] for the piece [piece index].
    def received_have(self, peer_id2, piece_index):
        self._log(f"Peer {self.peer_id} received the 'have' message from {peer_id2} for the piece {piece_index}.")

    # Whenever a peer receives an ‘interested’ message, it generates the following log:
    # [Time]: Peer [peer_ID 1] received the ‘interested’ message from [peer_ID 2].
    def received_interested(self, peer_id2):
        self._log(f"Peer {self.peer_id} received the 'interested' message from {peer_id2}.")

    # Whenever a peer receives a ‘not interested’ message, it generates the following log:
    # [Time]: Peer [peer_ID 1] received the ‘not interested’ message from [peer_ID 2].
    def received_not_interested(self, peer_id2):
        self._log(f"Peer {self.peer_id} received the 'not interested' message from {peer_id2}.")

    # Whenever a peer finishes downloading a piece, it generates the following log:
    # [Time]: Peer [peer_ID 1] has downloaded the piece [piece index] from [peer_ID 2].
    # Now the number of pieces it has is [number of pieces].
    def downloaded_piece(self, peer_id2, piece_index, num_pieces):
        self._log(
            f"Peer {self.peer_id} has downloaded the piece {piece_index} from {peer_id2}. Now the number of pieces it has is {num_pieces}."
        )

    # Whenever a peer downloads the complete file, it generates the following log:
    # [Time]: Peer [peer_ID] has downloaded the complete file.
    def downloaded_file(self):
        self._log(f"Peer {self.peer_id} has downloaded the complete file.")