"""Compatibility and Resource Validator for Arcade Online Launcher.

Verifies ROM existence and checksums, locates RetroArch binary and core
libraries across platforms (Batocera, EmuELEC, Linux, macOS), and enforces
strict compatibility checks before Netplay room entry.
"""

import os
import sys
import json
import zlib
import hashlib
import platform
import logging
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger("Arcade.Validator")


def calculate_file_hashes(file_path: str) -> Dict[str, str]:
    """Calculate SHA1, MD5, and CRC32 for a given file."""
    sha1 = hashlib.sha1()
    md5 = hashlib.md5()
    crc32_val = 0

    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha1.update(chunk)
            md5.update(chunk)
            crc32_val = zlib.crc32(chunk, crc32_val)

    return {
        "sha1": sha1.hexdigest(),
        "md5": md5.hexdigest(),
        "crc32": f"{crc32_val & 0xFFFFFFFF:08x}",
    }


def find_retroarch_binary(custom_path: Optional[str] = None) -> Optional[str]:
    """Find RetroArch executable path across supported operating systems."""
    # 1. Custom / Environment variable override
    env_bin = os.environ.get("ARCADE_RETROARCH_BIN") or custom_path
    if env_bin and os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
        return env_bin

    # 2. Mock mode for headless testing / CI
    if os.environ.get("ARCADE_MOCK_RETROARCH"):
        return env_bin or "/mock/bin/retroarch"

    # 3. Check standard PATH
    import shutil
    which_ra = shutil.which("retroarch")
    if which_ra:
        return which_ra

    # 4. Standard platform paths
    system = platform.system()
    candidates = []
    if system == "Linux":
        candidates = [
            "/usr/bin/retroarch",
            "/usr/local/bin/retroarch",
            "/opt/retroarch/bin/retroarch",
            "/userdata/system/bin/retroarch",  # Batocera custom
            os.path.expanduser("~/.var/app/org.libretro.RetroArch/data/retroarch"),
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/RetroArch.app/Contents/MacOS/RetroArch",
            os.path.expanduser("~/Applications/RetroArch.app/Contents/MacOS/RetroArch"),
            "/opt/homebrew/bin/retroarch",
            "/usr/local/bin/retroarch",
        ]
    elif system == "Windows":
        candidates = [
            r"C:\RetroArch-Win64\retroarch.exe",
            r"C:\Program Files\RetroArch\retroarch.exe",
        ]

    for candidate in candidates:
        if os.path.isfile(candidate) and (system == "Windows" or os.access(candidate, os.X_OK)):
            return candidate

    return None


def get_core_extensions() -> List[str]:
    """Return platform-specific dynamic library extensions for libretro cores."""
    system = platform.system()
    if system == "Darwin":
        return [".dylib", ".so"]
    if system == "Windows":
        return [".dll"]
    return [".so"]


def find_core_library(core_name: str, core_aliases: Optional[List[str]] = None,
                      custom_dirs: Optional[List[str]] = None) -> Optional[str]:
    """Search for the core library in common RetroArch paths."""
    # Mock mode
    if os.environ.get("ARCADE_MOCK_RETROARCH"):
        return f"/mock/cores/{core_name}_libretro.so"

    extensions = get_core_extensions()
    aliases = [core_name] + (core_aliases or [])

    search_dirs = []
    if custom_dirs:
        search_dirs.extend(custom_dirs)

    env_core_dir = os.environ.get("ARCADE_CORES_DIR")
    if env_core_dir:
        search_dirs.append(env_core_dir)

    system = platform.system()
    if system == "Linux":
        search_dirs.extend([
            "/usr/lib/libretro",
            "/usr/lib/x86_64-linux-gnu/libretro",
            "/usr/lib/aarch64-linux-gnu/libretro",
            "/userdata/system/cores",  # Batocera
            "/storage/cores",          # EmuELEC
            os.path.expanduser("~/.config/retroarch/cores"),
            os.path.expanduser("~/.var/app/org.libretro.RetroArch/config/retroarch/cores"),
        ])
    elif system == "Darwin":
        search_dirs.extend([
            os.path.expanduser("~/Library/Application Support/RetroArch/cores"),
            "/Applications/RetroArch.app/Contents/Resources/cores",
            "/opt/homebrew/lib/libretro",
        ])

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for alias in aliases:
            for ext in extensions:
                candidates = [
                    f"{alias}_libretro{ext}",
                    f"{alias}{ext}",
                    f"libretro_{alias}{ext}",
                ]
                for filename in candidates:
                    full_path = os.path.join(directory, filename)
                    if os.path.isfile(full_path):
                        return full_path

    return None


