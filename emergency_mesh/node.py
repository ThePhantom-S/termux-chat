import asyncio
import time
from .config import Config
from .storage import Storage
from .transport import Transport
from .discovery import Discovery
from .router import Router
from .gps import get_location
from .protocol import create_chat_message, create_broadcast_message, create_sos_message

class Node:
    def __init__(self, config_dir=None, node_id=None, port=None, enable_discovery=True):
        self.config = Config(config_dir=config_dir, node_id_override=node_id, port_override=port)
        self.node_id = self.config.node_id
        self.storage = Storage(self.config.db_path)

        self.on_display_msg_cb = None
        self.on_status_update_cb = None

        self.router = Router(
            self.node_id,
            self.storage,
            on_display_msg_cb=self._handle_display_msg,
            on_status_update_cb=self._handle_status_update
        )

        self.transport = Transport(
            "0.0.0.0",
            self.config.tcp_port,
            on_message_cb=self.router.handle_incoming_message
        )

        self.enable_discovery = enable_discovery
        self.discovery = Discovery(
            self.node_id,
            self.config.tcp_port,
            self.config.udp_port,
            on_peer_discovered_cb=self._on_peer_discovered
        ) if enable_discovery else None

    def set_callbacks(self, on_display_msg, on_status_update):
        self.on_display_msg_cb = on_display_msg
        self.on_status_update_cb = on_status_update

    def _handle_display_msg(self, msg):
        if self.on_display_msg_cb:
            self.on_display_msg_cb(msg)

    def _handle_status_update(self, msg_id, status):
        if self.on_status_update_cb:
            self.on_status_update_cb(msg_id, status)

    async def _on_peer_discovered(self, peer_node_id, ip, tcp_port):
        self.storage.upsert_peer(peer_node_id, ip, tcp_port)
        await self.router.flush_queued_messages()

    async def start(self):
        await self.transport.start_server()
        if self.discovery:
            self.discovery.start()
        self.router.start_queue_worker()

    async def stop(self):
        self.router.stop_queue_worker()
        if self.discovery:
            self.discovery.stop()
        await self.transport.stop_server()

    async def send_chat(self, recipient, text):
        msg = create_chat_message(self.node_id, recipient, text)
        await self.router.send_message(msg)
        return msg

    async def send_broadcast(self, text):
        msg = create_broadcast_message(self.node_id, text)
        await self.router.send_message(msg)
        return msg

    async def send_sos(self, text="Emergency assistance needed"):
        # Fetch GPS asynchronously using threadpool executor so it doesn't block asyncio loop
        loop = asyncio.get_event_loop()
        coords = await loop.run_in_executor(None, get_location)

        lat = coords["latitude"] if coords else None
        lon = coords["longitude"] if coords else None

        msg = create_sos_message(self.node_id, text, latitude=lat, longitude=lon)
        await self.router.send_message(msg)
        return msg

    def connect_peer(self, ip, port=9876):
        dummy_id = f"PEER-{ip.replace('.', '')[-4:]}"
        self.storage.upsert_peer(dummy_id, ip, port)

    def get_active_peers(self):
        return self.storage.get_active_peers()

    def get_history(self, limit=50):
        return self.storage.get_recent_messages(limit=limit)
