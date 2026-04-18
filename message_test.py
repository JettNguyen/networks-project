from src.messages import Message, serialize_message, create_handshake
import socket

# Replace with the peer you want to send to
TARGET_PEER_ID = 1001
TARGET_HOST = '127.0.0.1'
TARGET_PORT = 6001

# Your peer ID (sending peer)
MY_PEER_ID = 1002

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((TARGET_HOST, TARGET_PORT))

# Send handshake first
sock.sendall(create_handshake(MY_PEER_ID))

# Then send an actual message
msg = Message(msg_type=1, payload=b'Hello, peer 1001!')
sock.sendall(serialize_message(msg))

print(f"Sent message to peer {TARGET_PEER_ID}")

sock.close()