class GameManifest:
    """Manages the catalog of supported arcade games and compatibility parameters."""

    def __init__(self, manifest_path: Optional[str] = None, auto_scan: bool = True):
        if not manifest_path:
            manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
        self.manifest_path = manifest_path
        self.data: Dict[str, Any] = {}
        self.games: Dict[str, Dict[str, Any]] = {}
        self.load()
        if auto_scan and not os.environ.get("ARCADE_DISABLE_AUTOSCAN"):
            self.scan_and_merge()

    def load(self) -> None:
        if not os.path.exists(self.manifest_path):
            raise FileNotFoundError(f"Manifest file not found: {self.manifest_path}")
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.games = {g["game_id"]: g for g in self.data.get("games", [])}

    def scan_and_merge(self, scanner: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Dynamically scan disk for installed cores and ROMs, merging them into catalog."""
        try:
            from .scanner import SystemScanner
            s = scanner or SystemScanner()
            discovered = s.auto_scan()
            for gid, scanned in discovered.items():
                if gid not in self.games:
                    self.games[gid] = scanned.to_dict()
                else:
                    self.games[gid]["scanned_rom_path"] = scanned.rom_path
                    self.games[gid]["scanned_core_path"] = scanned.core_path
                    self.games[gid]["status"] = scanned.status
        except Exception:
            pass
        return list(self.games.values())

    def get_game(self, game_id: str) -> Optional[Dict[str, Any]]:
        return self.games.get(game_id)

    def list_games(self, only_ready: bool = False) -> List[Dict[str, Any]]:
        if only_ready:
            return [g for g in self.games.values() if g.get("status") == "ready"]
        return list(self.games.values())


class CatalogValidator:
    """Validates local environment, ROM assets, and peer compatibility."""

    def __init__(self, manifest: Optional[GameManifest] = None,
                 rom_dirs: Optional[List[str]] = None,
                 core_dirs: Optional[List[str]] = None,
                 retroarch_bin: Optional[str] = None):
        self.manifest = manifest or GameManifest()
        self.rom_dirs = rom_dirs or self._default_rom_dirs()
        self.core_dirs = core_dirs or []
        self.retroarch_bin = retroarch_bin

    def _default_rom_dirs(self) -> List[str]:
        dirs = []
        env_rom_dir = os.environ.get("ARCADE_ROMS_DIR")
        if env_rom_dir:
            dirs.append(env_rom_dir)
        system = platform.system()
        if system == "Linux":
            dirs.extend([
                "/userdata/roms/mame",
                "/userdata/roms/fbneo",
                "/userdata/roms/arcade",
                "/storage/roms/mame",
                os.path.expanduser("~/roms/mame"),
                os.path.expanduser("~/roms/arcade"),
            ])
        elif system == "Darwin":
            dirs.extend([
                os.path.expanduser("~/RetroArch/roms"),
                os.path.expanduser("~/Downloads/roms"),
            ])
        return dirs

    def find_rom_file(self, game: Dict[str, Any]) -> Optional[str]:
        """Search configured ROM directories for the game ROM file."""
        # 0. If already scanned and found dynamically
        scanned_path = game.get("scanned_rom_path")
        if scanned_path and (os.path.isfile(scanned_path) or scanned_path.startswith("/mock/")):
            return scanned_path

        # 1. Direct path override in env
        env_rom = os.environ.get(f"ARCADE_ROM_{game['game_id'].upper().replace('-', '_')}")
        if env_rom and os.path.isfile(env_rom):
            return env_rom

        rom_filename = game.get("rom_file")
        if not rom_filename:
            return None

        for directory in self.rom_dirs:
            candidate = os.path.join(directory, rom_filename)
            if os.path.isfile(candidate):
                return candidate

        # Fallback to mock path if in mock environment and not found locally
        if os.environ.get("ARCADE_MOCK_RETROARCH"):
            return f"/mock/roms/{rom_filename}"

        return None

    def verify_local_game(self, game_id: str, strict_hash: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        """Verify that game, ROM, core, and RetroArch binary exist and match requirements.

        Returns (is_valid, error_code_or_message, details_dict).
        """
        game = self.manifest.get_game(game_id)
        if not game:
            return False, "GAME_NOT_FOUND", {"message": f"Game '{game_id}' is not in catalog"}

        # 1. RetroArch binary check
        ra_bin = find_retroarch_binary(self.retroarch_bin)
        if not ra_bin:
            return False, "RETROARCH_NOT_FOUND", {
                "message": "RetroArch executable not found. Ensure RetroArch is installed."
            }

        # 2. Core library check
        scanned_core = game.get("scanned_core_path")
        if scanned_core and (os.path.isfile(scanned_core) or scanned_core.startswith("/mock/")):
            core_lib = scanned_core
        else:
            core_lib = find_core_library(
                game["retroarch_core"],
                game.get("core_aliases"),
                self.core_dirs
            )
        if not core_lib:
            return False, "CORE_MISMATCH", {
                "message": f"Required core '{game['retroarch_core']}' not found in system.",
                "core": game["retroarch_core"],
                "version": game.get("core_version")
            }

        # 3. ROM presence and hash check
        rom_path = self.find_rom_file(game)
        if not rom_path:
            return False, "ROM_NOT_FOUND", {
                "message": f"ROM file '{game['rom_file']}' not found in searched directories.",
                "searched_dirs": self.rom_dirs
            }

        if rom_path.startswith("/mock/"):
            hashes = {"sha1": "mock_hash_12345", "md5": "mock_hash_12345", "crc32": "00000000"}
        else:
            hashes = calculate_file_hashes(rom_path)
        expected_hashes = game.get("rom_hashes", {})

        if strict_hash and expected_hashes:
            matched = False
            for algo, expected_val in expected_hashes.items():
                if hashes.get(algo, "").lower() == expected_val.lower():
                    matched = True
                    break
            if not matched:
                return False, "GAME_MISMATCH", {
                    "message": "ROM checksum mismatch with manifest specification.",
                    "rom_path": rom_path,
                    "expected": expected_hashes,
                    "actual": hashes
                }

        details = {
            "game_id": game_id,
            "display_name": game.get("display_name"),
            "retroarch_bin": ra_bin,
            "core_lib": core_lib,
            "core_version": game.get("core_version"),
            "rom_path": rom_path,
            "rom_hashes": hashes,
        }
        logger.info(f"Validasi lokal game '{game_id}': LULUS (Binary: {ra_bin}, Core: {os.path.basename(core_lib)}, ROM: {os.path.basename(rom_path)})")
        return True, "OK", details

    def check_peer_compatibility(self, game_id: str, peer_compat: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if incoming peer compatibility metadata matches requirements."""
        game = self.manifest.get_game(game_id)
        if not game:
            return False, "GAME_MISMATCH"

        peer_core = peer_compat.get("core")
        allowed_cores = [game["retroarch_core"]] + game.get("core_aliases", [])
        if peer_core not in allowed_cores:
            return False, "CORE_MISMATCH"

        peer_core_ver = peer_compat.get("core_version")
        expected_ver = game.get("core_version")
        if expected_ver and peer_core_ver and peer_core_ver != expected_ver:
            return False, "CORE_MISMATCH"

        # Check ROM hash if supplied
        peer_hash = peer_compat.get("rom_hash")
        expected_hashes = game.get("rom_hashes", {})
        if peer_hash and expected_hashes:
            # Check against any known hash
            if not any(peer_hash.lower() == val.lower() for val in expected_hashes.values()):
                return False, "GAME_MISMATCH"

        return True, "OK"
