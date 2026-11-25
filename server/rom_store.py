"""Server-side ROM Repository & Manifest Manager for Auto-Sync to Cabinets."""

import hashlib
import json
import os
import threading
import time
from typing import Any, BinaryIO, Dict, List, Optional


class RomStore:
    """Stores uploaded ROM files and manages games_manifest.json."""

    def __init__(self, roms_dir: Optional[str] = None) -> None:
        self.roms_dir = roms_dir or os.environ.get("ARCADE_ROMS_DIR") or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "roms_repo")
        )
        os.makedirs(self.roms_dir, exist_ok=True)
        self.manifest_path = os.path.join(self.roms_dir, "games_manifest.json")
        self._lock = threading.Lock()
        self._load_or_init()
        self.reconcile_disk()

    def reconcile_disk(self) -> None:
        """Ensure games_manifest.json matches actual .zip/.7z files in roms_dir."""
        try:
            from catalog.scanner import ARCADE_DATABASE
        except Exception:
            ARCADE_DATABASE = {}

        with self._lock:
            data = self._load_or_init()
            existing = {g.get("filename"): g for g in data.get("games", []) if g.get("filename")}
            on_disk = {
                f for f in os.listdir(self.roms_dir)
                if not f.startswith(".") and f.lower().endswith((".zip", ".7z"))
                and os.path.isfile(os.path.join(self.roms_dir, f))
            }

            changed = False
            new_games = []
            for fname in sorted(on_disk):
                if fname in existing:
                    new_games.append(existing[fname])
                else:
                    full = os.path.join(self.roms_dir, fname)
                    h = hashlib.sha256()
                    with open(full, "rb") as rf:
                        while True:
                            chunk = rf.read(65536)
                            if not chunk:
                                break
                            h.update(chunk)
                    gid = os.path.splitext(fname)[0]
                    dname = ARCADE_DATABASE.get(gid, gid)
                    core = "snes9x" if "snes" in fname.lower() or "[!]" in fname else "fbneo"
                    new_games.append({
                        "game_id": gid,
                        "display_name": dname,
                        "filename": fname,
                        "core": core,
                        "sha256": h.hexdigest(),
                        "size": os.path.getsize(full),
                        "updated_at": time.time(),
                    })
                    changed = True

            if len(new_games) != len(existing):
                changed = True

            if changed:
                new_games.sort(key=lambda x: str(x.get("display_name", "")).lower())
                data["games"] = new_games
                self._save_manifest(data)

    def _load_or_init(self) -> Dict[str, Any]:
        if os.path.isfile(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.setdefault("games", [])
                data.setdefault("deleted", [])
                return data
            except Exception:
                pass
        data = {"games": [], "deleted": [], "updated_at": time.time()}
        self._save_manifest(data)
        return data

    def _save_manifest(self, data: Dict[str, Any]) -> None:
        data["updated_at"] = time.time()
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def get_manifest(self) -> Dict[str, Any]:
        with self._lock:
            return self._load_or_init()

    def list_games(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._load_or_init().get("games", []))

    def save_uploaded_rom(
        self,
        filename: str,
        stream: BinaryIO,
        content_len: int,
        display_name: str = "",
        core: str = "fbneo",
    ) -> Dict[str, Any]:
        safe_name = os.path.basename(filename).strip()
        if not safe_name or safe_name in (".", "..") or safe_name == "games_manifest.json":
            raise ValueError("Nama file tidak valid")

        tmp_path = os.path.join(self.roms_dir, f".tmp_{safe_name}")
        dest_path = os.path.join(self.roms_dir, safe_name)

        h = hashlib.sha256()
        remaining = content_len
        written = 0
        try:
            with open(tmp_path, "wb") as out:
                while remaining > 0:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    h.update(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
            os.replace(tmp_path, dest_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

        sha256 = h.hexdigest()
        game_id = os.path.splitext(safe_name)[0]
        final_name = display_name.strip() or game_id
        final_core = core.strip() or "fbneo"

        with self._lock:
            data = self._load_or_init()
            games = [g for g in data.get("games", []) if g.get("filename") != safe_name]
            deleted = [d for d in data.get("deleted", []) if d != safe_name]
            entry = {
                "game_id": game_id,
                "display_name": final_name,
                "filename": safe_name,
                "core": final_core,
                "sha256": sha256,
                "size": written,
                "updated_at": time.time(),
            }
            games.append(entry)
            games.sort(key=lambda x: str(x.get("display_name", "")).lower())
            data["games"] = games
            data["deleted"] = deleted
            self._save_manifest(data)
            return entry

    def update_game(
        self,
        filename: str,
        display_name: Optional[str] = None,
        core: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        safe_name = os.path.basename(filename).strip()
        with self._lock:
            data = self._load_or_init()
            for g in data.get("games", []):
                if g.get("filename") == safe_name:
                    if display_name is not None and display_name.strip():
                        g["display_name"] = display_name.strip()
                    if core is not None and core.strip():
                        g["core"] = core.strip()
                    g["updated_at"] = time.time()
                    self._save_manifest(data)
                    return g
        return None

    def delete_game(self, filename: str) -> bool:
        safe_name = os.path.basename(filename).strip()
        if not safe_name:
            return False
        with self._lock:
            data = self._load_or_init()
            before = len(data.get("games", []))
            data["games"] = [g for g in data.get("games", []) if g.get("filename") != safe_name]
            deleted = set(data.get("deleted", []))
            deleted.add(safe_name)
            data["deleted"] = sorted(deleted)
            self._save_manifest(data)

            full = os.path.join(self.roms_dir, safe_name)
            if os.path.isfile(full):
                try:
                    os.remove(full)
                except OSError:
                    pass
            return True

    def get_file_path(self, filename: str) -> Optional[str]:
        safe_name = os.path.basename(filename).strip()
        if not safe_name or safe_name == "games_manifest.json":
            return None
        full = os.path.join(self.roms_dir, safe_name)
        return full if os.path.isfile(full) else None

