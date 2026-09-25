import unittest
import asyncio
import tempfile
from pathlib import Path
from emergency_mesh.node import Node

class TestMeshRoutingMultiHop(unittest.TestCase):
    def test_three_node_sos_forwarding(self):
        async def run_multihop_test():
            temp_dir = tempfile.TemporaryDirectory()
            base_path = Path(temp_dir.name)

            node_a = Node(config_dir=base_path / "node_a", node_id="NODE-A", port=9101, enable_discovery=False)
            node_b = Node(config_dir=base_path / "node_b", node_id="NODE-B", port=9102, enable_discovery=False)
            node_c = Node(config_dir=base_path / "node_c", node_id="NODE-C", port=9103, enable_discovery=False)

            received_c = []
            node_c.set_callbacks(on_display_msg=lambda m: received_c.append(m), on_status_update=None)

            await node_a.start()
            await node_b.start()
            await node_c.start()

            node_a.connect_peer("127.0.0.1", 9102)
            node_b.connect_peer("127.0.0.1", 9103)

            await asyncio.sleep(0.5)

            await node_a.send_sos("Emergency assistance needed")

            await asyncio.sleep(1.5)

            await node_a.stop()
            await node_b.stop()
            await node_c.stop()
            temp_dir.cleanup()

            return received_c

        received = asyncio.run(run_multihop_test())
        self.assertTrue(len(received) > 0, "Node C did not receive forwarded SOS message")
        self.assertEqual(received[0]["type"], "sos")
        self.assertEqual(received[0]["sender"], "NODE-A")
        self.assertEqual(received[0]["text"], "Emergency assistance needed")

if __name__ == "__main__":
    unittest.main()
