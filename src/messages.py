from dataclasses import dataclass
from typing import Optional

HEADER = b"P2PFILESHARINGPROJ"
ZERO_BITS = b'\x00' * 10
HANDSHAKE_LEN = 32

# Message types
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

# Low-level IO utilities
def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            raise ConnectionError("Connection closed")
        data += packet
    return data


# Handshake
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


# Message structure
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
    length = int.from_bytes(recv_exact(sock, 4), 'big')
    if length == 0:
        return Message(-1, b'')

    body = recv_exact(sock, length)
    return Message(body[0], body[1:])


def send_message(sock, message: Message):
    sock.sendall(serialize_message(message))


def message_name(msg_type: int) -> str:
    return _MESSAGE_NAMES.get(msg_type, f"unknown({msg_type})")


# Message constructors
def make_choke(): return Message(MSG_CHOKE, b'')
def make_unchoke(): return Message(MSG_UNCHOKE, b'')
def make_interested(): return Message(MSG_INTERESTED, b'')
def make_not_interested(): return Message(MSG_NOT_INTERESTED, b'')

def make_have(piece_index: int):
    return Message(MSG_HAVE, piece_index.to_bytes(4, 'big'))

def make_bitfield(bitfield: bytes):
    return Message(MSG_BITFIELD, bytes(bitfield))

def make_request(piece_index: int):
    return Message(MSG_REQUEST, piece_index.to_bytes(4, 'big'))

def make_piece(piece_index: int, data: bytes):
    return Message(MSG_PIECE, piece_index.to_bytes(4, 'big') + data)


# Parsing helpers
def parse_have(message: Message) -> int:
    return int.from_bytes(message.payload, 'big')


def parse_request(message: Message) -> int:
    return int.from_bytes(message.payload, 'big')


def parse_piece(message: Message):
    piece_index = int.from_bytes(message.payload[:4], 'big')
    return piece_index, message.payload[4:]


# Bitfield helpers
def bitfield_has_piece(bitfield: bytes, idx: int) -> bool:
    byte = idx // 8
    if byte >= len(bitfield):
        return False
    bit = 7 - (idx % 8)
    return bool(bitfield[byte] & (1 << bit))


def bitfield_set_piece(bitfield: bytearray, idx: int):
    byte = idx // 8
    bit = 7 - (idx % 8)
    bitfield[byte] |= (1 << bit)


def bitfield_missing_pieces(remote_bitfield: bytes, file_manager, num_pieces: int):
    return [
        i for i in range(num_pieces)
        if bitfield_has_piece(remote_bitfield, i)
        and not file_manager.has_piece(i)
    ]


def choose_piece_to_request(remote_bitfield: bytes, file_manager, num_pieces: int, requested: set):
    candidates = [
        i for i in range(num_pieces)
        if bitfield_has_piece(remote_bitfield, i)
        and not file_manager.has_piece(i)
        and i not in requested
    ]
    return min(candidates) if candidates else None


