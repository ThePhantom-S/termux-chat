import sys
import asyncio
import time
import socket

# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

BANNER_TEMPLATE = f"""{CYAN}{BOLD}
╔══════════════════════════════════════════╗
║          EMERGENCY MESH                  ║
║      OFFLINE COMMUNICATION               ║
╠══════════════════════════════════════════╣
║ Node: {{node_id:<27}} ║
║ Network: OFFLINE MESH                    ║
║ Nearby nodes: {{peer_count:<25}} ║
╚══════════════════════════════════════════╝{RESET}
Type {BOLD}/help{RESET} for commands list.
"""

HELP_TEXT = f"""
{BOLD}Available Commands:{RESET}
  {CYAN}/help{RESET}                     - Show this help manual
  {CYAN}/nodes{RESET}                    - List active nearby mesh nodes
  {CYAN}/msg <node> <message>{RESET}   - Send direct offline chat message to node
  {CYAN}/broadcast <message>{RESET}   - Broadcast message to all nearby mesh nodes
  {CYAN}/sos [message]{RESET}         - Send urgent emergency alert with GPS coordinates
  {CYAN}/history{RESET}                  - View stored message history
  {CYAN}/status{RESET}                 - View node status, IP address, and ports
  {CYAN}/connect <ip> [port]{RESET}     - Manually connect to peer IP address (default port 9876)
  {CYAN}/id{RESET}                     - Print this node's unique ID
  {CYAN}/quit{RESET}                   - Exit EmergencyMesh
"""

def format_time(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))

