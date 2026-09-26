import os
import json
import random
import string
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / ".emergency_mesh"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_DB_FILE = DEFAULT_CONFIG_DIR / "mesh.db"

DEFAULT_TCP_PORT = 9876
DEFAULT_UDP_PORT = 9877
DEFAULT_CHAT_TTL = 5
DEFAULT_SOS_TTL = 8
DEFAULT_SOS_PROXIMITY_RADIUS = 6  # Default 6 meters proximity threshold
MAX_PACKET_SIZE = 65536  # 64 KB limit
PEER_EXPIRY_SECONDS = 30
BEACON_INTERVAL_SECONDS = 5

class Config:
    def __init__(self, config_dir=None, node_id_override=None, port_override=None):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.db_path = self.config_dir / "mesh.db"

        self.tcp_port = port_override or DEFAULT_TCP_PORT
        self.udp_port = DEFAULT_UDP_PORT
        if port_override:
            self.udp_port = port_override + 100

        self.sos_proximity_radius = DEFAULT_SOS_PROXIMITY_RADIUS
        self.node_id = node_id_override
        self.load_or_create()

        if node_id_override:
            self.node_id = node_id_override

    def generate_node_id(self):
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"RESCUE-{suffix}"

    def load_or_create(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not self.node_id:
                        self.node_id = data.get("node_id")
                    self.sos_proximity_radius = data.get("sos_proximity_radius", DEFAULT_SOS_PROXIMITY_RADIUS)
            except Exception:
                pass

        if not self.node_id:
            self.node_id = self.generate_node_id()

        self.save()

    def save(self):
        data = {
            "node_id": self.node_id,
            "tcp_port": self.tcp_port,
            "udp_port": self.udp_port,
            "sos_proximity_radius": self.sos_proximity_radius
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
