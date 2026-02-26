import os
import sys
from src.logger import get_peer_logger

def main():

    # peerProcess takes peer ID as its parameter
    if len(sys.argv) != 2:
        print("Usage: python peerProcess.py <peer_id>")
        sys.exit(1)
    peer_id = int(sys.argv[1])

    # All executables and configuration files for running peer processes must be in the working project directory
    project_root = os.path.abspath(os.path.dirname(__file__))

    # Each peer writes its log into the log file ‘log_peer_[peerID].log’ at the working directory
    log = get_peer_logger(peer_id, working_dir=project_root)

    print(f"peerProcess started with peer_id={peer_id}")


if __name__ == "__main__":
    main()
