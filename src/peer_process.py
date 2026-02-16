import sys

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python peerProcess.py <peer_id>")
        sys.exit(1)

    peer_id = int(sys.argv[1])
    print(f"peerProcess started with peer_id={peer_id}")

if __name__ == "__main__":
    main()
