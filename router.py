import asyncio
import time
from collections import OrderedDict
from .protocol import create_ack_message, validate_message
from .transport import Transport

MAX_DUPLICATE_CACHE_SIZE = 2000

class Router:
    def __init__(self, node_id, storage, on_display_msg_cb=None, on_status_update_cb=None):
        self.node_id = node_id
        self.storage = storage
        self.on_display_msg_cb = on_display_msg_cb
        self.on_status_update_cb = on_status_update_cb
        self.seen_message_ids = OrderedDict()
        self.retry_task = None

    def mark_seen(self, msg_id):
        self.seen_message_ids[msg_id] = time.time()
        if len(self.seen_message_ids) > MAX_DUPLICATE_CACHE_SIZE:
            self.seen_message_ids.popitem(last=False)

    def is_seen(self, msg_id):
        return msg_id in self.seen_message_ids

    def start_queue_worker(self):
        loop = asyncio.get_event_loop()
        self.retry_task = loop.create_task(self._queue_retry_loop())

    def stop_queue_worker(self):
        if self.retry_task:
            self.retry_task.cancel()

    async def _queue_retry_loop(self):
        while True:
            try:
                await self.flush_queued_messages()
            except Exception:
                pass
            await asyncio.sleep(10)

    async def handle_incoming_message(self, msg):
        is_valid, err = validate_message(msg)
        if not is_valid:
            return

        msg_id = msg.get("id")
        if self.is_seen(msg_id):
            return  # Drop duplicate

        self.mark_seen(msg_id)

        msg_type = msg.get("type")
        sender = msg.get("sender")
        recipient = msg.get("recipient")
        ttl = msg.get("ttl", 5)

        origin_ip = msg.get("_peer_ip")

        # If origin_ip is provided, register sender peer if possible
        if sender and sender != self.node_id and origin_ip:
            peer = self.storage.get_peer(sender)
            port = peer["port"] if peer else 9876
            self.storage.upsert_peer(sender, origin_ip, port)

        # Handle ACK messages
        if msg_type == "ack":
            ack_target_id = msg.get("ack_msg_id")
            if ack_target_id:
                self.storage.update_message_status(ack_target_id, "ACKNOWLEDGED")
                if self.on_status_update_cb:
                    self.on_status_update_cb(ack_target_id, "ACKNOWLEDGED")

            if recipient == self.node_id:
                return  # ACK reached original sender

            # Forward ACK if TTL > 1
            if ttl > 1:
                forward_msg = dict(msg)
                forward_msg["ttl"] = ttl - 1
                await self._forward_to_peers(forward_msg, exclude_node=sender)
            return

        # Handle messages where THIS node is target or broadcast/SOS
        is_for_me = (recipient == self.node_id) or (recipient == "*")

        if is_for_me:
            # Save to local DB
            self.storage.save_message(msg, status="RECEIVED")

            # UI notification
            if self.on_display_msg_cb:
                self.on_display_msg_cb(msg)

            # If targeted chat message for me, send ACK back to sender
            if msg_type == "chat" and recipient == self.node_id:
                ack_msg = create_ack_message(self.node_id, sender, msg_id)
                await self.send_message(ack_msg)

        # Forwarding logic for broadcast/SOS or relayed chat messages
        if recipient == "*" or msg_type == "sos" or msg_type == "broadcast":
            if ttl > 1:
                forward_msg = dict(msg)
                forward_msg["ttl"] = ttl - 1
                await self._forward_to_peers(forward_msg, exclude_node=sender)
        elif not is_for_me:
            # Multi-hop routing: B forwarding chat message from A to C
            if ttl > 1:
                self.storage.save_message(msg, status="FORWARDED")
                forward_msg = dict(msg)
                forward_msg["ttl"] = ttl - 1
                await self._forward_to_peers(forward_msg, exclude_node=sender)

    async def send_message(self, msg):
        """
        Sends an outgoing message created on this node, or places it in QUEUED status.
        """
        msg_id = msg["id"]
        recipient = msg.get("recipient")

        self.mark_seen(msg_id)

        # Save initially as QUEUED
        self.storage.save_message(msg, status="QUEUED")

        sent_count = await self._forward_to_peers(msg)

        if sent_count > 0:
            if recipient != "*":
                self.storage.update_message_status(msg_id, "SENT")
                if self.on_status_update_cb:
                    self.on_status_update_cb(msg_id, "SENT")
            else:
                self.storage.update_message_status(msg_id, "BROADCAST")
                if self.on_status_update_cb:
                    self.on_status_update_cb(msg_id, "BROADCAST")
            return True
        else:
            if self.on_status_update_cb:
                self.on_status_update_cb(msg_id, "QUEUED")
            return False

    async def _forward_to_peers(self, msg, exclude_node=None):
        recipient = msg.get("recipient")
        active_peers = self.storage.get_active_peers()

        if exclude_node:
            active_peers = [p for p in active_peers if p["node_id"] != exclude_node]

        if not active_peers:
            return 0

        # If specific recipient is in active peers, send directly
        target_peers = [p for p in active_peers if p["node_id"] == recipient] if recipient != "*" else active_peers

        # Fallback: flood to all active peers if target peer is not direct neighbor
        if not target_peers and recipient != "*":
            target_peers = active_peers

        successful_sends = 0
        for peer in target_peers:
            success = await Transport.send_packet(peer["address"], peer["port"], msg)
            if success:
                successful_sends += 1

        return successful_sends

    async def flush_queued_messages(self):
        queued_msgs = self.storage.get_queued_messages()
        if not queued_msgs:
            return

        active_peers = self.storage.get_active_peers()
        if not active_peers:
            return

        for msg in queued_msgs:
            sent_count = await self._forward_to_peers(msg)
            if sent_count > 0:
                if msg["recipient"] != "*":
                    self.storage.update_message_status(msg["id"], "SENT")
                    if self.on_status_update_cb:
                        self.on_status_update_cb(msg["id"], "SENT")
                else:
                    self.storage.update_message_status(msg["id"], "BROADCAST")
