from dataclasses import dataclass
import os

HEADER = b"P2PFILESHARINGPROJ"
ZERO_BITS = b'\x00' * 10
HANDSHAKE_LEN = 32


def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            raise ConnectionError("Connection closed")
        data += packet
    return data


def create_handshake(peer_id: int) -> bytes:
    return HEADER + ZERO_BITS + peer_id.to_bytes(4, 'big')


def parse_handshake(data: bytes) -> int:
    if len(data) != HANDSHAKE_LEN:
        raise ValueError("Invalid handshake length")

    header = data[:18]
    zero_bits = data[18:28]
    peer_id_bytes = data[28:32]

    if header != HEADER:
        raise ValueError("Invalid header")

    if zero_bits != ZERO_BITS:
        raise ValueError("Invalid zero bits")

    return int.from_bytes(peer_id_bytes, 'big')


@dataclass
class Message:
    msg_type: int
    payload: bytes


def serialize_message(message: Message) -> bytes:
    length = 1 + len(message.payload)
    return (
        length.to_bytes(4, 'big') +
        message.msg_type.to_bytes(1, 'big') +
        message.payload
    )


def receive_message(sock) -> Message:
    length_bytes = recv_exact(sock, 4)
    length = int.from_bytes(length_bytes, 'big')

    body = recv_exact(sock, length)

    msg_type = body[0]
    payload = body[1:]

    return Message(msg_type, payload)


def handle_connection(sock, neighbor_id, logger, peer_id):
    """Handles sending/receiving messages with one peer."""
    try:
        handshake_data = recv_exact(sock, HANDSHAKE_LEN)
        remote_peer_id = parse_handshake(handshake_data)

        logger._log(
            f"Peer {peer_id} received handshake from Peer {remote_peer_id}"
        )

        sock.sendall(create_handshake(peer_id))

        while True:
            message = receive_message(sock)

            logger._log(
                f"Peer {peer_id} received message type {message.msg_type} "
                f"from Peer {remote_peer_id}"
            )

    except Exception as e:
        logger._log(f"Connection error with Peer {neighbor_id}: {e}")
    finally:
        sock.close()