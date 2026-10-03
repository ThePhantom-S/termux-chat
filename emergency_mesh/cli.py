import sys
import asyncio
import time
import socket
import shutil
import subprocess
import math
from pathlib import Path

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
║ Node: {{node_id:<27}}        ║
║ Network: OFFLINE MESH                    ║
║ Nearby nodes: {{peer_count:<25}}  ║
╚══════════════════════════════════════════╝{RESET}
Type {BOLD}/help{RESET} for commands list.
"""

HELP_TEXT = f"""
{BOLD}Available Commands:{RESET}
  {CYAN}/help{RESET}                     - Show this help manual
  {CYAN}/nodes{RESET}                    - List active nearby mesh nodes in real-time
  {CYAN}/msg <node> <message>{RESET}   - Send direct offline chat message to node
  {CYAN}/broadcast <message>{RESET}   - Broadcast message to all nearby mesh nodes
  {CYAN}/record <node|broadcast> [s] - Record and send offline voice note (default 5s)
  {CYAN}/play <message_id>{RESET}        - Play received voice note audio payload
  {CYAN}/sos [message]{RESET}         - Send urgent emergency alert with real-time GPS coordinates
  {CYAN}/sos radius [meters]{RESET}   - View or set proximity vibration alert radius (default 6m)
  {CYAN}/location{RESET}                 - View or update node GPS/manual location coordinates
  {CYAN}/map{RESET}                     - Display offline ASCII radar map of nearby peers & SOS alerts
  {CYAN}/map open [node_id]{RESET}        - Open target in Android offline maps app (OsmAnd / Organic Maps)
  {CYAN}/map html{RESET}                - Export self-contained offline vector HTML map file
  {CYAN}/navigate <node_id|sos>{RESET}  - Step-by-step compass bearing & distance guidance to target
  {CYAN}/history{RESET}                  - View stored message history
  {CYAN}/status{RESET}                 - View node status, IP address, and ports
  {CYAN}/connect <ip> [port]{RESET}     - Manually connect to peer IP address (default port 9876)
  {CYAN}/id{RESET}                     - Print this node's unique ID
  {CYAN}/quit{RESET}                   - Exit EmergencyMesh
