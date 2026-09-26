import unittest
import asyncio
import tempfile
from pathlib import Path
from emergency_mesh.audio import AudioManager
from emergency_mesh.protocol import create_audio_message, validate_message
from emergency_mesh.storage import Storage
from emergency_mesh.node import Node

class TestAudioSharing(unittest.TestCase):
    def test_audio_manager_encoding_decoding(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_dir = Path(tmpdir)
            am = AudioManager(audio_dir=audio_dir)

            rec_file = am.record_voice_note(duration_seconds=1)
            self.assertIsNotNone(rec_file)
            self.assertTrue(rec_file.exists())

            b64_str = am.encode_audio_to_base64(rec_file)
            self.assertIsNotNone(b64_str)
            self.assertIsInstance(b64_str, str)

            out_file = audio_dir / "decoded.wav"
            res = am.decode_base64_to_audio(b64_str, out_file)
            self.assertIsNotNone(res)
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.stat().st_size, rec_file.stat().st_size)

    def test_audio_protocol_validation(self):
        msg = create_audio_message("NODE-1", "NODE-2", audio_base64="AAAA==", duration_seconds=5)
        self.assertEqual(msg["type"], "audio")
        valid, err = validate_message(msg)
        self.assertTrue(valid, f"Validation failed: {err}")

    def test_audio_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "mesh.db"
            storage = Storage(db_file)

            msg = create_audio_message("NODE-A", "NODE-B", audio_base64="VGVzdEF1ZGlv", duration_seconds=3)
            storage.save_message(msg)

            retrieved = storage.get_message(msg["id"])
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved["audio_data"], "VGVzdEF1ZGlv")
            self.assertEqual(retrieved["audio_duration"], 3)

    def test_node_send_and_play_audio(self):
        async def run_node_audio():
            with tempfile.TemporaryDirectory() as tmpdir:
                base_dir = Path(tmpdir)
                node_a = Node(config_dir=base_dir / "a", node_id="NODE-A", port=9201, enable_discovery=False)
                node_b = Node(config_dir=base_dir / "b", node_id="NODE-B", port=9202, enable_discovery=False)

                received_b = []
                node_b.set_callbacks(on_display_msg=lambda m: received_b.append(m), on_status_update=None)

                await node_a.start()
                await node_b.start()

                node_a.connect_peer("127.0.0.1", 9202)
                await asyncio.sleep(0.3)

                msg = await node_a.send_audio("NODE-B", duration_seconds=1)
                self.assertIsNotNone(msg)

                await asyncio.sleep(1.0)

                await node_a.stop()
                await node_b.stop()

                return received_b

        received = asyncio.run(run_node_audio())
        self.assertTrue(len(received) > 0, "Node B did not receive audio message")
        self.assertEqual(received[0]["type"], "audio")
        self.assertEqual(received[0]["sender"], "NODE-A")

if __name__ == "__main__":
    unittest.main()
