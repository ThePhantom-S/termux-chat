import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

class Storage:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
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
                    status TEXT,
                    audio_data TEXT,
                    audio_duration INTEGER,
                    audio_format TEXT
                )
            """)
            # Schema migration for existing databases
            cursor.execute("PRAGMA table_info(messages)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "audio_data" not in columns:
                cursor.execute("ALTER TABLE messages ADD COLUMN audio_data TEXT")
            if "audio_duration" not in columns:
                cursor.execute("ALTER TABLE messages ADD COLUMN audio_duration INTEGER")
            if "audio_format" not in columns:
                cursor.execute("ALTER TABLE messages ADD COLUMN audio_format TEXT")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS peers (
                    node_id TEXT PRIMARY KEY,
                    address TEXT,
                    port INTEGER,
                    last_seen INTEGER
                )
            """)
            conn.commit()

    def save_message(self, msg, status="RECEIVED"):
        lat = msg.get("latitude")
        if lat is not None and lat != "UNKNOWN":
            try:
                lat = float(lat)
            except (ValueError, TypeError):
                lat = None
        else:
            lat = None

        lon = msg.get("longitude")
        if lon is not None and lon != "UNKNOWN":
            try:
                lon = float(lon)
            except (ValueError, TypeError):
                lon = None
        else:
            lon = None

        audio_data = msg.get("audio_data")
        audio_duration = msg.get("audio_duration")
        audio_format = msg.get("audio_format")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO messages (
                    id, sender, recipient, type, priority, text,
                    latitude, longitude, timestamp, ttl, status,
                    audio_data, audio_duration, audio_format
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg.get("id"),
                msg.get("sender"),
                msg.get("recipient"),
                msg.get("type"),
                msg.get("priority", "normal"),
                msg.get("text", ""),
                lat,
                lon,
                int(msg.get("timestamp", time.time())),
                int(msg.get("ttl", 5)),
                status,
                audio_data,
                audio_duration,
                audio_format
            ))
            conn.commit()

    def update_message_status(self, msg_id, status):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET status = ? WHERE id = ?", (status, msg_id))
            conn.commit()

    def get_message(self, msg_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_recent_messages(self, limit=50):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_queued_messages(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages WHERE status = 'QUEUED' ORDER BY timestamp ASC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def upsert_peer(self, node_id, address, port, expiry_seconds=30):
        now = int(time.time())
        cutoff = now - expiry_seconds

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_seen FROM peers WHERE node_id = ?", (node_id,))
            existing = cursor.fetchone()
            is_new = (existing is None) or (existing["last_seen"] < cutoff)

            cursor.execute("""
                INSERT INTO peers (node_id, address, port, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    address = excluded.address,
                    port = excluded.port,
                    last_seen = excluded.last_seen
            """, (node_id, address, port, now))
            conn.commit()

            cursor.execute("SELECT COUNT(*) as active_cnt FROM peers WHERE last_seen >= ?", (cutoff,))
            active_count = cursor.fetchone()["active_cnt"]

            return is_new, active_count

    def get_active_peers(self, expiry_seconds=30):
        cutoff = int(time.time()) - expiry_seconds
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM peers WHERE last_seen >= ? ORDER BY last_seen DESC", (cutoff,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_all_peers(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM peers ORDER BY last_seen DESC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_peer(self, node_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM peers WHERE node_id = ?", (node_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def remove_peer(self, node_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM peers WHERE node_id = ?", (node_id,))
            conn.commit()
