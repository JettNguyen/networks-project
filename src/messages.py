from dataclasses import dataclass
from typing import Optional

HEADER = b"P2PFILESHARINGPROJ"
ZERO_BITS = b'\x00' * 10
HANDSHAKE_LEN = 32

# Message type constants
MSG_CHOKE = 0
MSG_UNCHOKE = 1
MSG_INTERESTED = 2
MSG_NOT_INTERESTED = 3
MSG_HAVE = 4
MSG_BITFIELD = 5
MSG_REQUEST = 6
MSG_PIECE = 7

_MESSAGE_NAMES = {
    MSG_CHOKE: "choke",
    MSG_UNCHOKE: "unchoke",
    MSG_INTERESTED: "interested",
    MSG_NOT_INTERESTED: "not_interested",
    MSG_HAVE: "have",
    MSG_BITFIELD: "bitfield",
    MSG_REQUEST: "request",
    MSG_PIECE: "piece",
}


def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            raise ConnectionError("Connection closed")
        data += packet
    return data


def _piece_index_to_bytes(piece_index: int) -> bytes:
    if piece_index < 0:
        raise ValueError("piece_index must be non-negative")
    return piece_index.to_bytes(4, 'big')


def _piece_index_from_bytes(payload: bytes, msg_name: str) -> int:
    if len(payload) != 4:
        raise ValueError(f"Invalid {msg_name} payload length: expected 4, got {len(payload)}")
    return int.from_bytes(payload, 'big')


def _bitfield_num_bytes(num_pieces: int) -> int:
    if num_pieces < 0:
        raise ValueError("num_pieces must be non-negative")
    return (num_pieces + 7) // 8

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
    if message.msg_type < 0 or message.msg_type > 255:
        raise ValueError(f"Invalid message type {message.msg_type}")

    length = 1 + len(message.payload)
    return (
        length.to_bytes(4, 'big') +
        message.msg_type.to_bytes(1, 'big') +
        message.payload
    )


def receive_message(sock) -> Message:
    length_bytes = recv_exact(sock, 4)
    length = int.from_bytes(length_bytes, 'big')

    if length < 0:
        raise ValueError(f"Invalid message length: {length}")

    if length == 0:
        return Message(-1, b'')

    body = recv_exact(sock, length)
    if not body:
        raise ValueError("Malformed message: empty body with nonzero length")

    msg_type = body[0]
    payload = body[1:]

    return Message(msg_type, payload)


def message_name(msg_type: int) -> str:
    return _MESSAGE_NAMES.get(msg_type, f"unknown({msg_type})")


def make_choke() -> Message:
    return Message(MSG_CHOKE, b'')


def make_unchoke() -> Message:
    return Message(MSG_UNCHOKE, b'')


def make_interested() -> Message:
    return Message(MSG_INTERESTED, b'')


def make_not_interested() -> Message:
    return Message(MSG_NOT_INTERESTED, b'')


def make_have(piece_index: int) -> Message:
    return Message(MSG_HAVE, _piece_index_to_bytes(piece_index))


def make_bitfield(bitfield: bytes) -> Message:
    return Message(MSG_BITFIELD, bytes(bitfield))


def make_request(piece_index: int) -> Message:
    return Message(MSG_REQUEST, _piece_index_to_bytes(piece_index))


def make_piece(piece_index: int, piece_data: bytes) -> Message:
    return Message(MSG_PIECE, _piece_index_to_bytes(piece_index) + piece_data)


def parse_have(message: Message) -> int:
    if message.msg_type != MSG_HAVE:
        raise ValueError(f"Expected HAVE message, got {message_name(message.msg_type)}")
    return _piece_index_from_bytes(message.payload, "have")


def parse_request(message: Message) -> int:
    if message.msg_type != MSG_REQUEST:
        raise ValueError(f"Expected REQUEST message, got {message_name(message.msg_type)}")
    return _piece_index_from_bytes(message.payload, "request")


def parse_piece(message: Message) -> tuple[int, bytes]:
    if message.msg_type != MSG_PIECE:
        raise ValueError(f"Expected PIECE message, got {message_name(message.msg_type)}")
    if len(message.payload) < 4:
        raise ValueError("Invalid piece payload length: expected >= 4")
    piece_index = int.from_bytes(message.payload[:4], 'big')
    piece_data = message.payload[4:]
    return piece_index, piece_data


def validate_message(message: Message):
    if message.msg_type == -1:
        return

    if message.msg_type in (MSG_CHOKE, MSG_UNCHOKE, MSG_INTERESTED, MSG_NOT_INTERESTED):
        if len(message.payload) != 0:
            raise ValueError(f"{message_name(message.msg_type)} payload must be empty")
        return

    if message.msg_type in (MSG_HAVE, MSG_REQUEST):
        if len(message.payload) != 4:
            raise ValueError(f"{message_name(message.msg_type)} payload must be 4 bytes")
        return

    if message.msg_type == MSG_BITFIELD:
        if len(message.payload) == 0:
            raise ValueError("bitfield payload must not be empty")
        return

    if message.msg_type == MSG_PIECE:
        if len(message.payload) < 4:
            raise ValueError("piece payload must include 4-byte index and data")
        return

    raise ValueError(f"Unknown message type: {message.msg_type}")


