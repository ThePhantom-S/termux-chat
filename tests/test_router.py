import unittest
import tempfile
import asyncio
from pathlib import Path
from emergency_mesh.storage import Storage
from emergency_mesh.router import Router
from emergency_mesh.protocol import create_chat_message, create_sos_message, create_ack_message

class TestRouter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_router.db"
        self.storage = Storage(self.db_path)
        self.displayed_messages = []
        self.status_updates = []

        self.router = Router(
            "LOCAL-NODE",
            self.storage,
            on_display_msg_cb=lambda m: self.displayed_messages.append(m),
            on_status_update_cb=lambda mid, st: self.status_updates.append((mid, st))
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_duplicate_detection(self):
        msg_id = "test-unique-id-123"
        self.assertFalse(self.router.is_seen(msg_id))
        self.router.mark_seen(msg_id)
        self.assertTrue(self.router.is_seen(msg_id))

    def test_incoming_chat_for_me(self):
        msg = create_chat_message("SENDER-A", "LOCAL-NODE", "Direct message to me")
        asyncio.run(self.router.handle_incoming_message(msg))

        self.assertEqual(len(self.displayed_messages), 1)
        self.assertEqual(self.displayed_messages[0]["text"], "Direct message to me")

        stored = self.storage.get_message(msg["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["status"], "RECEIVED")

    def test_incoming_sos_broadcast(self):
        sos_msg = create_sos_message("RESCUE-A", "Help needed at grid 5", latitude=10.0, longitude=70.0)
        asyncio.run(self.router.handle_incoming_message(sos_msg))

        self.assertEqual(len(self.displayed_messages), 1)
        self.assertEqual(self.displayed_messages[0]["type"], "sos")

    def test_ack_processing(self):
        # Save a message sent earlier
        target_msg = create_chat_message("LOCAL-NODE", "PEER-B", "Hello B")
        self.storage.save_message(target_msg, status="SENT")

        ack = create_ack_message("PEER-B", "LOCAL-NODE", target_msg["id"])
        asyncio.run(self.router.handle_incoming_message(ack))

        updated = self.storage.get_message(target_msg["id"])
        self.assertEqual(updated["status"], "ACKNOWLEDGED")

if __name__ == "__main__":
    unittest.main()
