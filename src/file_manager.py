import os
import threading


class FileManager:
    def __init__(self, peer_id, project_root, file_name, file_size, piece_size, num_pieces):
        self.peer_id = peer_id
        self.file_name = file_name
        self.file_size = file_size
        self.piece_size = piece_size
        self.num_pieces = num_pieces
        self.peer_dir = os.path.join(project_root, f"peer_{peer_id}")
        os.makedirs(self.peer_dir, exist_ok=True)
        self._lock = threading.Lock()

    def piece_path(self, piece_index):
        return os.path.join(self.peer_dir, f"piece_{piece_index}.bin")

    def has_piece(self, piece_index):
        return os.path.exists(self.piece_path(piece_index))

    def write_piece(self, piece_index, data):
        with self._lock:
            with open(self.piece_path(piece_index), 'wb') as f:
                f.write(data)

    def read_piece(self, piece_index):
        path = self.piece_path(piece_index)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Piece {piece_index} not found")
        with open(path, 'rb') as f:
            return f.read()

    def load_initial_pieces(self):
        src_file = os.path.join(self.peer_dir, self.file_name)
        if not os.path.exists(src_file):
            raise FileNotFoundError(
                f"Peer {self.peer_id} is marked as having the file but '{src_file}' was not found."
            )
        with open(src_file, 'rb') as f:
            for i in range(self.num_pieces):
                if not self.has_piece(i):
                    chunk = f.read(self.piece_size)
                    if chunk:
                        self.write_piece(i, chunk)

    def assemble_file(self):
        output_path = os.path.join(self.peer_dir, self.file_name)
        with self._lock:
            with open(output_path, 'wb') as out:
                for i in range(self.num_pieces):
                    out.write(self.read_piece(i))

    def build_bitfield(self):
        num_bytes = (self.num_pieces + 7) // 8
        bitfield = bytearray(num_bytes)
        for i in range(self.num_pieces):
            if self.has_piece(i):
                byte_index = i // 8
                bit_index = 7 - (i % 8)
                bitfield[byte_index] |= (1 << bit_index)
        return bitfield

    def pieces_owned(self):
        return [i for i in range(self.num_pieces) if self.has_piece(i)]

    def num_pieces_owned(self):
        return sum(1 for i in range(self.num_pieces) if self.has_piece(i))

    def has_complete_file(self):
        return all(self.has_piece(i) for i in range(self.num_pieces))