"""

def format_time(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))

def format_distance(meters):
    if meters is None:
        return "UNKNOWN"
    if meters >= 1000:
        return f"{meters / 1000.0:.2f} km ({int(meters)}m)"
    else:
        return f"{int(meters)}m"

def render_ascii_radar(radar_info, my_node_id):
    my_loc = radar_info["my_location"]
    targets = radar_info["targets"]

    # 11 rows x 25 columns canvas
    grid_rows = 11
    grid_cols = 25
    center_r = 5
    center_c = 12

    # Canvas buffer
    canvas = [[" " for _ in range(grid_cols)] for _ in range(grid_rows)]

    # Draw grid axes
    for r in range(grid_rows):
        canvas[r][center_c] = "│"
    for c in range(grid_cols):
        canvas[center_r][c] = "─"
    canvas[center_r][center_c] = "┼"

    # Plot targets on canvas based on bearing and distance
    # Scale max distance to grid bounds (max radius ~500m default or dynamic)
    max_dist = max([t["distance_meters"] for t in targets if t["distance_meters"] is not None] + [100.0])
    max_dist = max(max_dist, 50.0)

    labels = []

    for t in targets:
        dist = t.get("distance_meters")
        bearing = t.get("bearing")
        if dist is None or bearing is None:
            continue

        # Scale distance ratio (0.0 to 1.0)
        norm_dist = min(dist / max_dist, 1.0)

        # Bearing 0° = UP (negative row), 90° = RIGHT (positive col)
        rad = math.radians(bearing)
        dr = -math.cos(rad) * norm_dist * 4.0  # row radius max 4
        dc = math.sin(rad) * norm_dist * 10.0  # col radius max 10

        r = int(round(center_r + dr))
        c = int(round(center_c + dc))

        r = max(1, min(grid_rows - 2, r))
        c = max(1, min(grid_cols - 2, c))

        if t["type"] == "sos":
            canvas[r][c] = "🚨"
        else:
            canvas[r][c] = "●"

        labels.append((r, c, t))

    # Build ASCII string output
    lines = []
    lines.append(f"{CYAN}{BOLD}╔═══════════════════════════════════════════════════════╗{RESET}")
    lines.append(f"{CYAN}{BOLD}║               OFFLINE MESH RADAR MAP                  ║{RESET}")
    lines.append(f"{CYAN}{BOLD}╠═══════════════════════════════════════════════════════╣{RESET}")
    lines.append(f"║                     {BOLD}N (0°){RESET}                             ║")

    for r in range(grid_rows):
        row_str = ""
        for c in range(grid_cols):
            if r == center_r and c == center_c:
                row_str += f"{YELLOW}{BOLD}★{RESET}"
            elif canvas[r][c] == "🚨":
                row_str += f"{RED}{BOLD}🚨{RESET}"
            elif canvas[r][c] == "●":
                row_str += f"{CYAN}●{RESET}"
            else:
                row_str += canvas[r][c]

        if r == center_r:
            lines.append(f"║ {BOLD}W (270°){RESET} ── {row_str} ── {BOLD}E (90°){RESET} ║")
        else:
            lines.append(f"║           {row_str}           ║")

    lines.append(f"║                     {BOLD}S (180°){RESET}                           ║")
    lines.append(f"{CYAN}{BOLD}╚═══════════════════════════════════════════════════════╝{RESET}")
    lines.append(f"  {YELLOW}{BOLD}★ YOU ({my_node_id}){RESET} at ({my_loc['latitude']:.6f}, {my_loc['longitude']:.6f})")

    if not targets:
        lines.append(f"\n{YELLOW}No nearby target nodes or SOS alerts detected on radar.{RESET}")
    else:
        lines.append(f"\n{BOLD}Target Radar Entries ({len(targets)} active):{RESET}")
        for t in targets:
            tid = t["id"]
            ttype = t["type"]
            dist_str = format_distance(t["distance_meters"])
            bearing_deg = t["bearing"]
            cardinal = t["cardinal"]

            if ttype == "sos":
                lines.append(f"  {RED}{BOLD}🚨 {tid:<18}{RESET} {dist_str:<12} Bearing: {CYAN}{bearing_deg}° ({cardinal}){RESET} - {t.get('text', '')}")
            else:
                lines.append(f"  {CYAN}●  {tid:<18}{RESET} {dist_str:<12} Bearing: {CYAN}{bearing_deg}° ({cardinal}){RESET}")

    lines.append(f"\n{BOLD}Map & Navigation Commands:{RESET}")
    lines.append(f"  {CYAN}/navigate <node_id>{RESET}  - Get compass bearing step-by-step navigation")
    lines.append(f"  {CYAN}/map open [target]{RESET}   - Launch target in Android offline maps (OsmAnd)")
    lines.append(f"  {CYAN}/map html{RESET}          - Export self-contained offline vector HTML map\n")

    return "\n".join(lines)

def generate_offline_html_map(radar_info, my_node_id, output_path):
    my_loc = radar_info["my_location"]
    targets = radar_info["targets"]

    my_lat = my_loc["latitude"]
    my_lon = my_loc["longitude"]

    target_js_items = []
    for t in targets:
        t_id = t["id"]
        t_type = t["type"]
        t_lat = t["latitude"]
        t_lon = t["longitude"]
        t_dist = format_distance(t["distance_meters"])
        t_bearing = f"{t['bearing']}° ({t['cardinal']})"
        t_text = t.get("text", "")

        color = "red" if t_type == "sos" else "cyan"
        target_js_items.append(
            f'{{ id: "{t_id}", type: "{t_type}", lat: {t_lat}, lon: {t_lon}, dist: "{t_dist}", bearing: "{t_bearing}", text: "{t_text}", color: "{color}" }}'
        )

    targets_js_array = "[\n      " + ",\n      ".join(target_js_items) + "\n    ]"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EmergencyMesh Offline Radar Map</title>
    <style>
        body {{
            background-color: #121212;
            color: #e0e0e0;
            font-family: monospace, system-ui, sans-serif;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        h1 {{ color: #00e5ff; margin-bottom: 5px; }}
        .subtitle {{ color: #888; margin-bottom: 20px; }}
        #radarCanvas {{
            background-color: #050b14;
            border: 2px solid #00e5ff;
            border-radius: 50%;
            box-shadow: 0 0 20px rgba(0, 229, 255, 0.3);
        }}
        .legend {{
            margin-top: 20px;
            max-width: 600px;
            width: 100%;
            background: #1e1e1e;
            padding: 15px;
            border-radius: 8px;
        }}
        .legend-item {{
            margin-bottom: 8px;
            padding-bottom: 8px;
            border-bottom: 1px solid #333;
        }}
        .sos {{ color: #ff1744; font-weight: bold; }}
        .peer {{ color: #00e5ff; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>🚨 EMERGENCY MESH RADAR</h1>
    <div class="subtitle">Self-Contained Offline Map • Center: {my_node_id} ({my_lat:.6f}, {my_lon:.6f})</div>

    <canvas id="radarCanvas" width="500" height="500"></canvas>

    <div class="legend">
        <h3>Active Mesh Targets</h3>
        <div id="targetList"></div>
    </div>

    <script>
        const myLat = {my_lat};
        const myLon = {my_lon};
        const targets = {targets_js_array};

        const canvas = document.getElementById('radarCanvas');
        const ctx = canvas.getContext('2d');
        const cx = 250;
        const cy = 250;

        function drawRadar() {{
            ctx.clearRect(0, 0, 500, 500);

            // Distance rings
            ctx.strokeStyle = '#003344';
            ctx.lineWidth = 1;
            [50, 100, 175, 230].forEach(r => {{
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, 2 * Math.PI);
                ctx.stroke();
            }});

            // Axes
            ctx.strokeStyle = '#005577';
            ctx.beginPath();
            ctx.moveTo(cx, 10); ctx.lineTo(cx, 490);
            ctx.moveTo(10, cy); ctx.lineTo(490, cy);
            ctx.stroke();

            // Cardinal labels
            ctx.fillStyle = '#00e5ff';
            ctx.font = '14px monospace';
            ctx.fillText('N (0°)', cx - 20, 25);
            ctx.fillText('S (180°)', cx - 25, 485);
            ctx.fillText('E (90°)', 445, cy + 5);
            ctx.fillText('W (270°)', 15, cy + 5);

            // You (Center)
            ctx.fillStyle = '#ffea00';
            ctx.beginPath();
            ctx.arc(cx, cy, 7, 0, 2 * Math.PI);
            ctx.fill();

            // Max distance scale
            let maxDist = 100;
            targets.forEach(t => {{
                let d = parseFloat(t.dist);
                if (!isNaN(d) && d > maxDist) maxDist = d;
            }});

            const targetListDiv = document.getElementById('targetList');
            targetListDiv.innerHTML = '';

            targets.forEach(t => {{
                let distNum = parseFloat(t.dist);
                let bearingNum = parseFloat(t.bearing);

                let normD = Math.min(distNum / maxDist, 1.0) * 220;
                let rad = (bearingNum - 90) * Math.PI / 180;

                let tx = cx + normD * Math.cos(rad);
                let ty = cy + normD * Math.sin(rad);

                ctx.fillStyle = t.color === 'red' ? '#ff1744' : '#00e5ff';
                ctx.beginPath();
                ctx.arc(tx, ty, 6, 0, 2 * Math.PI);
                ctx.fill();

                ctx.fillStyle = '#ffffff';
                ctx.font = '11px monospace';
                ctx.fillText(t.id, tx + 10, ty + 4);

                let div = document.createElement('div');
                div.className = 'legend-item ' + (t.type === 'sos' ? 'sos' : 'peer');
                div.innerHTML = `<strong>${{t.id}}</strong> • ${{t.dist}} • Bearing: ${{t.bearing}} ${{t.text ? '- ' + t.text : ''}}`;
                targetListDiv.appendChild(div);
            }});
        }}

        drawRadar();
    </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

class CLI:
    def __init__(self, node):
        self.node = node
        self.running = True

    def get_prompt_str(self):
        peer_cnt = len(self.node.get_active_peers())
        return f"[{CYAN}{self.node.node_id}{RESET} | Peers: {GREEN}{peer_cnt}{RESET}] > "

    def display_banner(self):
        peers = self.node.get_active_peers()
        print(BANNER_TEMPLATE.format(node_id=self.node.node_id, peer_count=len(peers)))

    def on_peer_change(self, event_type, peer_node_id, active_count):
        if event_type == "joined":
            print(f"\n{GREEN}{BOLD}[+] Peer {peer_node_id} joined nearby mesh (Active peers: {active_count}){RESET}")
        elif event_type == "left":
            print(f"\n{YELLOW}{BOLD}[-] Peer {peer_node_id} disconnected (Active peers: {active_count}){RESET}")

        sys.stdout.write(self.get_prompt_str())
        sys.stdout.flush()

    def on_display_msg(self, msg):
        msg_type = msg.get("type")
        sender = msg.get("sender")
        recipient = msg.get("recipient")
        text = msg.get("text", "")
        ts = format_time(msg.get("timestamp", time.time()))

        if msg_type == "sos":
            lat = msg.get("latitude")
            lon = msg.get("longitude")
            if lat not in (None, "UNKNOWN") and lon not in (None, "UNKNOWN"):
                try:
                    loc_str = f"{float(lat):.6f}, {float(lon):.6f}"
                except (ValueError, TypeError):
                    loc_str = "UNKNOWN"
            else:
                loc_str = "UNKNOWN"
            dist_meters = msg.get("_distance_meters")
            is_proximity = msg.get("_is_proximity_alert", False)

            if is_proximity:
                print(f"\n{RED}{BOLD}🚨 PROXIMITY SOS ALERT (WITHIN {format_distance(dist_meters)})!{RESET}")
            else:
                print(f"\n{RED}{BOLD}🚨 SOS FROM {sender}{RESET}")

            print(f"{RED}Sender Node: {sender}{RESET}")
            if dist_meters is not None:
                print(f"{RED}Approx. Distance: {format_distance(dist_meters)}{RESET}")
            print(f"{RED}Location: {loc_str}{RESET}")
            print(f"{RED}Message: {text}{RESET}\n")

        elif msg_type == "audio":
            msg_id_short = msg.get("id", "")[:8]
            duration = msg.get("audio_duration", 5)
            print(f"\n[{ts}] {CYAN}{BOLD}🎤 VOICE NOTE ({duration}s) FROM {sender}{RESET}")
            print(f"  Message ID: {msg_id_short}")
            print(f"  Play command: {GREEN}/play {msg_id_short}{RESET}\n")
        elif msg_type == "broadcast":
            print(f"\n[{ts}] {YELLOW}[BROADCAST]{RESET} {BOLD}{sender}{RESET} > *: {text}")
        elif msg_type == "chat":
            target = "YOU" if recipient == self.node.node_id else recipient
            print(f"\n[{ts}] {CYAN}{BOLD}{sender}{RESET} > {BOLD}{target}{RESET}: {text}")

        sys.stdout.write(self.get_prompt_str())
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

        sys.stdout.write(self.get_prompt_str())
        sys.stdout.flush()

    async def run(self):
        self.node.set_callbacks(
            on_display_msg=self.on_display_msg,
            on_status_update=self.on_status_update,
            on_peer_change=self.on_peer_change
        )
        await self.node.start()
        self.display_banner()

        loop = asyncio.get_event_loop()

        while self.running:
            try:
                line = await loop.run_in_executor(None, input, self.get_prompt_str())
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
        parts = cmd_line.split(" ")
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
                print(f"\n{BOLD}Real-Time Nearby Nodes ({len(peers)} active):{RESET}")
                now = time.time()
                for p in peers:
                    ago = int(now - p["last_seen"])
                    print(f"  {CYAN}{p['node_id']:<15}{RESET} {p['address']:<15}:{p['port']}  last seen {ago} sec ago")
                print()
        elif cmd == "/msg":
            sub_parts = cmd_line.split(" ", 2)
            if len(sub_parts) < 3:
                print(f"{YELLOW}Usage: /msg <node_id> <message>{RESET}")
                return
            target_node = sub_parts[1]
            text = sub_parts[2]
            print(f"{GREEN}✓ Message queued{RESET}")
            await self.node.send_chat(target_node, text)
        elif cmd == "/broadcast":
            text = cmd_line[len("/broadcast"):].strip()
            if not text:
                print(f"{YELLOW}Usage: /broadcast <message>{RESET}")
                return
            print(f"{GREEN}✓ Broadcast message queued{RESET}")
            await self.node.send_broadcast(text)
        elif cmd == "/record":
            sub_parts = cmd_line.split(" ")
            target_node = sub_parts[1] if len(sub_parts) >= 2 else "*"
            duration = int(sub_parts[2]) if len(sub_parts) >= 3 and sub_parts[2].isdigit() else 5

            print(f"\n{RED}{BOLD}🎙 RECORDING VOICE NOTE ({duration} seconds)... Speak now!{RESET}")
            msg = await self.node.send_audio(target_node, duration_seconds=duration)
            if msg:
                print(f"{GREEN}✓ Voice note recorded and queued ({len(msg['audio_data'])} bytes){RESET}\n")
            else:
                print(f"{RED}Audio recording failed. Ensure termux-api / ffmpeg or sox is available.{RESET}\n")
        elif cmd == "/play":
            if len(parts) < 2:
                print(f"{YELLOW}Usage: /play <message_id_prefix>{RESET}")
                return
            msg_id_prefix = parts[1]
            success, msg_str = self.node.play_audio_message(msg_id_prefix)
            if success:
                print(f"{GREEN}✓ {msg_str}{RESET}")
            else:
                print(f"{RED}Playback failed: {msg_str}{RESET}")
        elif cmd == "/map":
            if len(parts) >= 2 and parts[1].lower() == "open":
                target_id = parts[2] if len(parts) >= 3 else None
                if target_id:
                    nav_info, err = self.node.get_navigation_target(target_id)
                    if err:
                        print(f"{RED}{err}{RESET}")
                        return
                    t = nav_info["target"]
                    geo_url = f"geo:{t['latitude']:.6f},{t['longitude']:.6f}?q={t['latitude']:.6f},{t['longitude']:.6f}({t['id']})"
                else:
                    my_loc = self.node.location_manager.get_location()
                    if not my_loc:
                        print(f"{YELLOW}Location UNKNOWN. Set coordinates manually via '/location set <lat> <lon>'{RESET}")
                        return
                    geo_url = f"geo:{my_loc['latitude']:.6f},{my_loc['longitude']:.6f}"

                print(f"{CYAN}Opening target location in Android offline map app (OsmAnd / Organic Maps)...{RESET}")
                if shutil.which("termux-open-url"):
                    try:
                        subprocess.Popen(["termux-open-url", geo_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        print(f"{GREEN}✓ Launched map intent: {geo_url}{RESET}")
                    except Exception as e:
                        print(f"{RED}Failed to open intent: {e}{RESET}")
                else:
                    print(f"{YELLOW}termux-open-url unavailable. Geo Intent URL: {geo_url}{RESET}")

            elif len(parts) >= 2 and parts[1].lower() == "html":
                radar_info, err = self.node.get_radar_nodes()
                if err:
                    print(f"{YELLOW}{err}{RESET}")
                    return
                html_path = self.node.config.config_dir / "map.html"
                generate_offline_html_map(radar_info, self.node.node_id, html_path)
                print(f"{GREEN}✓ Self-contained offline HTML map generated at: {html_path}{RESET}")
                if shutil.which("termux-open-url"):
                    try:
                        subprocess.Popen(["termux-open-url", str(html_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        print(f"{GREEN}✓ Opened map in browser.{RESET}")
                    except Exception:
                        pass
            else:
                radar_info, err = self.node.get_radar_nodes()
                if err:
                    print(f"{YELLOW}{err}{RESET}")
                else:
                    print(render_ascii_radar(radar_info, self.node.node_id))

        elif cmd == "/navigate":
            if len(parts) < 2:
                print(f"{YELLOW}Usage: /navigate <node_id|sos_id|lat,lon>{RESET}")
                return
            target_id = parts[1]
            nav_info, err = self.node.get_navigation_target(target_id)
            if err:
                print(f"{RED}{err}{RESET}")
            else:
                my_loc = nav_info["my_location"]
                t = nav_info["target"]

                dist_str = format_distance(t["distance_meters"])
                bearing = t["bearing"]
                cardinal = t["cardinal"]

                print(f"\n{CYAN}{BOLD}🧭 OFFLINE COMPASS NAVIGATION GUIDANCE{RESET}")
                print(f"  {BOLD}Destination:{RESET}             {CYAN}{t['id']}{RESET}")
                print(f"  {BOLD}Target Coordinates:{RESET}      {t['latitude']:.6f}, {t['longitude']:.6f}")
                print(f"  {BOLD}Your Coordinates:{RESET}        {my_loc['latitude']:.6f}, {my_loc['longitude']:.6f}\n")
                print(f"  {BOLD}Approx. Distance:{RESET}        {GREEN}{dist_str}{RESET}")
                print(f"  {BOLD}Compass Bearing:{RESET}         {YELLOW}{bearing}° ({cardinal}){RESET}\n")
                print(f"{BOLD}NAVIGATION INSTRUCTION:{RESET}")
                print(f"  {GREEN}Face {cardinal} ({bearing}°) and walk forward for approximately {dist_str}.{RESET}\n")

        elif cmd == "/location":
            if len(parts) >= 4 and parts[1].lower() == "set":
                lat, lon = parts[2], parts[3]
                success = self.node.set_manual_location(lat, lon)
                if success:
                    print(f"{GREEN}✓ Location manually set to ({lat}, {lon}){RESET}")
                else:
                    print(f"{RED}Invalid coordinates. Usage: /location set <latitude> <longitude>{RESET}")
            elif len(parts) >= 2 and parts[1].lower() == "clear":
                self.node.location_manager.clear_manual_location()
                print(f"{GREEN}✓ Manual location cleared. Reverted to automatic lookup.{RESET}")
            elif len(parts) >= 2 and parts[1].lower() in ("refresh", "update"):
                print(f"{CYAN}Refreshing location lookup (GPS / IP)...{RESET}")
                loop = asyncio.get_event_loop()
                loc = await loop.run_in_executor(None, self.node.location_manager.get_location_fresh)
                if loc:
                    provider = loc.get("provider", "unknown")
                    ts = format_time(loc.get("timestamp", time.time()))
                    print(f"\n{BOLD}Location Updated:{RESET}")
                    print(f"  Latitude:  {CYAN}{loc['latitude']}{RESET}")
                    print(f"  Longitude: {CYAN}{loc['longitude']}{RESET}")
                    print(f"  Provider:  {provider}")
                    print(f"  Updated:   {ts}\n")
                else:
                    print(f"{YELLOW}Location: UNKNOWN. Try manually setting coordinates with '/location set <lat> <lon>'{RESET}")
            else:
                loc = self.node.location_manager.get_location()
                if loc:
                    provider = loc.get("provider", "unknown")
                    ts = format_time(loc.get("timestamp", time.time()))
                    print(f"\n{BOLD}Current Node Location:{RESET}")
                    print(f"  Latitude:  {CYAN}{loc['latitude']}{RESET}")
                    print(f"  Longitude: {CYAN}{loc['longitude']}{RESET}")
                    print(f"  Provider:  {provider}")
                    print(f"  Updated:   {ts}\n")
                else:
                    print(f"{YELLOW}Location: UNKNOWN (Searching via Termux GPS / IP Geolocation in background).{RESET}")
                    print(f"{YELLOW}You can force a lookup with '/location refresh' or set coordinates manually using '/location set <lat> <lon>'{RESET}")
        elif cmd == "/sos":
            if len(parts) >= 2 and parts[1].lower() == "radius":
                if len(parts) >= 3:
                    meters = parts[2]
                    success = self.node.set_sos_proximity_radius(meters)
                    if success:
                        print(f"{GREEN}✓ SOS proximity vibration alert radius set to {meters} meters{RESET}")
                    else:
                        print(f"{RED}Invalid radius. Usage: /sos radius <meters>{RESET}")
                else:
                    current_r = self.node.config.sos_proximity_radius
                    print(f"\n{BOLD}Current SOS Proximity Vibration Radius:{RESET} {CYAN}{current_r} meters{RESET}\n")
                return

            text = cmd_line[len("/sos"):].strip()
            if not text:
                text = "Emergency assistance required"
            print(f"\n{RED}{BOLD}🚨 SOS CREATED{RESET}")
            print(f"Node: {self.node.node_id}")
            print(f"Status: QUEUED / TRANSMITTING...")
            msg = await self.node.send_sos(text)
            lat = msg.get("latitude")
            lon = msg.get("longitude")
            if lat not in (None, "UNKNOWN") and lon not in (None, "UNKNOWN"):
                try:
                    loc_str = f"{float(lat):.6f}, {float(lon):.6f}"
                except (ValueError, TypeError):
                    loc_str = "UNKNOWN"
            else:
                loc_str = "UNKNOWN"

            print(f"Location: {RED}{loc_str}{RESET}")
            if loc_str == "UNKNOWN":
                print(f"{YELLOW}⚠ GPS coordinates unavailable from OS.{RESET}")
                print(f"{YELLOW}  - Set exact location manually anytime: /location set <lat> <lon>{RESET}")
                print(f"{YELLOW}  - Example: /location set 13.0827 80.2707{RESET}\n")
            else:
                print()
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
            loc = self.node.location_manager.get_location()
            loc_str = f"{loc['latitude']}, {loc['longitude']}" if loc else "UNKNOWN"

            print(f"\n{BOLD}EmergencyMesh Node Status:{RESET}")
            print(f"  Node ID:          {CYAN}{self.node.node_id}{RESET}")
            print(f"  Local IP:         {ip}")
            print(f"  TCP Port:         {self.node.config.tcp_port}")
            print(f"  UDP Port:         {self.node.config.udp_port}")
            print(f"  Peer Count:       {GREEN}{len(peers)}{RESET}")
            print(f"  Location:         {loc_str}")
            print(f"  SOS Radius:       {CYAN}{self.node.config.sos_proximity_radius} meters{RESET}")
            print(f"  DB Path:          {self.node.config.db_path}\n")
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
