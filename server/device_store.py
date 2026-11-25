"""SQLite-backed Device & Command Store for Arcade Online Admin Dashboard."""

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional


class DeviceStore:
    """Persists registered arcade cabinets, their game catalogs, and remote command queues."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.environ.get("ARCADE_DB_PATH") or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "arcade.db")
        )
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS devices (
                        machine_id TEXT PRIMARY KEY,
                        player_name TEXT NOT NULL,
                        hostname TEXT DEFAULT '',
                        ip_local TEXT DEFAULT '',
                        ip_public TEXT DEFAULT '',
                        os_info TEXT DEFAULT '',
                        launcher_version TEXT DEFAULT '',
                        wifi_signal TEXT DEFAULT '',
                        status TEXT DEFAULT 'idle',
                        current_game TEXT DEFAULT '',
                        games_json TEXT DEFAULT '[]',
                        config_json TEXT DEFAULT '{}',
                        first_seen REAL NOT NULL,
                        last_seen REAL NOT NULL
                    )
                    """
                )
                try:
                    conn.execute("ALTER TABLE devices ADD COLUMN config_json TEXT DEFAULT '{}'")
                except sqlite3.OperationalError:
                    pass
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS device_commands (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        machine_id TEXT NOT NULL,
                        command TEXT NOT NULL,
                        payload_json TEXT DEFAULT '{}',
                        status TEXT DEFAULT 'pending',
                        created_at REAL NOT NULL,
                        sent_at REAL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def upsert_heartbeat(
        self,
        machine_id: str,
        player_name: str,
        hostname: str = "",
        ip_local: str = "",
        ip_public: str = "",
        os_info: str = "",
        launcher_version: str = "",
        wifi_signal: str = "",
        status: str = "idle",
        current_game: str = "",
        games: Optional[List[Dict[str, Any]]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Update device state and pop pending remote commands for it."""
        now = time.time()
        games_json = json.dumps(games if games is not None else [])
        config_json = json.dumps(config if config is not None else {})
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    "SELECT first_seen, games_json, config_json FROM devices WHERE machine_id = ?",
                    (machine_id,),
                ).fetchone()

                if existing:
                    final_games_json = games_json if games is not None else existing["games_json"]
                    final_config_json = config_json if config is not None else existing["config_json"]
                    conn.execute(
                        """
                        UPDATE devices
                        SET player_name = ?, hostname = ?, ip_local = ?, ip_public = ?,
                            os_info = ?, launcher_version = ?, wifi_signal = ?,
                            status = ?, current_game = ?, games_json = ?, config_json = ?, last_seen = ?
                        WHERE machine_id = ?
                        """,
                        (
                            player_name, hostname, ip_local, ip_public,
                            os_info, launcher_version, wifi_signal,
                            status, current_game, final_games_json, final_config_json, now, machine_id,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO devices (
                            machine_id, player_name, hostname, ip_local, ip_public,
                            os_info, launcher_version, wifi_signal, status,
                            current_game, games_json, config_json, first_seen, last_seen
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            machine_id, player_name, hostname, ip_local, ip_public,
                            os_info, launcher_version, wifi_signal, status,
                            current_game, games_json, config_json, now, now,
                        ),
                    )

                rows = conn.execute(
                    """
                    SELECT id, command, payload_json, created_at
                    FROM device_commands
                    WHERE machine_id = ? AND status = 'pending'
                    ORDER BY id ASC
                    """,
                    (machine_id,),
                ).fetchall()

                commands: List[Dict[str, Any]] = []
                if rows:
                    cmd_ids = [r["id"] for r in rows]
                    placeholders = ",".join("?" for _ in cmd_ids)
                    conn.execute(
                        f"UPDATE device_commands SET status = 'sent', sent_at = ? WHERE id IN ({placeholders})",
                        [now, *cmd_ids],
                    )
                    for r in rows:
                        try:
                            payload = json.loads(r["payload_json"] or "{}")
                        except Exception:
                            payload = {}
                        commands.append({
                            "id": r["id"],
                            "command": r["command"],
                            "payload": payload,
                            "created_at": r["created_at"],
                        })

                conn.commit()
                return commands
            finally:
                conn.close()

    def queue_command(
        self,
        machine_id: str,
        command: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Queue a remote command for a machine."""
        now = time.time()
        payload_json = json.dumps(payload or {})
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO device_commands (machine_id, command, payload_json, status, created_at)
                    VALUES (?, ?, ?, 'pending', ?)
                    """,
                    (machine_id, command, payload_json, now),
                )
                conn.commit()
                return int(cur.lastrowid)
            finally:
                conn.close()

    def list_devices(self, offline_after_seconds: float = 90.0) -> List[Dict[str, Any]]:
        """Return all registered devices with computed online/offline state."""
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM devices ORDER BY last_seen DESC"
                ).fetchall()
                pending_rows = conn.execute(
                    "SELECT machine_id, COUNT(*) AS cnt FROM device_commands WHERE status = 'pending' GROUP BY machine_id"
                ).fetchall()
                pending_map = {r["machine_id"]: r["cnt"] for r in pending_rows}
            finally:
                conn.close()

        result: List[Dict[str, Any]] = []
        for r in rows:
            age = max(0.0, now - float(r["last_seen"]))
            online = age <= offline_after_seconds
            try:
                games = json.loads(r["games_json"] or "[]")
            except Exception:
                games = []
            try:
                cfg = json.loads(r["config_json"] or "{}")
            except Exception:
                cfg = {}
            result.append({
                "machine_id": r["machine_id"],
                "player_name": r["player_name"],
                "hostname": r["hostname"],
                "ip_local": r["ip_local"],
                "ip_public": r["ip_public"],
                "os_info": r["os_info"],
                "launcher_version": r["launcher_version"],
                "wifi_signal": r["wifi_signal"],
                "status": r["status"] if online else "offline",
                "online": online,
                "current_game": r["current_game"] if online else "",
                "games_count": len(games),
                "games": games,
                "config": cfg,
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "seconds_ago": round(age, 1),
                "pending_commands": pending_map.get(r["machine_id"], 0),
            })
        return result

    def get_games_summary(self, offline_after_seconds: float = 90.0) -> List[Dict[str, Any]]:
        """Aggregate game catalog and compatibility across all registered devices."""
        devices = self.list_devices(offline_after_seconds=offline_after_seconds)
        games_map: Dict[str, Dict[str, Any]] = {}

        for dev in devices:
            for g in dev.get("games", []):
                gid = str(g.get("game_id") or g.get("rom_file") or "").strip()
                if not gid:
                    continue
                entry = games_map.setdefault(gid, {
                    "game_id": gid,
                    "filename": g.get("filename") or f"{gid}.zip",
                    "display_name": g.get("display_name") or gid,
                    "core": g.get("core") or g.get("retroarch_core") or "",
                    "machines": [],
                    "hashes": set(),
                    "cores": set(),
                })
                rom_hash = str(g.get("crc32") or g.get("sha1") or g.get("rom_hash") or "")
                core_name = str(g.get("core") or g.get("retroarch_core") or "")
                if rom_hash:
                    entry["hashes"].add(rom_hash)
                if core_name:
                    entry["cores"].add(core_name)
                entry["machines"].append({
                    "machine_id": dev["machine_id"],
                    "player_name": dev["player_name"],
                    "online": dev["online"],
                    "core": core_name,
                    "rom_hash": rom_hash,
                    "status": g.get("status", "ready"),
                })

        summary: List[Dict[str, Any]] = []
        for entry in games_map.values():
            hashes = sorted(entry.pop("hashes"))
            cores = sorted(entry.pop("cores"))
            entry["hash_mismatch"] = len(hashes) > 1
            entry["core_mismatch"] = len(cores) > 1
            entry["hashes"] = hashes
            entry["cores"] = cores
            entry["machine_count"] = len(entry["machines"])
            summary.append(entry)

        summary.sort(key=lambda x: x["display_name"].lower())
        return summary

    def delete_device(self, machine_id: str) -> bool:
        """Delete a registered device and its queued commands."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM devices WHERE machine_id = ?", (machine_id,))
                conn.execute("DELETE FROM device_commands WHERE machine_id = ?", (machine_id,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

