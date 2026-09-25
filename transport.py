import asyncio
import json

import inspect
from .protocol import deserialize_message, serialize_message, validate_message

MAX_PAYLOAD_SIZE = 65536  # 64 KB

class Transport:
    def __init__(self, host, port, on_message_cb):
        self.host = host
        self.port = port
        self.on_message_cb = on_message_cb
        self.server = None

    async def start_server(self):
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )

    async def stop_server(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle_client(self, reader, writer):
        peer_addr = writer.get_extra_info('peername')
        try:
            data = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if data:
                if len(data) > MAX_PAYLOAD_SIZE:
                    writer.close()
                    await writer.wait_closed()
                    return

                msg_str = data.decode('utf-8').strip()
                if msg_str:
                    msg = deserialize_message(msg_str)
                    is_valid, err = validate_message(msg)
                    if is_valid:
                        # Attach origin peer IP for peer discovery update
                        if peer_addr and len(peer_addr) >= 1:
                            msg["_peer_ip"] = peer_addr[0]
                        if self.on_message_cb:
                            if inspect.iscoroutinefunction(self.on_message_cb):
                                await self.on_message_cb(msg)
                            else:
                                self.on_message_cb(msg)
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    async def send_packet(ip, port, msg_dict, timeout=5.0):
        """
        Sends a single JSON message payload to target (ip, port) over TCP.
        Returns True if sent successfully, False otherwise.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=timeout
            )
            payload = (serialize_message(msg_dict) + "\n").encode('utf-8')
            writer.write(payload)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False
