# EmergencyMesh 🚨

**Real-World Offline Emergency Mesh Communication System for Android Termux**

EmergencyMesh is a terminal-based, peer-to-peer (P2P) emergency chat and SOS alert application designed to run inside **Termux on physical Android smartphones**. It enables offline phone-to-phone communication without cellular data, internet infrastructure, cloud servers, or SIM cards.

---

## 1. Real Phone Deployment Setup

To deploy EmergencyMesh across 2 to 3 Android phones:

### Step 1: Install Termux on Each Phone
1. Download and install **Termux** on each phone (available via F-Droid or GitHub releases).
2. Download and install **Termux:API** app from F-Droid to enable hardware GPS access.

### Step 2: Install EmergencyMesh on Each Phone
Open Termux on each phone and run:

```bash
# Update packages and install python + termux-api
pkg update && pkg install -y git python termux-api

# Grant storage & location permissions
termux-setup-storage

# Clone emergency-mesh repository
cd ~
git clone https://github.com/ThePhantom-S/termux-chat.git
cd termux-chat

# Run installation script
chmod +x install.sh
./install.sh
```

---

## 2. Connecting 3 Physical Phones (Phone A ↔ Phone B ↔ Phone C)

No SIM card or mobile data is required!

### Network Configuration (Wi-Fi Hotspot)
1. On **Phone A**, enable **Personal Hotspot** (Mobile Data can be turned OFF).
2. Connect **Phone B** and **Phone C** to Phone A's Wi-Fi hotspot.
3. Start EmergencyMesh on all 3 phones:
   ```bash
   python3 -m emergency_mesh
   ```

### Peer Discovery & Link Setup

#### Automatic UDP Discovery
In most Wi-Fi hotspot networks, the phones will automatically discover each other via UDP broadcast beacons (`255.255.255.255`) within 5 seconds!

Type `/nodes` on any phone to check discovered peers:
```text
> /nodes

Nearby nodes:
  RESCUE-A82F   192.168.43.1:9876    last seen 2 sec ago
  MEDIC-44D1    192.168.43.18:9876   last seen 4 sec ago
```

#### Manual Link (`/connect`) Fallback
If an Android Hotspot suppresses UDP broadcast packets:
1. Check Phone A's IP address by running `/status` inside EmergencyMesh (e.g. `192.168.43.1`).
2. On Phone B and Phone C, type:
   ```text
   > /connect 192.168.43.1 9876
   ```

---

## 3. Real 3-Phone Multi-Hop SOS Demo Scenario

Suppose **Phone A** is out of range of **Phone C**, but **Phone B** is in range of both:

$$\text{Phone A} \longrightarrow \text{Phone B} \longrightarrow \text{Phone C}$$

### Demo Step 1: Send SOS from Phone A
On **Phone A**, type:
```text
> /sos Medical assistance required in Sector 4
```

**Phone A Display:**
```text
🚨 SOS CREATED
Node: RESCUE-A82F
Status: QUEUED / TRANSMITTING...
Location: 13.123456, 80.123456
```

### Demo Step 2: Relay on Phone B
**Phone B** receives the SOS broadcast and automatically relays it across the mesh network:
```text
🚨 SOS FROM RESCUE-A82F
Location: 13.123456, 80.123456
Message: Medical assistance required in Sector 4
```

### Demo Step 3: Reception on Phone C
**Phone C** receives the forwarded SOS message from Phone A (via Phone B):
```text
🚨 SOS FROM RESCUE-A82F
Location: 13.123456, 80.123456
Message: Medical assistance required in Sector 4
```

---

## 4. Interactive Command Reference

| Command | Description |
| :--- | :--- |
| `/help` | Print command usage manual |
| `/nodes` | List active nearby mesh nodes and last seen times |
| `/msg <node_id> <message>` | Send direct offline text message to specific node |
| `/broadcast <message>` | Broadcast message to all nearby nodes |
| `/sos [message]` | Broadcast high-priority emergency alert with GPS location |
| `/location` | View or set node GPS/manual location coordinates (`/location set <lat> <lon>`) |
| `/history` | View stored message history from SQLite database |
| `/status` | View node configuration, local IP address, and ports |
| `/connect <ip> [port]` | Manually connect to peer IP address |
| `/id` | Print this node's unique ID |
| `/quit` | Exit EmergencyMesh |

---

## 5. Technical Architecture

- **Transport Layer**: Asynchronous TCP socket server listening on port `9876`.
- **Peer Discovery**: UDP broadcast beacons sent every 5s to port `9877`.
- **Store-and-Forward Mesh Router**:
  - Multi-hop message propagation with Time-To-Live (`TTL`) enforcement.
  - Duplicate message suppression cache.
  - Automatic delivery acknowledgements (`ACK`).
  - SQLite offline message queue with automatic retry worker.
- **GPS Coordinates**: Queries `termux-location` CLI via standard Python `subprocess`. Falls back to `UNKNOWN` if GPS fix is unavailable.
- **Database Storage**: SQLite database stored locally at `~/.emergency_mesh/mesh.db`.

---

## 6. Android/Termux Realities & Limitations

- **Wi-Fi Hotspot Required**: Standard Termux standard library Python uses POSIX TCP/UDP sockets over Wi-Fi or Personal Hotspot interfaces.
- **GPS Permission**: Ensure Termux:API has location permissions enabled in Android Settings → Apps → Termux:API → Permissions → Location.
- **Power Savings**: Turn off battery optimization for Termux so background message routing remains active when the screen dims.
