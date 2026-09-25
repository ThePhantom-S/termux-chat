import asyncio
import time
from .config import Config
from .storage import Storage
from .transport import Transport
from .discovery import Discovery
from .router import Router
from .gps import get_location_manager
from .protocol import create_chat_message, create_broadcast_message, create_sos_message

class Node:
    def __init__(self, config_dir=None, node_id=None, port=None, enable_discovery=True):
        self.config = Config(config_dir=config_dir, node_id_override=node_id, port_override=port)
        self.node_id = self.config.node_id
        self.storage = Storage(self.config.db_path)
        self.location_manager = get_location_manager()

        self.on_display_msg_cb = None
        self.on_status_update_cb = None
        self.on_peer_change_cb = None

        self.known_active_peers = set()

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

        self.peer_monitor_task = None
        self.gps_bg_task = None

    def set_callbacks(self, on_display_msg, on_status_update, on_peer_change=None):
        self.on_display_msg_cb = on_display_msg
        self.on_status_update_cb = on_status_update
        self.on_peer_change_cb = on_peer_change

    def _handle_display_msg(self, msg):
        if self.on_display_msg_cb:
            self.on_display_msg_cb(msg)

    def _handle_status_update(self, msg_id, status):
        if self.on_status_update_cb:
            self.on_status_update_cb(msg_id, status)

    async def _on_peer_discovered(self, peer_node_id, ip, tcp_port):
        is_new, active_cnt = self.storage.upsert_peer(peer_node_id, ip, tcp_port)
        await self.router.flush_queued_messages()
        if is_new and self.on_peer_change_cb:
            self.on_peer_change_cb("joined", peer_node_id, active_cnt)
            self.known_active_peers.add(peer_node_id)

    async def _peer_monitor_loop(self):
        while True:
            try:
                active_peers = self.storage.get_active_peers(expiry_seconds=30)
                current_active_ids = {p["node_id"] for p in active_peers}

                # Check joined
                newly_joined = current_active_ids - self.known_active_peers
                for pid in newly_joined:
                    if self.on_peer_change_cb:
                        self.on_peer_change_cb("joined", pid, len(current_active_ids))

                # Check left
                newly_left = self.known_active_peers - current_active_ids
                for pid in newly_left:
                    if self.on_peer_change_cb:
                        self.on_peer_change_cb("left", pid, len(current_active_ids))

                self.known_active_peers = current_active_ids
            except Exception:
                pass
            await asyncio.sleep(3)

    async def start(self):
        await self.transport.start_server()
        if self.discovery:
            self.discovery.start()
        self.router.start_queue_worker()

        loop = asyncio.get_event_loop()
        self.peer_monitor_task = loop.create_task(self._peer_monitor_loop())
        self.gps_bg_task = loop.create_task(self.location_manager.start_background_updates(interval=15))

    async def stop(self):
        if self.peer_monitor_task:
            self.peer_monitor_task.cancel()
        if self.gps_bg_task:
            self.gps_bg_task.cancel()
        self.location_manager.stop_background_updates()

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
        coords = self.location_manager.get_location()

        lat = coords["latitude"] if coords else None
        lon = coords["longitude"] if coords else None

        msg = create_sos_message(self.node_id, text, latitude=lat, longitude=lon)
        await self.router.send_message(msg)
        return msg

    def set_manual_location(self, lat, lon):
        return self.location_manager.set_manual_location(lat, lon)

    def connect_peer(self, ip, port=9876):
        dummy_id = f"PEER-{ip.replace('.', '')[-4:]}"
        is_new, active_cnt = self.storage.upsert_peer(dummy_id, ip, port)
        if self.on_peer_change_cb:
            self.on_peer_change_cb("joined", dummy_id, active_cnt)
        self.known_active_peers.add(dummy_id)

    def get_active_peers(self):
        return self.storage.get_active_peers()

    def get_history(self, limit=50):
        return self.storage.get_recent_messages(limit=limit)