# Connection handler
def handle_connection(sock, neighbor_id, logger, peer_id, state):
    my_requested: set = set()

    def release_my_requests():
        """Return any in-flight piece reservations held by this connection."""
        with state.lock:
            state.requested_pieces -= my_requested
        my_requested.clear()

    try:
        if neighbor_id is None:
            handshake = recv_exact(sock, HANDSHAKE_LEN)
            remote_id = parse_handshake(handshake)
            sock.sendall(create_handshake(peer_id))
            logger.connect_from(remote_id)
        else:
            handshake = recv_exact(sock, HANDSHAKE_LEN)
            remote_id = parse_handshake(handshake)
            if neighbor_id != remote_id:
                raise ValueError("Peer ID mismatch")
            logger.connect_to(remote_id)

        # Register
        with state.lock:
            state.neighbor_sockets[remote_id] = sock
            state.choking_me.add(remote_id)
            state.choked_by_me.add(remote_id)

        # Send bitfield
        bf = state.file_manager.build_bitfield()
        send_message(sock, make_bitfield(bf))

        # Main loop
        while True:
            msg = receive_message(sock)
            if msg.msg_type == -1:
                continue

            # CHOKE
            if msg.msg_type == MSG_CHOKE:
                logger.choked_by(remote_id)
                with state.lock:
                    state.choking_me.add(remote_id)
                release_my_requests()

            # UNCHOKE
            elif msg.msg_type == MSG_UNCHOKE:
                logger.unchoked_by(remote_id)

                with state.lock:
                    state.choking_me.discard(remote_id)
                    has_bitfield = remote_id in state.bitfield_received
                    remote_bf = state.neighbor_bitfields.get(remote_id)

                    piece = None
                    if has_bitfield:
                        piece = choose_piece_to_request(
                            remote_bf, state.file_manager, state.num_pieces,
                            state.requested_pieces
                        )
                        if piece is not None:
                            state.requested_pieces.add(piece)
                            my_requested.add(piece)

                if piece is not None:
                    send_message(sock, make_request(piece))

            # INTERESTED
            elif msg.msg_type == MSG_INTERESTED:
                logger.received_interested(remote_id)
                with state.lock:
                    state.interested_in_me.add(remote_id)

            # NOT INTERESTED 
            elif msg.msg_type == MSG_NOT_INTERESTED:
                logger.received_not_interested(remote_id)
                with state.lock:
                    state.interested_in_me.discard(remote_id)

            # BITFIELD
            elif msg.msg_type == MSG_BITFIELD:
                with state.lock:
                    state.neighbor_bitfields[remote_id] = msg.payload
                    state.bitfield_received.add(remote_id)
                    if all(bitfield_has_piece(msg.payload, i) for i in range(state.num_pieces)):
                        state.peer_has_file[remote_id] = True

                wanted = bitfield_missing_pieces(
                    msg.payload,
                    state.file_manager,
                    state.num_pieces
                )

                send_message(sock,
                    make_interested() if wanted else make_not_interested()
                )

            # HAVE
            elif msg.msg_type == MSG_HAVE:
                idx = parse_have(msg)
                logger.received_have(remote_id, idx)

                with state.lock:
                    bf = state.neighbor_bitfields.get(remote_id)
                    if bf is not None:
                        bf = bytearray(bf)
                        bitfield_set_piece(bf, idx)
                        state.neighbor_bitfields[remote_id] = bytes(bf)

                        if all(bitfield_has_piece(bf, i) for i in range(state.num_pieces)):
                            state.peer_has_file[remote_id] = True

                if not state.file_manager.has_piece(idx):
                    send_message(sock, make_interested())

            # REQUEST
            elif msg.msg_type == MSG_REQUEST:
                idx = parse_request(msg)

                with state.lock:
                    is_choked = remote_id in state.choked_by_me

                if is_choked:
                    continue

                data = state.file_manager.read_piece(idx)
                send_message(sock, make_piece(idx, data))

            # PIECE
            elif msg.msg_type == MSG_PIECE:
                idx, data = parse_piece(msg)

                state.file_manager.write_piece(idx, data)

                with state.lock:
                    state.requested_pieces.discard(idx)
                    my_requested.discard(idx)
                    state.download_bytes[remote_id] = \
                        state.download_bytes.get(remote_id, 0) + len(data)

                num_owned = state.file_manager.num_pieces_owned()
                logger.downloaded_piece(remote_id, idx, num_owned)

                if state.file_manager.has_complete_file() and not state.file_assembled:
                    logger.complete_file()
                    try:
                        state.file_manager.assemble_file()
                        print(f"[PEER {peer_id}] File assembled successfully")
                    except Exception as e:
                        print(f"[PEER {peer_id}] Assembly failed: {e}")

                    with state.lock:
                        state.file_assembled = True
                        state.peer_has_file[peer_id] = True

                state.broadcast_have(idx)

                with state.lock:
                    has_bitfield = remote_id in state.bitfield_received
                    remote_bf = state.neighbor_bitfields.get(remote_id)
                    piece = None
                    if has_bitfield:
                        piece = choose_piece_to_request(
                            remote_bf,
                            state.file_manager,
                            state.num_pieces,
                            state.requested_pieces
                        )
                        if piece is not None:
                            state.requested_pieces.add(piece)
                            my_requested.add(piece)

                if piece is not None:
                    send_message(sock, make_request(piece))

    except Exception as e:
        logger._log(f"Connection error: {e}")
    finally:
        release_my_requests()
        sock.close()