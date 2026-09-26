# Software Requirements Specification (SRS)
## EmergencyMesh (`termux-chat`) - Offline P2P Emergency Communication System

**Document Version:** 1.0.0  
**Date:** September 26, 2026  
**Target Platform:** Android Termux (Python 3)  
**Standard:** IEEE 830 / ISO/IEC/IEEE 29148 Compliant  

---

## 1. Introduction

### 1.1 Purpose
This Software Requirements Specification (SRS) document defines the software, functional, non-functional, and architectural requirements for **EmergencyMesh** (repository: `termux-chat`). EmergencyMesh is a terminal-based, peer-to-peer (P2P) emergency text communication and SOS alert application designed to run entirely within Android Termux environments without requiring cellular networks, internet infrastructure, cloud servers, or SIM cards.

### 1.2 Scope
EmergencyMesh enables nearby Android smartphones to form an ad-hoc offline mesh network over Wi-Fi Hotspot or local network interfaces. Key capabilities include:
- Multi-hop store-and-forward text message routing.
- Priority SOS emergency broadcasts containing real-time GPS coordinates.
- Automatic 4-layer peer discovery.
- SQLite-backed offline message queueing and delivery acknowledgements.
- High-visibility interactive ANSI command-line interface.

### 1.3 Definitions, Acronyms, and Abbreviations
- **P2P**: Peer-to-Peer network topology.
- **TTL**: Time-To-Live (hop count limit for network packets).
- **ACK**: Delivery Acknowledgement packet.
- **SOS**: High-priority distress signal broadcast.
- **Termux**: Android terminal emulator and Linux environment application.
- **Termux:API**: Termux addon exposing Android OS hardware APIs (e.g. GPS) to shell scripts.
- **POSIX**: Portable Operating System Interface standard.

### 1.4 References
1. IEEE Std 830-1998, *IEEE Recommended Practice for Software Requirements Specifications*.
2. Python 3 standard library documentation (`asyncio`, `socket`, `sqlite3`).
3. Termux Developer Documentation (`termux-location` CLI specification).

---

## 2. Overall Description

### 2.1 Product Perspective
EmergencyMesh operates as a standalone, self-contained terminal application running within Python 3 inside Termux. It uses standard POSIX socket APIs (`AF_INET`, `SOCK_STREAM`, `SOCK_DGRAM`) to communicate over local Wi-Fi / Hotspot interfaces, operating independently of cellular networks or third-party backend servers.

```
+-------------------------------------------------------------------+
|                        Android Smartphone                         |
|  +-------------------------------------------------------------+  |
|  |                     Termux Environment                      |  |
|  |  +-------------------------------------------------------+  |  |
|  |  |                 EmergencyMesh System                  |  |  |
|  |  | +------------+  +-------------+  +------------------+ |  |  |
|  |  | | ANSI CLI   |  | Mesh Router |  | SQLite Database  | |  |  |
|  |  | +------------+  +-------------+  +------------------+ |  |  |
|  |  | +------------+  +-------------+  +------------------+ |  |  |
|  |  | | Transport  |  | Discovery   |  | Location Manager | |  |  |
|  |  | +------------+  +-------------+  +------------------+ |  |  |
|  |  +-------------------------------------------------------+  |  |
|  +-------------------------------------------------------------+  |
|         │                        │                        │       |
|   POSIX Sockets            POSIX Sockets            termux-location|
+---------│------------------------│------------------------│-------+
          ▼                        ▼                        ▼
     Wi-Fi / TCP              Wi-Fi / UDP             Android GPS
```

### 2.2 Product Functions
1. **Node Identity**: Auto-generates persistent unique Node IDs (e.g., `RESCUE-A82F`).
2. **Peer Discovery**: Continuously broadcasts and listens for nearby nodes across 4 network vectors.
3. **Direct Chat**: Reliable 1-to-1 text messaging between active or offline nodes.
4. **Broadcast Messaging**: Multi-hop message flooding to all reachable nodes within range.
5. **SOS Emergency Alerting**: High-priority alert broadcasting real-time GPS coordinates.
6. **Store-and-Forward Relaying**: Intermediate nodes forward messages meant for out-of-range nodes.
7. **Offline Queueing**: Retains un-acknowledged messages locally in SQLite and retries upon peer reconnection.

### 2.3 User Classes and Characteristics
- **Emergency Rescuers & First Responders**: Require fast, reliable SOS reception and coordinate tracking.
- **Off-Grid / Disaster Survivors**: Require zero-setup text messaging when cellular towers are down.
- **System Administrators / Developers**: Need access to status diagnostic logs, custom ports, and manual peer linking.

### 2.4 Operating Environment
- **OS**: Android 7.0+ running Termux.
- **Runtime**: Python 3.8 or higher.
- **Hardware Prerequisites**: Wi-Fi radio (Client or Personal Hotspot mode), GPS module (optional via Termux:API).
- **Storage**: Minimum 10 MB free internal storage for SQLite database.

