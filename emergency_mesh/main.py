import argparse
import asyncio
import sys
from .node import Node
from .cli import CLI

def main():
    parser = argparse.ArgumentParser(description="EmergencyMesh: Offline Emergency P2P Mesh Communication")
    parser.add_argument("--node", type=str, help="Specify persistent Node ID (e.g., RESCUE-01)")
    parser.add_argument("--port", type=int, help="Specify custom TCP listen port (default: 9876)")
    parser.add_argument("--dir", type=str, help="Specify configuration directory (default: ~/.emergency_mesh)")
    parser.add_argument("--connect", type=str, help="Manually connect to a peer IP (e.g., 192.168.43.1:9876)")

    args = parser.parse_args()

    node = Node(
        config_dir=args.dir,
        node_id=args.node,
        port=args.port,
        enable_discovery=True
    )

    if args.connect:
        parts = args.connect.split(":")
        ip = parts[0]
        port = int(parts[1]) if len(parts) > 1 else (args.port or 9876)
        node.connect_peer(ip, port)

    cli = CLI(node)

    try:
        asyncio.run(cli.run())
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    main()
