import asyncio
import time
from .config import Config
from .storage import Storage
from .transport import Transport
from .discovery import Discovery
from .router import Router
from .gps import get_location_manager, haversine_distance, calculate_bearing, trigger_vibration, trigger_sos_alarm
from .audio import AudioManager
from .protocol import (
    create_chat_message,
    create_broadcast_message,
    create_sos_message,
    create_audio_message
)

VIBRATION_COOLDOWN_SECONDS = 60

class Node:
    def __init__(self, config_dir=None, node_id=None, port=None, enable_discovery=True):
        self.config = Config(config_dir=config_dir, node_id_override=node_id, port_override=port)
        self.node_id = self.config.node_id
        self.storage = Storage(self.config.db_path)
        self.location_manager = get_location_manager(self.config.config_dir)
        self.audio_manager = AudioManager(self.config.audio_dir)

        self.on_display_msg_cb = None
        self.on_status_update_cb = None
        self.on_peer_change_cb = None

        self.known_active_peers = set()
        self.vibrated_sos_timestamps = {}

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
        msg_type = msg.get("type")
        msg_id = msg.get("id")

        if msg_type == "sos":
            my_loc = self.location_manager.get_location()
            sender_lat = msg.get("latitude")
            sender_lon = msg.get("longitude")

            if my_loc and sender_lat not in (None, "UNKNOWN") and sender_lon not in (None, "UNKNOWN"):
                dist = haversine_distance(
                    my_loc["latitude"], my_loc["longitude"],
                    sender_lat, sender_lon
                )
                msg["_distance_meters"] = dist

                if dist is not None and dist <= self.config.sos_proximity_radius:
                    msg["_is_proximity_alert"] = True

            now = time.time()
            last_alarm = self.vibrated_sos_timestamps.get(msg_id, 0)
            if (now - last_alarm) > VIBRATION_COOLDOWN_SECONDS:
                sender_name = msg.get("sender", "Peer Node")
                alert_text = f"SOS from {sender_name}: {msg.get('text', '')}"
                trigger_sos_alarm(2000, alert_text)
                self.vibrated_sos_timestamps[msg_id] = now

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

                newly_joined = current_active_ids - self.known_active_peers
                for pid in newly_joined:
                    if self.on_peer_change_cb:
                        self.on_peer_change_cb("joined", pid, len(current_active_ids))

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
        loop = asyncio.get_event_loop()
        coords = await loop.run_in_executor(None, self.location_manager.get_location_fresh)

        lat = coords["latitude"] if coords else None
        lon = coords["longitude"] if coords else None

        msg = create_sos_message(self.node_id, text, latitude=lat, longitude=lon)
        await self.router.send_message(msg)
        return msg

    async def send_audio(self, recipient, duration_seconds=5):
        loop = asyncio.get_event_loop()
        rec_path = await loop.run_in_executor(None, self.audio_manager.record_voice_note, duration_seconds)
        if not rec_path or not rec_path.exists():
            return None

        audio_b64 = self.audio_manager.encode_audio_to_base64(rec_path)
        if not audio_b64:
            return None

        audio_fmt = rec_path.suffix.lstrip(".") or "wav"

        msg = create_audio_message(
            sender=self.node_id,
            recipient=recipient,
            audio_base64=audio_b64,
            duration_seconds=duration_seconds,
            audio_format=audio_fmt
        )
        await self.router.send_message(msg)
        return msg

    def play_audio_message(self, msg_id_prefix):
        msg = self.storage.get_message(msg_id_prefix)
        if not msg:
            recent = self.storage.get_recent_messages(limit=100)
            for m in recent:
                if m["id"].startswith(msg_id_prefix):
                    msg = m
                    break

        if not msg:
            return False, "Message not found"

        audio_b64 = msg.get("audio_data")
        if not audio_b64:
            return False, "Message does not contain voice note payload"

        fmt = msg.get("audio_format", "wav")
        msg_id = msg.get("id", "audio")
        audio_path = self.config.audio_dir / f"play_{msg_id[:8]}.{fmt}"

        if not audio_path.exists():
            self.audio_manager.decode_base64_to_audio(audio_b64, audio_path)

        success = self.audio_manager.play_audio(audio_path)
        if success:
            return True, f"Playing voice note ({msg.get('audio_duration', 5)}s)..."
        return False, "Media player playback unavailable"

    def set_manual_location(self, lat, lon):
        return self.location_manager.set_manual_location(lat, lon)

    def set_sos_proximity_radius(self, meters):
        try:
            self.config.sos_proximity_radius = int(meters)
            self.config.save()
            return True
        except (ValueError, TypeError):
            return False

    def get_radar_nodes(self):
        """
        Returns (radar_dict, error_string).
        """
        my_loc = self.location_manager.get_location()
        if not my_loc:
            return None, "Location UNKNOWN. Set coordinates manually via '/location set <lat> <lon>' or turn on GPS."

        my_lat = my_loc["latitude"]
        my_lon = my_loc["longitude"]

        targets = []
        seen_target_ids = set()

        # 1. Active peers
        active_peers = self.storage.get_active_peers(expiry_seconds=30)
        recent_msgs = self.storage.get_recent_messages(limit=100)

        for p in active_peers:
            pid = p["node_id"]
            peer_lat, peer_lon = None, None
            for m in recent_msgs:
                if m["sender"] == pid and m.get("latitude") not in (None, "UNKNOWN") and m.get("longitude") not in (None, "UNKNOWN"):
                    try:
                        peer_lat = float(m["latitude"])
                        peer_lon = float(m["longitude"])
                        break
                    except (ValueError, TypeError):
                        pass

            if peer_lat is not None and peer_lon is not None:
                dist = haversine_distance(my_lat, my_lon, peer_lat, peer_lon)
                bearing, cardinal = calculate_bearing(my_lat, my_lon, peer_lat, peer_lon)
                targets.append({
                    "id": pid,
                    "type": "peer",
                    "latitude": peer_lat,
                    "longitude": peer_lon,
                    "distance_meters": dist,
                    "bearing": bearing,
                    "cardinal": cardinal
                })
                seen_target_ids.add(pid)

        # 2. Active SOS Alerts
        recent_sos = [m for m in recent_msgs if m["type"] == "sos"]
        for s in recent_sos:
            s_lat = s.get("latitude")
            s_lon = s.get("longitude")
            s_sender = s.get("sender")
            if s_lat not in (None, "UNKNOWN") and s_lon not in (None, "UNKNOWN"):
                try:
                    s_lat = float(s_lat)
                    s_lon = float(s_lon)
                    sos_key = f"SOS-{s_sender}"
                    if sos_key not in seen_target_ids:
                        dist = haversine_distance(my_lat, my_lon, s_lat, s_lon)
                        bearing, cardinal = calculate_bearing(my_lat, my_lon, s_lat, s_lon)
                        targets.append({
                            "id": sos_key,
                            "sender": s_sender,
                            "type": "sos",
                            "text": s.get("text", ""),
                            "latitude": s_lat,
                            "longitude": s_lon,
                            "distance_meters": dist,
                            "bearing": bearing,
                            "cardinal": cardinal
                        })
                        seen_target_ids.add(sos_key)
                except (ValueError, TypeError):
                    pass

        return {
            "my_location": my_loc,
            "targets": targets
        }, None

    def get_navigation_target(self, target_id):
        radar_info, err = self.get_radar_nodes()
        if err:
            return None, err

        my_loc = radar_info["my_location"]
        targets = radar_info["targets"]

        matched_target = None
        target_id_upper = target_id.upper()

        for t in targets:
            if t["id"].upper().startswith(target_id_upper) or t.get("sender", "").upper().startswith(target_id_upper):
                matched_target = t
                break

        if not matched_target and "," in target_id:
            try:
                parts = target_id.split(",")
                t_lat = float(parts[0].strip())
                t_lon = float(parts[1].strip())
                dist = haversine_distance(my_loc["latitude"], my_loc["longitude"], t_lat, t_lon)
                bearing, cardinal = calculate_bearing(my_loc["latitude"], my_loc["longitude"], t_lat, t_lon)
                matched_target = {
                    "id": f"Coordinates ({t_lat:.4f}, {t_lon:.4f})",
                    "type": "custom",
                    "latitude": t_lat,
                    "longitude": t_lon,
                    "distance_meters": dist,
                    "bearing": bearing,
                    "cardinal": cardinal
                }
            except Exception:
                pass

        if not matched_target:
            return None, f"Target '{target_id}' not found in active peers or SOS alerts."

        return {
            "my_location": my_loc,
            "target": matched_target
        }, None

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
