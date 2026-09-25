import unittest
from emergency_mesh.protocol import (
    create_chat_message,
    create_broadcast_message,
    create_sos_message,
    create_ack_message,
    create_beacon_message,
    serialize_message,
    deserialize_message,
    validate_message
)

class TestProtocol(unittest.TestCase):
    def test_create_and_validate_chat_message(self):
        msg = create_chat_message("NODE-A", "NODE-B", "Hello Mesh")
        self.assertEqual(msg["sender"], "NODE-A")
        self.assertEqual(msg["recipient"], "NODE-B")
        self.assertEqual(msg["type"], "chat")
        self.assertEqual(msg["ttl"], 5)

        is_valid, err = validate_message(msg)
        self.assertTrue(is_valid, err)

    def test_create_and_validate_sos_message(self):
        msg = create_sos_message("NODE-A", "Medical help needed", latitude=13.0, longitude=80.0)
        self.assertEqual(msg["sender"], "NODE-A")
        self.assertEqual(msg["recipient"], "*")
        self.assertEqual(msg["type"], "sos")
        self.assertEqual(msg["priority"], "critical")
        self.assertEqual(msg["latitude"], 13.0)
        self.assertEqual(msg["longitude"], 80.0)

        is_valid, err = validate_message(msg)
        self.assertTrue(is_valid, err)

    def test_serialization_roundtrip(self):
        msg = create_broadcast_message("NODE-X", "Warning")
        raw = serialize_message(msg)
        deserialized = deserialize_message(raw)
        self.assertEqual(msg, deserialized)

    def test_invalid_messages(self):
        # Invalid type
        bad_msg = {"type": "unknown", "id": "1", "sender": "A", "recipient": "B", "ttl": 5, "timestamp": 100}
        is_valid, err = validate_message(bad_msg)
        self.assertFalse(is_valid)

        # TTL out of range
        bad_ttl = create_chat_message("A", "B", "Hi", ttl=99)
        is_valid, err = validate_message(bad_ttl)
        self.assertFalse(is_valid)

        # Missing ID
        no_id = create_chat_message("A", "B", "Hi")
        del no_id["id"]
        is_valid, err = validate_message(no_id)
        self.assertFalse(is_valid)

if __name__ == "__main__":
    unittest.main()