### 2.5 Design and Implementation Constraints
1. **Zero External Dependencies**: Must run entirely on Python 3 standard library modules.
2. **No GUI Requirement**: Interactive interface must rely exclusively on ANSI terminal formatting.
3. **Non-Blocking Execution**: Network operations must use `asyncio` to prevent UI freezing.

---

## 3. Specific Functional Requirements

### 3.1 Node Initialization & Identity Management
- **FR-1.1**: Upon first execution, the system shall generate a random, persistent Node ID in the format `RESCUE-XXXX` (where `XXXX` is a 4-character alphanumeric suffix).
- **FR-1.2**: Configuration parameters shall be persisted in JSON format at `~/.emergency_mesh/config.json`.
- **FR-1.3**: The default TCP listen port shall be `9876` and UDP broadcast port shall be `9877`.

### 3.2 4-Layer Universal Peer Discovery
- **FR-2.1**: The system shall broadcast UDP presence beacons every 3 seconds across 4 discovery layers:
  1. Global UDP Broadcast (`255.255.255.255`).
  2. Subnet Broadcast (`192.168.x.255`).
  3. Android Hotspot Default Gateway (`192.168.43.1`).
  4. Local Subnet IP Range Probing (`1..25` and `100..120`).
- **FR-2.2**: When a beacon is received, the receiving node shall reply with a direct unicast UDP response beacon to ensure 2-way peer detection.
- **FR-2.3**: Peers inactive for >30 seconds shall be marked offline.

### 3.3 Store-and-Forward Mesh Routing
- **FR-3.1**: Each message shall contain an integer Time-To-Live (`TTL`) field (Default Chat: 5, SOS: 8).
- **FR-3.2**: Intermediate nodes receiving a message not addressed to them shall decrement `TTL` by 1 and forward it to active peers. Messages with `TTL <= 0` shall be dropped.
- **FR-3.3**: Duplicate messages shall be identified via UUID4 message IDs and suppressed using an in-memory sliding window cache.

### 3.4 Priority Emergency SOS Alerting
- **FR-4.1**: Executing `/sos [message]` shall construct a high-priority distress payload.
- **FR-4.2**: The system shall retrieve hardware GPS coordinates via `termux-location` in a non-blocking background thread.
- **FR-4.3**: If hardware GPS is unavailable, the location shall default to `UNKNOWN` or manual coordinates set via `/location set <lat> <lon>`.
- **FR-4.4**: SOS alerts received by any node shall be rendered prominently in red ANSI formatting with coordinates and timestamp.
- **FR-4.5**: The system shall calculate the Haversine distance between receiver and SOS sender. If distance is closer than 6 meters (default `sos_proximity_radius`), the peer's phone shall trigger physical device vibration via `termux-vibrate`.

### 3.5 Delivery Acknowledgement & Offline Queue
- **FR-5.1**: Recipients of direct chat messages shall return a high-priority `ack` packet back to the sender.
- **FR-5.2**: Messages sent to unreachable nodes shall be stored in SQLite with status `QUEUED`.
- **FR-5.3**: A background worker shall retry transmitting queued messages every 10 seconds or immediately upon peer discovery.

---

## 4. External Interface Requirements

### 4.1 Command-Line Interface (CLI)
The CLI shall display a dynamic prompt showing node identity and active peer count:
```text
[RESCUE-DF9G | Peers: 2] > 
```
Supported commands:
- `/help`, `/nodes`, `/msg <node> <text>`, `/broadcast <text>`, `/sos [text]`, `/location [set|clear]`, `/history`, `/status`, `/connect <ip> [port]`, `/id`, `/quit`.

### 4.2 Database Schema

#### `messages` Table
```sql
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    sender TEXT,
    recipient TEXT,
    type TEXT,
    priority TEXT,
    text TEXT,
    latitude REAL,
    longitude REAL,
    timestamp INTEGER,
    ttl INTEGER,
    status TEXT
);
```

#### `peers` Table
```sql
CREATE TABLE IF NOT EXISTS peers (
    node_id TEXT PRIMARY KEY,
    address TEXT,
    port INTEGER,
    last_seen INTEGER
);
```

---

## 5. Non-Functional Requirements

### 5.1 Performance
- **Latency**: Direct 1-hop message delivery latency shall be < 100 ms over local Wi-Fi.
- **Throughput**: Routing engine shall handle at least 50 incoming packets/second without dropping framed payloads.

### 5.2 Reliability
- **Data Integrity**: Database transactions must be managed with context managers ensuring connections close cleanly.
- **Fault Tolerance**: Network socket disconnects or invalid JSON payloads must be caught gracefully without crashing the node process.

### 5.3 Security
- Input payloads must be strictly validated against defined protocol schemas (`validate_message`) to prevent buffer overflows or malformed command injections.