class CLI:
    def __init__(self, node):
        self.node = node
        self.running = True

    def display_banner(self):
        peers = self.node.get_active_peers()
        print(BANNER_TEMPLATE.format(node_id=self.node.node_id, peer_count=len(peers)))

    def on_display_msg(self, msg):
        msg_type = msg.get("type")
        sender = msg.get("sender")
        recipient = msg.get("recipient")
        text = msg.get("text", "")
        ts = format_time(msg.get("timestamp", time.time()))

        if msg_type == "sos":
            lat = msg.get("latitude", "UNKNOWN")
            lon = msg.get("longitude", "UNKNOWN")
            loc_str = f"{lat}, {lon}" if lat != "UNKNOWN" else "UNKNOWN"

            print(f"\n{RED}{BOLD}🚨 SOS FROM {sender}{RESET}")
            print(f"{RED}Location: {loc_str}{RESET}")
            print(f"{RED}Message: {text}{RESET}\n")
        elif msg_type == "broadcast":
            print(f"\n[{ts}] {YELLOW}[BROADCAST]{RESET} {BOLD}{sender}{RESET} > *: {text}")
        elif msg_type == "chat":
            target = "YOU" if recipient == self.node.node_id else recipient
            print(f"\n[{ts}] {CYAN}{BOLD}{sender}{RESET} > {BOLD}{target}{RESET}: {text}")
        
        sys.stdout.write("> ")
        sys.stdout.flush()

    def on_status_update(self, msg_id, status):
        if status == "SENT":
            print(f"{GREEN}✓ Sent to peer{RESET}")
        elif status == "ACKNOWLEDGED":
            print(f"{GREEN}✓ ACK received{RESET}")
        elif status == "QUEUED":
            print(f"{YELLOW}⚠ Peer unavailable - Message stored locally (Will retry when online){RESET}")
        elif status == "BROADCAST":
            print(f"{GREEN}✓ Message broadcasted{RESET}")

        sys.stdout.write("> ")
        sys.stdout.flush()

    async def run(self):
        self.node.set_callbacks(self.on_display_msg, self.on_status_update)
        await self.node.start()
        self.display_banner()

        loop = asyncio.get_event_loop()

        while self.running:
            try:
                line = await loop.run_in_executor(None, input, "> ")
                line = line.strip()
                if not line:
                    continue

                if line.startswith("/"):
                    await self.process_command(line)
                else:
                    print(f"{YELLOW}Type commands starting with '/'. Example: /help{RESET}")
            except (EOFError, KeyboardInterrupt):
                print("\nExiting EmergencyMesh...")
                break
            except Exception as e:
                print(f"{RED}Error: {e}{RESET}")

        await self.node.stop()

    async def process_command(self, cmd_line):
        parts = cmd_line.split(" ", 2)
        cmd = parts[0].lower()

        if cmd == "/help":
            print(HELP_TEXT)
        elif cmd == "/id":
            print(f"Node ID: {CYAN}{BOLD}{self.node.node_id}{RESET}")
        elif cmd == "/nodes":
            peers = self.node.get_active_peers()
            if not peers:
                print(f"{YELLOW}No active nearby mesh nodes found.{RESET}")
            else:
                print(f"\n{BOLD}Nearby nodes:{RESET}")
                now = time.time()
                for p in peers:
                    ago = int(now - p["last_seen"])
                    print(f"  {CYAN}{p['node_id']:<15}{RESET} {p['address']:<15}:{p['port']}  last seen {ago} sec ago")
                print()
        elif cmd == "/msg":
            if len(parts) < 3:
                print(f"{YELLOW}Usage: /msg <node_id> <message>{RESET}")
                return
            target_node = parts[1]
            text = parts[2]
            print(f"{GREEN}✓ Message queued{RESET}")
            await self.node.send_chat(target_node, text)
        elif cmd == "/broadcast":
            if len(parts) < 2:
                print(f"{YELLOW}Usage: /broadcast <message>{RESET}")
                return
            text = cmd_line[len("/broadcast"):].strip()
            print(f"{GREEN}✓ Broadcast message queued{RESET}")
            await self.node.send_broadcast(text)
        elif cmd == "/sos":
            text = cmd_line[len("/sos"):].strip()
            if not text:
                text = "Emergency assistance required"
            print(f"\n{RED}{BOLD}🚨 SOS CREATED{RESET}")
            print(f"Node: {self.node.node_id}")
            print(f"Status: QUEUED / TRANSMITTING...")
            msg = await self.node.send_sos(text)
            lat = msg.get("latitude")
            lon = msg.get("longitude")
            loc_str = f"{lat}, {lon}" if lat != "UNKNOWN" else "UNKNOWN"
            print(f"Location: {loc_str}\n")
        elif cmd == "/history":
            history = self.node.get_history(limit=20)
            if not history:
                print(f"{YELLOW}No stored message history.{RESET}")
            else:
                print(f"\n{BOLD}Recent Message History:{RESET}")
                for m in history:
                    ts = format_time(m["timestamp"])
                    st = m.get("status", "")
                    if m["type"] == "sos":
                        print(f"  [{ts}] {RED}🚨 SOS {m['sender']}: {m['text']} ({st}){RESET}")
                    else:
                        print(f"  [{ts}] {m['sender']} -> {m['recipient']}: {m['text']} ({st})")
                print()
        elif cmd == "/status":
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
            except Exception:
                ip = "127.0.0.1 (Offline)"

            peers = self.node.get_active_peers()
            print(f"\n{BOLD}EmergencyMesh Node Status:{RESET}")
            print(f"  Node ID:     {CYAN}{self.node.node_id}{RESET}")
            print(f"  Local IP:    {ip}")
            print(f"  TCP Port:    {self.node.config.tcp_port}")
            print(f"  UDP Port:    {self.node.config.udp_port}")
            print(f"  Peer Count:  {len(peers)}")
            print(f"  DB Path:     {self.node.config.db_path}\n")
        elif cmd == "/connect":
            if len(parts) < 2:
                print(f"{YELLOW}Usage: /connect <ip> [port]{RESET}")
                return
            ip = parts[1]
            port = int(parts[2]) if len(parts) >= 3 else self.node.config.tcp_port
            self.node.connect_peer(ip, port)
            print(f"{GREEN}✓ Connected manually to peer {ip}:{port}{RESET}")
        elif cmd == "/quit":
            print("Exiting EmergencyMesh...")
            self.running = False
        else:
            print(f"{YELLOW}Unknown command: {cmd}. Type /help for available commands.{RESET}")
