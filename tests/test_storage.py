import unittest
import tempfile
import os
from pathlib import Path
from emergency_mesh.storage import Storage
from emergency_mesh.protocol import create_chat_message

class TestStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_mesh.db"
        self.storage = Storage(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_message_persistence(self):
        msg = create_chat_message("NODE-A", "NODE-B", "Test message")
        self.storage.save_message(msg, status="QUEUED")

        retrieved = self.storage.get_message(msg["id"])
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["sender"], "NODE-A")
        self.assertEqual(retrieved["recipient"], "NODE-B")
        self.assertEqual(retrieved["status"], "QUEUED")

        # Update status
        self.storage.update_message_status(msg["id"], "ACKNOWLEDGED")
        retrieved_updated = self.storage.get_message(msg["id"])
        self.assertEqual(retrieved_updated["status"], "ACKNOWLEDGED")

    def test_peer_tracking(self):
        self.storage.upsert_peer("RESCUE-100", "192.168.1.50", 9876)
        active_peers = self.storage.get_active_peers(expiry_seconds=30)
        self.assertEqual(len(active_peers), 1)
        self.assertEqual(active_peers[0]["node_id"], "RESCUE-100")
        self.assertEqual(active_peers[0]["address"], "192.168.1.50")

        # Update peer address
        self.storage.upsert_peer("RESCUE-100", "192.168.1.51", 9876)
        updated_peer = self.storage.get_peer("RESCUE-100")
        self.assertEqual(updated_peer["address"], "192.168.1.51")

if __name__ == "__main__":
    unittest.main()
