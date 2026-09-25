import asyncio
import socket
import json
import inspect
from .protocol import create_beacon_message, deserialize_message

class Discovery:
    def __init__(self, node_id, tcp_port, udp_port, on_peer_discovered_cb):
        self.node_id = node_id
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.on_peer_discovered_cb = on_peer_discovered_cb
        self.running = False
        self.broadcast_task = None
        self.listen_task = None

    def start(self):
        self.running = True
        loop = asyncio.get_event_loop()
        self.broadcast_task = loop.create_task(self._beacon_loop())
        self.listen_task = loop.create_task(self._listen_loop())

    def stop(self):
        self.running = False
        if self.broadcast_task:
            self.broadcast_task.cancel()
        if self.listen_task:
            self.listen_task.cancel()

    async def _beacon_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)

        beacon_msg = create_beacon_message(self.node_id, self.tcp_port)
        payload = json.dumps(beacon_msg).encode('utf-8')

        loop = asyncio.get_event_loop()

        while self.running:
            try:
                # Broadcast to 255.255.255.255
                await loop.sock_sendto(sock, payload, ('<broadcast>', self.udp_port))
            except Exception:
                pass
            await asyncio.sleep(5)

    async def _listen_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)

        try:
            sock.bind(('0.0.0.0', self.udp_port))
        except Exception:
            return

        loop = asyncio.get_event_loop()

        while self.running:
            try:
                data, addr = await loop.sock_recvfrom(sock, 4096)
                if data:
                    msg = deserialize_message(data.decode('utf-8'))
                    if msg.get("type") == "beacon":
                        peer_node_id = msg.get("node_id")
                        peer_tcp_port = msg.get("tcp_port")
                        peer_ip = addr[0]

                        # Ignore self-beacons
                        if peer_node_id and peer_node_id != self.node_id and peer_tcp_port:
                            if self.on_peer_discovered_cb:
                                if inspect.iscoroutinefunction(self.on_peer_discovered_cb):
                                    await self.on_peer_discovered_cb(peer_node_id, peer_ip, peer_tcp_port)
                                else:
                                    self.on_peer_discovered_cb(peer_node_id, peer_ip, peer_tcp_port)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)
