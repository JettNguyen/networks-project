from dataclasses import dataclass
import logging
import os


def get_peer_logger(peer_id, working_dir):

    # Log file must be log_peer_[peerID].log in the working directory
    base_dir = os.path.abspath(working_dir)
    log_file = os.path.join(base_dir, f"log_peer_{peer_id}.log")

    # Create a dedicated logger instance for the peer
    logger = logging.getLogger(f"peer_{peer_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Avoid duplicate FileHandlers
    already_has_handler = False
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler) and os.path.abspath(getattr(h, "baseFilename", "")) == os.path.abspath(log_file):
            already_has_handler = True
            break

    # Attach a FileHandler to write log messages to its log file
    if not already_has_handler:
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