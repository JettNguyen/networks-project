from dataclasses import dataclass
from pathlib import Path

@dataclass
class CommonConfig:
    number_of_preferred_neighbors: int
    unchoking_interval: int
    optimistic_unchoking_interval: int
    file_name: str
    file_size: int
    piece_size: int
    
    @classmethod
    def from_file(cls, filepath):
        # load and parse the main config file
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Common.cfg not found at {filepath}")
        
        config = {}
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    config[parts[0]] = parts[1]
        
        # verify required parameters are set in config
        required = {
            'NumberOfPreferredNeighbors', 'UnchokingInterval', 'OptimisticUnchokingInterval', 'FileName', 'FileSize', 'PieceSize'
        }
        missing = required - set(config.keys())
        if missing:
            raise ValueError(f"Missing config keys: {', '.join(sorted(missing))}")
        
        # parse and convert config values to proper types
        try:
            return cls(
                number_of_preferred_neighbors=int(config['NumberOfPreferredNeighbors']),
                unchoking_interval=int(config['UnchokingInterval']),
                optimistic_unchoking_interval=int(config['OptimisticUnchokingInterval']),
                file_name=config['FileName'],
                file_size=int(config['FileSize']),
                piece_size=int(config['PieceSize'])
            )
        except ValueError as e:
            raise ValueError(f"Invalid config value: {e}")

@dataclass
class PeerInfo:
    peer_id: int
    host_name: str
    port: int
    has_file: bool

class PeerInfoConfig:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"PeerInfo.cfg not found at {self.filepath}")
        
        self.peers = {}
        self.peer_list = []
        self._parse()
    
    def _parse(self):
        # read peer info line by line and build peer registry
        with open(self.filepath) as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split()
                if len(parts) < 4:
                    raise ValueError(f"Line {line_no}: expected at least 4 fields")
                
                try:
                    peer_id = int(parts[0])
                    hostname = parts[1]
                    port = int(parts[2])
                    has_file = bool(int(parts[3]))
                except (ValueError, IndexError) as e:
                    raise ValueError(f"Line {line_no}: invalid peer entry - {e}")
                
                peer = PeerInfo(peer_id, hostname, port, has_file)
                self.peers[peer_id] = peer
                self.peer_list.append(peer)
    
    def get_peer(self, peer_id):
        # lookup peer by id
        return self.peers.get(peer_id)
    
    def get_all(self):
        # return all peers in order
        return self.peer_list
    
    def with_file(self):
        # return peers with complete file
        return [p for p in self.peer_list if p.has_file]
    
    def __len__(self):
        return len(self.peer_list)
    
    def __iter__(self):
        return iter(self.peer_list)

class Config:
    # loads both common and peer info
    def __init__(self, common_cfg="Common.cfg", peer_info_cfg="PeerInfo.cfg"):
        self.common = CommonConfig.from_file(common_cfg)
        self.peers = PeerInfoConfig(peer_info_cfg)
    
    def get_peer(self, peer_id):
        # get peer by id
        return self.peers.get_peer(peer_id)
    
    def get_all_peers(self):
        # get list of all peers in network
        return self.peers.get_all()
    
    def num_pieces(self):
        # calculate total number of pieces in the file
        # uses ceiling division to account for partial last piece
        return (self.common.file_size + self.common.piece_size - 1) // self.common.piece_size
