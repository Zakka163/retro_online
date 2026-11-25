"""Background Device Heartbeat & Remote Command Executor for Arcade Online Launcher."""

import json
import logging
import os
import platform
import re
import socket
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Arcade.DeviceReporter")


def _get_machine_id(player_name: str) -> str:
    """Build a stable machine_id per cabinet."""
    mid = ""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    mid = f.read().strip()[:12]
                if mid:
                    break
            except Exception:
                pass
    host = socket.gethostname() or "arcade"
    clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", player_name.strip()) or "cab"
    return f"{host}-{mid}" if mid else f"{host}-{clean_name}"


def _read_local_config(config_path: str) -> Dict[str, Any]:
    """Read local config.json (supporting // comments)."""
    if not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        pat = re.compile(r'(?:/\*.*?\*/|//[^\r\n]*|#[^\r\n]*)|("(?:\\.|[^"\\])*")', re.DOTALL)
        clean = pat.sub(lambda m: m.group(1) if m.group(1) is not None else "", content)
        data = json.loads(clean)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _update_local_config(config_path: str, updates: Dict[str, Any]) -> bool:
    """Safely update keys in local config.json (supports // comments)."""
    try:
        cfg: Dict[str, Any] = {}
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            pat = re.compile(r'(?:/\*.*?\*/|//[^\r\n]*|#[^\r\n]*)|("(?:\\.|[^"\\])*")', re.DOTALL)
            clean = pat.sub(lambda m: m.group(1) if m.group(1) is not None else "", content)
            cfg = json.loads(clean)

        for key_path, val in updates.items():
            parts = key_path.split(".")
            target = cfg
            for p in parts[:-1]:
                if p not in target or not isinstance(target[p], dict):
                    target[p] = {}
                target = target[p]
            target[parts[-1]] = val

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        return True
    except Exception as e:
        logger.warning(f"[Reporter] Gagal memperbarui {config_path}: {e}")
        return False


class DeviceReporter:
    """Periodically reports machine status & game list to VPS and runs queued admin commands."""

    def __init__(
        self,
        server_url: str,
        player_name: str,
        config_path: str = "config.json",
        get_games_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        on_rename_fn: Optional[Callable[[str], None]] = None,
        on_restart_fn: Optional[Callable[[], None]] = None,
        interval_seconds: float = 25.0,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.player_name = player_name
        self.config_path = config_path
        self.get_games_fn = get_games_fn
        self.on_rename_fn = on_rename_fn
        self.on_restart_fn = on_restart_fn
        self.interval_seconds = interval_seconds

        self.machine_id = _get_machine_id(player_name)
        self.status = "idle"
        self.current_game = ""
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def set_activity(self, status: str, current_game: str = "") -> None:
        self.status = status
        self.current_game = current_game

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        # Small delay so UI startup isn't slowed down
        if self._stop_event.wait(1.5):
            return
        while not self._stop_event.is_set():
            try:
                self.send_heartbeat_once()
            except Exception as e:
                logger.debug(f"[Reporter] Heartbeat dilewati: {e}")
            if self._stop_event.wait(self.interval_seconds):
                break

    def send_heartbeat_once(self) -> None:
        from .connection_manager import get_local_ip, get_network_indicator_text
        from .system_info import LAUNCHER_VERSION

        games_payload: List[Dict[str, Any]] = []
        if self.get_games_fn:
            try:
                for g in self.get_games_fn():
                    hashes = g.get("rom_hashes") or {}
                    rom_hash = ""
                    if isinstance(hashes, dict) and hashes:
                        rom_hash = str(next(iter(hashes.values())))
                    rom_path = str(g.get("rom_path") or "")
                    fname = os.path.basename(rom_path) if rom_path else f"{g.get('game_id', '')}.zip"
                    games_payload.append({
                        "game_id": g.get("game_id", ""),
                        "filename": fname,
                        "display_name": g.get("display_name", ""),
                        "core": g.get("retroarch_core", ""),
                        "rom_hash": rom_hash,
                        "status": g.get("status", "ready"),
                    })
            except Exception:
                pass

        payload = {
            "machine_id": self.machine_id,
            "player_name": self.player_name,
            "hostname": socket.gethostname(),
            "ip_local": get_local_ip(),
            "os_info": f"{platform.system()} {platform.machine()}",
            "launcher_version": LAUNCHER_VERSION,
            "wifi_signal": get_network_indicator_text(),
            "status": self.status,
            "current_game": self.current_game,
            "games": games_payload,
            "config": _read_local_config(self.config_path),
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.server_url}/api/devices/heartbeat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        for cmd in body.get("commands", []):
            self._handle_command(cmd)

    def _handle_command(self, cmd: Dict[str, Any]) -> None:
        name = cmd.get("command", "")
        payload = cmd.get("payload") or {}
        logger.info(f"[Reporter] Menerima perintah admin: {name}")

        if name == "rename":
            new_name = str(payload.get("player_name", "")).strip()
            if new_name:
                if _update_local_config(self.config_path, {"client.player_name": new_name}):
                    self.player_name = new_name
                    if self.on_rename_fn:
                        self.on_rename_fn(new_name)

        elif name == "set_config":
            if isinstance(payload, dict) and payload:
                if _update_local_config(self.config_path, payload):
                    new_name = str(payload.get("client.player_name", "")).strip()
                    if new_name and new_name != self.player_name:
                        self.player_name = new_name
                        if self.on_rename_fn:
                            self.on_rename_fn(new_name)
                    if self.on_restart_fn and self.status == "idle":
                        self.on_restart_fn()

        elif name == "check_update":
            try:
                from .system_info import LAUNCHER_VERSION
                from .updater import check_for_update, download_and_apply_update, get_effective_version, sync_roms_from_server
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                roms_dir = os.path.join(project_root, "roms")
                cur_ver = get_effective_version(LAUNCHER_VERSION, project_root)
                dl, rm = sync_roms_from_server(self.server_url, roms_dir)
                manifest = check_for_update(self.server_url, cur_ver, timeout=5.0)
                updated = False
                if manifest:
                    updated, _ = download_and_apply_update(self.server_url, manifest, project_root)
                if (updated or dl > 0 or rm > 0) and self.on_restart_fn and self.status == "idle":
                    self.on_restart_fn()
            except Exception as e:
                logger.warning(f"[Reporter] Gagal menjalankan check_update: {e}")

        elif name == "restart_launcher":
            if self.on_restart_fn and self.status == "idle":
                self.on_restart_fn()