def send_message(sock, message: Message):
    validate_message(message)
    sock.sendall(serialize_message(message))


def bitfield_has_piece(bitfield: bytes, piece_index: int) -> bool:
    if piece_index < 0:
        return False
    byte_index = piece_index // 8
    if byte_index >= len(bitfield):
        return False
    bit_index = 7 - (piece_index % 8)
    return bool(bitfield[byte_index] & (1 << bit_index))


def bitfield_set_piece(bitfield: bytearray, piece_index: int):
    if piece_index < 0:
        raise ValueError("piece_index must be non-negative")
    byte_index = piece_index // 8
    if byte_index >= len(bitfield):
        raise ValueError("piece_index is out of range for this bitfield")
    bit_index = 7 - (piece_index % 8)
    bitfield[byte_index] |= (1 << bit_index)


def bitfield_missing_pieces(remote_bitfield: bytes, file_manager, num_pieces: int) -> list[int]:
    wanted = []
    for idx in range(num_pieces):
        if bitfield_has_piece(remote_bitfield, idx) and not file_manager.has_piece(idx):
            wanted.append(idx)
    return wanted


def choose_piece_to_request(remote_bitfield: bytes, file_manager, num_pieces: int, requested_pieces: Optional[set] = None) -> Optional[int]:
    requested = requested_pieces or set()
    candidates = [
        idx for idx in range(num_pieces)
        if bitfield_has_piece(remote_bitfield, idx)
        and not file_manager.has_piece(idx)
        and idx not in requested
    ]
    if not candidates:
        return None
    return min(candidates)


def handle_connection(sock, neighbor_id, logger, peer_id):
    """Handles sending/receiving messages with one peer."""
    try:
        handshake_data = recv_exact(sock, HANDSHAKE_LEN)
        remote_peer_id = parse_handshake(handshake_data)

        if isinstance(neighbor_id, int) and neighbor_id != remote_peer_id:
            raise ValueError(
                f"Handshake peer id mismatch: expected {neighbor_id}, got {remote_peer_id}"
            )

        logger.connect_from(remote_peer_id)

        # Current peerProcess behavior:
        # - outbound side sends handshake before starting handle_connection
        # - inbound side does not send before starting handle_connection
        # Reply with handshake only for inbound-accepted connections.
        if not isinstance(neighbor_id, int):
            sock.sendall(create_handshake(peer_id))

        logger._log(f"Peer {peer_id} established handshake with Peer {remote_peer_id}")

        while True:
            message = receive_message(sock)
            if message.msg_type == -1:
                continue

            validate_message(message)

            if message.msg_type == MSG_CHOKE:
                logger.choked_by(remote_peer_id)
            elif message.msg_type == MSG_UNCHOKE:
                logger.unchoked_by(remote_peer_id)
            elif message.msg_type == MSG_INTERESTED:
                logger.received_interested(remote_peer_id)
            elif message.msg_type == MSG_NOT_INTERESTED:
                logger.received_not_interested(remote_peer_id)
            elif message.msg_type == MSG_HAVE:
                piece_index = parse_have(message)
                logger.received_have(remote_peer_id, piece_index)
            elif message.msg_type == MSG_BITFIELD:
                logger._log(
                    f"Peer {peer_id} received bitfield ({len(message.payload)} bytes) "
                    f"from Peer {remote_peer_id}"
                )
            elif message.msg_type == MSG_REQUEST:
                piece_index = parse_request(message)
                logger._log(
                    f"Peer {peer_id} received request for piece {piece_index} "
                    f"from Peer {remote_peer_id}"
                )
            elif message.msg_type == MSG_PIECE:
                piece_index, piece_data = parse_piece(message)
                logger._log(
                    f"Peer {peer_id} received piece {piece_index} "
                    f"({len(piece_data)} bytes) from Peer {remote_peer_id}"
                )

            logger._log(
                f"Peer {peer_id} received message type {message_name(message.msg_type)} "
                f"from Peer {remote_peer_id}"
            )

    except Exception as e:
        logger._log(f"Connection error with Peer {neighbor_id}: {e}")
    finally:
        sock.close()


__all__ = [
    "HEADER",
    "ZERO_BITS",
    "HANDSHAKE_LEN",
    "MSG_CHOKE",
    "MSG_UNCHOKE",
    "MSG_INTERESTED",
    "MSG_NOT_INTERESTED",
    "MSG_HAVE",
    "MSG_BITFIELD",
    "MSG_REQUEST",
    "MSG_PIECE",
    "Message",
    "recv_exact",
    "create_handshake",
    "parse_handshake",
    "serialize_message",
    "receive_message",
    "message_name",
    "make_choke",
    "make_unchoke",
    "make_interested",
    "make_not_interested",
    "make_have",
    "make_bitfield",
    "make_request",
    "make_piece",
    "parse_have",
    "parse_request",
    "parse_piece",
    "validate_message",
    "send_message",
    "bitfield_has_piece",
    "bitfield_set_piece",
    "bitfield_missing_pieces",
    "choose_piece_to_request",
    "handle_connection",
]