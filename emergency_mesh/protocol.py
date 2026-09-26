import json
import time
import uuid

MESSAGE_TYPES = {"chat", "sos", "ack", "broadcast", "audio"}
MAX_TTL = 20
MAX_TEXT_LENGTH = 4096
MAX_AUDIO_DATA_LENGTH = 750000  # Base64 string limit (~500KB binary audio)

def generate_msg_id():
    return str(uuid.uuid4())

def create_chat_message(sender, recipient, text, ttl=5):
    return {
        "id": generate_msg_id(),
        "sender": sender,
        "recipient": recipient,
        "type": "chat",
        "priority": "normal",
        "text": text,
        "timestamp": int(time.time()),
        "ttl": int(ttl)
    }

def create_broadcast_message(sender, text, ttl=5):
    return {
        "id": generate_msg_id(),
        "sender": sender,
        "recipient": "*",
        "type": "broadcast",
        "priority": "normal",
        "text": text,
        "timestamp": int(time.time()),
        "ttl": int(ttl)
    }

def create_sos_message(sender, text, latitude=None, longitude=None, ttl=8):
    return {
        "id": generate_msg_id(),
        "sender": sender,
        "recipient": "*",
        "type": "sos",
        "priority": "critical",
        "text": text,
        "latitude": latitude if latitude is not None else "UNKNOWN",
        "longitude": longitude if longitude is not None else "UNKNOWN",
        "timestamp": int(time.time()),
        "ttl": int(ttl)
    }

def create_audio_message(sender, recipient, audio_base64, duration_seconds=5, audio_format="aac", ttl=5):
    return {
        "id": generate_msg_id(),
        "sender": sender,
        "recipient": recipient,
        "type": "audio",
        "priority": "high",
        "audio_data": audio_base64,
        "audio_duration": int(duration_seconds),
        "audio_format": str(audio_format),
        "text": f"🎤 Voice Note ({duration_seconds}s)",
        "timestamp": int(time.time()),
        "ttl": int(ttl)
    }

def create_ack_message(sender, recipient, ack_msg_id, ttl=5):
    return {
        "id": generate_msg_id(),
        "sender": sender,
        "recipient": recipient,
        "type": "ack",
        "priority": "high",
        "ack_msg_id": ack_msg_id,
        "timestamp": int(time.time()),
        "ttl": int(ttl)
    }

def create_beacon_message(node_id, tcp_port):
    return {
        "type": "beacon",
        "node_id": node_id,
        "tcp_port": tcp_port,
        "timestamp": int(time.time())
    }

def serialize_message(msg_dict):
    return json.dumps(msg_dict, ensure_ascii=False)

def deserialize_message(raw_bytes_or_str):
    if isinstance(raw_bytes_or_str, bytes):
        raw_str = raw_bytes_or_str.decode("utf-8")
    else:
        raw_str = raw_bytes_or_str
    return json.loads(raw_str)

def validate_message(msg):
    """
    Validates that a message dictionary conforms to the required schema.
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    if not isinstance(msg, dict):
        return False, "Message must be a JSON object"

    msg_type = msg.get("type")
    if msg_type == "beacon":
        if not msg.get("node_id") or not isinstance(msg.get("node_id"), str):
            return False, "Beacon node_id invalid"
        if not isinstance(msg.get("tcp_port"), int):
            return False, "Beacon tcp_port invalid"
        return True, None

    if msg_type not in MESSAGE_TYPES:
        return False, f"Unsupported message type: {msg_type}"

    msg_id = msg.get("id")
    if not msg_id or not isinstance(msg_id, str):
        return False, "Missing or invalid 'id'"

    sender = msg.get("sender")
    if not sender or not isinstance(sender, str):
        return False, "Missing or invalid 'sender'"

    recipient = msg.get("recipient")
    if not recipient or not isinstance(recipient, str):
        return False, "Missing or invalid 'recipient'"

    ttl = msg.get("ttl")
    if not isinstance(ttl, int) or ttl < 0 or ttl > MAX_TTL:
        return False, f"Invalid 'ttl': {ttl}"

    timestamp = msg.get("timestamp")
    if not isinstance(timestamp, (int, float)):
        return False, "Invalid 'timestamp'"

    if msg_type in ("chat", "broadcast", "sos"):
        text = msg.get("text", "")
        if not isinstance(text, str) or len(text) > MAX_TEXT_LENGTH:
            return False, f"Invalid 'text' field (length > {MAX_TEXT_LENGTH})"

    if msg_type == "audio":
        audio_data = msg.get("audio_data")
        if not audio_data or not isinstance(audio_data, str) or len(audio_data) > MAX_AUDIO_DATA_LENGTH:
            return False, "Invalid or oversized 'audio_data'"

    if msg_type == "ack":
        ack_msg_id = msg.get("ack_msg_id")
        if not ack_msg_id or not isinstance(ack_msg_id, str):
            return False, "ACK message missing 'ack_msg_id'"

    return True, None
