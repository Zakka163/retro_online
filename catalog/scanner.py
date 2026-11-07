"""Dynamic Game & Core Auto-Scanner for Arcade Online Launcher.

Automatically discovers:
1. All installed libretro cores on the system (MAME, FBNeo, FBA, etc.)
2. All arcade ROMs across local storage, Batocera partitions, USB mount points
3. Auto-identifies arcade titles from ROM filenames and calculates checksums
4. Dynamically generates playable game catalog so users never have to configure paths manually.
"""

import os
import sys
import json
import glob
import time
import platform
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple

from .validator import calculate_file_hashes, get_core_extensions, find_retroarch_binary

logger = logging.getLogger("Arcade.Scanner")

# Built-in database of popular arcade ROM identifiers -> Friendly Titles
ARCADE_DATABASE = {
    # Capcom / Street Fighter
    "sf2": "Street Fighter II: The World Warrior",
    "sf2ce": "Street Fighter II': Champion Edition",
    "sf2hf": "Street Fighter II' Turbo: Hyper Fighting",
    "ssf2": "Super Street Fighter II: The New Challengers",
    "ssf2t": "Super Street Fighter II Turbo",
    "sfa": "Street Fighter Alpha: Warriors' Dreams",
    "sfa2": "Street Fighter Alpha 2",
    "sfa3": "Street Fighter Alpha 3",
    "sfiii": "Street Fighter III: New Generation",
    "sfiii2": "Street Fighter III 2nd Impact: Giant Attack",
    "sfiii3": "Street Fighter III 3rd Strike: Fight for the Future",
    # SNK / Neo Geo
    "mslug": "Metal Slug: Super Vehicle-001",
    "mslug2": "Metal Slug 2: Super Vehicle-001/II",
    "mslugx": "Metal Slug X: Super Vehicle-001",
    "mslug3": "Metal Slug 3",
    "mslug4": "Metal Slug 4",
    "mslug5": "Metal Slug 5",
    "kof94": "The King of Fighters '94",
    "kof95": "The King of Fighters '95",
    "kof96": "The King of Fighters '96",
    "kof97": "The King of Fighters '97",
    "kof98": "The King of Fighters '98: The Slugfest",
    "kof99": "The King of Fighters '99: Millennium Battle",
    "kof2000": "The King of Fighters 2000",
    "kof2001": "The King of Fighters 2001",
    "kof2002": "The King of Fighters 2002: Challenge to Ultimate Battle",
    "garou": "Garou: Mark of the Wolves",
    "samsho": "Samurai Shodown",
    "samsho2": "Samurai Shodown II",
    "samsho4": "Samurai Shodown IV: Amakusa's Revenge",
    "fatfury": "Fatal Fury: King of Fighters",
    "fatfury2": "Fatal Fury 2",
    "rbff1": "Real Bout Fatal Fury",
    "rbffspec": "Real Bout Fatal Fury Special",
    # Classic Arcade Beat-em-ups & Action
    "captcomm": "Captain Commando",
    "punisher": "The Punisher",
    "dino": "Cadillacs and Dinosaurs",
    "ffight": "Final Fight",
    "tmnt": "Teenage Mutant Ninja Turtles",
    "tmnt2": "Teenage Mutant Ninja Turtles: Turtles in Time",
    "simpsons": "The Simpsons Arcade Game",
    "xmen": "X-Men (4/6 Player Arcade)",
    "ddragon": "Double Dragon",
    "ddragon2": "Double Dragon II: The Revenge",
    "goldnaxe": "Golden Axe",
    "sunsetbl": "Sunset Riders",
    "avsp": "Alien vs. Predator",
    # Marvel / Capcom Fighters
    "xmcota": "X-Men: Children of the Atom",
    "msh": "Marvel Super Heroes",
    "xmvsf": "X-Men vs. Street Fighter",
    "mshvsf": "Marvel Super Heroes vs. Street Fighter",
    "mvsc": "Marvel vs. Capcom: Clash of Super Heroes",
    # Midway / Namco / Classics
    "mk": "Mortal Kombat",
    "mk2": "Mortal Kombat II",
    "umk3": "Ultimate Mortal Kombat 3",
    "tekken": "Tekken",
    "tekken2": "Tekken 2",
    "tekken3": "Tekken 3",
    "pacman": "Pac-Man",
    "galaga": "Galaga",
    "1942": "1942",
    "1944": "1944: The Loop Master",
}

# Preferred arcade cores in order of netplay reliability
PREFERRED_ARCADE_CORES = [
    "fbneo",
    "mame2003_plus",
    "mame2003",
    "fbalpha",
    "mame",
    "mame2010",
]


@dataclass
class ScannedGame:
    """Represents a dynamically discovered arcade game on the local machine."""
    game_id: str
    display_name: str
    rom_file: str
    rom_path: str
    core_name: str
    core_path: str
    core_version: str = "auto"
    rom_hashes: Dict[str, str] = field(default_factory=dict)
    players: int = 2
    netplay_enabled: bool = True
    default_port: int = 55435
    status: str = "ready"  # 'ready', 'missing_core', 'missing_rom'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "display_name": self.display_name,
            "rom_file": self.rom_file,
            "rom_path": self.rom_path,
            "retroarch_core": self.core_name,
            "core_path": self.core_path,
            "core_version": self.core_version,
            "rom_hashes": self.rom_hashes,
            "players": self.players,
            "netplay_enabled": self.netplay_enabled,
            "default_port": self.default_port,
            "status": self.status,
        }


class SystemScanner:
    """Scans operating system, disks, cores, and ROMs dynamically."""

    def __init__(self, custom_rom_dirs: Optional[List[str]] = None,
                 custom_core_dirs: Optional[List[str]] = None,
                 cache_file: Optional[str] = None):
        self.custom_rom_dirs = custom_rom_dirs or []
        self.custom_core_dirs = custom_core_dirs or []
        self.cache_file = cache_file or os.path.expanduser("~/.arcade_online_cache.json")
        self.installed_cores: Dict[str, str] = {}  # core_name -> path
        self.discovered_games: Dict[str, ScannedGame] = {}

    def get_system_core_directories(self) -> List[str]:
        """Detect all standard RetroArch core paths across operating systems."""
        dirs = []
        if self.custom_core_dirs:
            dirs.extend(self.custom_core_dirs)

        env_dir = os.environ.get("ARCADE_CORES_DIR")
        if env_dir:
            dirs.append(env_dir)

        system = platform.system()
        if system == "Linux":
            dirs.extend([
                "/usr/lib/libretro",
                "/usr/lib/x86_64-linux-gnu/libretro",
                "/usr/lib/aarch64-linux-gnu/libretro",
                "/usr/lib/arm-linux-gnueabihf/libretro",
                "/userdata/system/cores",                       # Batocera
                "/storage/cores",                               # EmuELEC
                "/opt/retropie/libretrocores",                  # RetroPie
                os.path.expanduser("~/.config/retroarch/cores"),
                os.path.expanduser("~/.var/app/org.libretro.RetroArch/config/retroarch/cores"),
            ])
        elif system == "Darwin":
            dirs.extend([
                os.path.expanduser("~/Library/Application Support/RetroArch/cores"),
                "/Applications/RetroArch.app/Contents/Resources/cores",
                "/opt/homebrew/lib/libretro",
                "/usr/local/lib/libretro",
            ])
        elif system == "Windows":
            appdata = os.environ.get("APPDATA", "")
            localappdata = os.environ.get("LOCALAPPDATA", "")
            prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
            prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            dirs.extend([
                os.path.join(appdata, "RetroArch", "cores"),
                os.path.join(localappdata, "RetroArch", "cores"),
                r"C:\RetroArch-Win64\cores",
                r"C:\RetroArch\cores",
                os.path.join(prog_files, "RetroArch", "cores"),
                os.path.join(prog_files_x86, "RetroArch", "cores"),
                os.path.join(prog_files_x86, "Steam", "steamapps", "common", "RetroArch", "cores"),
                os.path.join(prog_files, "Steam", "steamapps", "common", "RetroArch", "cores"),
                r"D:\RetroArch-Win64\cores",
                r"D:\RetroArch\cores",
            ])

        return [d for d in dirs if os.path.isdir(d)]

    def scan_installed_cores(self) -> Dict[str, str]:
        """Scan system directories and return map of core_name -> full library path."""
        # Mock mode
        if os.environ.get("ARCADE_MOCK_RETROARCH"):
            mock_cores = {
                "mame2003_plus": "/mock/cores/mame2003_plus_libretro.so",
                "fbneo": "/mock/cores/fbneo_libretro.so",
                "mame": "/mock/cores/mame_libretro.so",
            }
            self.installed_cores = mock_cores
            return mock_cores

        found_cores: Dict[str, str] = {}
        core_extensions = get_core_extensions()
        search_dirs = self.get_system_core_directories()

        for directory in search_dirs:
            try:
                for entry in os.listdir(directory):
                    ext = os.path.splitext(entry)[1].lower()
                    if ext not in core_extensions:
                        continue

                    stem = os.path.splitext(entry)[0]
                    # Clean up libretro naming variants: e.g. "mame2003_plus_libretro" -> "mame2003_plus"
                    clean_name = stem
                    if clean_name.startswith("libretro_"):
                        clean_name = clean_name[len("libretro_"):]
                    if clean_name.endswith("_libretro"):
                        clean_name = clean_name[:-len("_libretro")]

                    full_path = os.path.join(directory, entry)
                    if os.path.isfile(full_path):
                        found_cores[clean_name.lower()] = full_path
                        # Also register standard aliases
                        if "fbneo" in clean_name.lower():
                            found_cores["fbneo"] = full_path
                        elif "2003_plus" in clean_name.lower() or "2003-plus" in clean_name.lower():
                            found_cores["mame2003_plus"] = full_path
                        elif "2003" in clean_name.lower() and "plus" not in clean_name.lower():
                            found_cores["mame2003"] = full_path
            except Exception as e:
                logger.debug(f"Error scanning core directory {directory}: {e}")

        self.installed_cores = found_cores
        return found_cores

    def get_system_rom_directories(self) -> List[str]:
        """Auto-detect all possible arcade ROM paths on internal and external drives."""
        dirs = []
        if self.custom_rom_dirs:
            dirs.extend(self.custom_rom_dirs)

        env_roms = os.environ.get("ARCADE_ROMS_DIR")
        if env_roms:
            dirs.append(env_roms)

        system = platform.system()
        if system == "Linux":
            dirs.extend([
                "/userdata/roms/mame",
                "/userdata/roms/fbneo",
                "/userdata/roms/arcade",
                "/userdata/roms/neogeo",
                "/storage/roms/mame",                           # EmuELEC
                "/storage/roms/fbneo",
                "/storage/roms/arcade",
                "/home/pi/RetroPie/roms/arcade",               # RetroPie
                "/home/pi/RetroPie/roms/mame-libretro",
                "/home/pi/RetroPie/roms/fba",
                os.path.expanduser("~/roms/mame"),
                os.path.expanduser("~/roms/arcade"),
                os.path.expanduser("~/roms/fbneo"),
            ])
            # Auto-detect external USB sticks on Linux / Batocera
            for usb_mount in glob.glob("/media/*/*") + glob.glob("/run/media/*/*"):
                if os.path.isdir(usb_mount):
                    for sub in ["roms/mame", "roms/arcade", "roms/fbneo", "mame", "arcade"]:
                        p = os.path.join(usb_mount, sub)
                        if os.path.isdir(p):
                            dirs.append(p)

        elif system == "Darwin":
            dirs.extend([
                os.path.expanduser("~/RetroArch/roms"),
                os.path.expanduser("~/roms/mame"),
                os.path.expanduser("~/roms/arcade"),
                os.path.expanduser("~/Downloads/roms"),
            ])
            # macOS external volumes
            for vol in glob.glob("/Volumes/*"):
                if os.path.isdir(vol):
                    for sub in ["roms/mame", "roms/arcade", "roms/fbneo", "mame", "arcade"]:
                        p = os.path.join(vol, sub)
                        if os.path.isdir(p):
                            dirs.append(p)

        elif system == "Windows":
            user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
            dirs.extend([
                os.path.join(user_profile, "Downloads", "roms"),
                os.path.join(user_profile, "roms"),
                os.path.join(user_profile, "RetroArch", "roms"),
                r"C:\roms",
                r"C:\RetroArch-Win64\roms",
                r"C:\RetroArch\roms",
                r"C:\Program Files\RetroArch\roms",
                r"D:\roms",
                r"D:\RetroArch-Win64\roms",
                r"E:\roms",
            ])
            for drive in ["C:", "D:", "E:", "F:"]:
                for sub in [r"\roms\mame", r"\roms\arcade", r"\roms\fbneo", r"\roms\snes", r"\Downloads\roms"]:
                    p = drive + sub
                    if os.path.isdir(p):
                        dirs.append(p)

        # Remove duplicates while preserving order
        unique_dirs = []
        for d in dirs:
            norm = os.path.abspath(d)
            if norm not in unique_dirs and os.path.isdir(norm):
                unique_dirs.append(norm)

        return unique_dirs

    def _detect_rom_system(self, full_path: str, filename: str) -> str:
        """Detect whether a ROM is Arcade, SNES, Genesis, NES, etc."""
        fname_lower = filename.lower()
        if fname_lower.endswith((".sfc", ".smc", ".fig")):
            return "snes"
        if fname_lower.endswith((".nes", ".fds")):
            return "nes"
        if fname_lower.endswith((".md", ".gen", ".smd")):
            return "genesis"

        # Check inside zip if accessible
        import zipfile
        if fname_lower.endswith((".zip", ".7z")):
            try:
                if zipfile.is_zipfile(full_path):
                    with zipfile.ZipFile(full_path, "r") as z:
                        names = [n.lower() for n in z.namelist()]
                        if any(n.endswith((".sfc", ".smc", ".fig")) for n in names):
                            return "snes"
                        if any(n.endswith((".nes", ".fds")) for n in names):
                            return "nes"
                        if any(n.endswith((".md", ".gen", ".smd")) for n in names):
                            return "genesis"
            except Exception:
                pass

        # Console GoodTools / No-Intro naming markers: e.g. "(V1.0) (E) [!]"
        console_markers = ["(v1.", "(e)", "(usa)", "(u)", "(j)", "(japan)", "(europe)", "[!]"]
        if any(m in fname_lower for m in console_markers):
            return "snes"

        return "arcade"

    def _select_best_core_for_rom(self, rom_basename: str, system_type: str = "arcade") -> Tuple[str, str]:
        """Pick the best available installed core for this ROM."""
        if system_type == "snes":
            snes_cores = ["snes9x", "snes9x2010", "snes9x2005", "bsnes", "snes9x_next"]
            for pref in snes_cores:
                if pref in self.installed_cores:
                    return pref, self.installed_cores[pref]
            return "snes9x", ""

        if system_type == "genesis":
            gen_cores = ["genesis_plus_gx", "picodrive"]
            for pref in gen_cores:
                if pref in self.installed_cores:
                    return pref, self.installed_cores[pref]
            return "genesis_plus_gx", ""

        if system_type == "nes":
            nes_cores = ["fceumm", "nestopia", "mesen"]
            for pref in nes_cores:
                if pref in self.installed_cores:
                    return pref, self.installed_cores[pref]
            return "fceumm", ""

        # Arcade cores in order
        for pref in PREFERRED_ARCADE_CORES:
            if pref in self.installed_cores:
                return pref, self.installed_cores[pref]

        for name, path in self.installed_cores.items():
            if any(k in name for k in ("mame", "fb", "arcade", "neo")):
                return name, path

        return "mame2003_plus", ""

    def scan_roms(self, max_depth: int = 2) -> Dict[str, ScannedGame]:
        """Scan directories for arcade ROM files (.zip, .7z) and identify them dynamically."""
        # Ensure cores are scanned first
        if not self.installed_cores:
            self.scan_installed_cores()

        found_games: Dict[str, ScannedGame] = {}
        rom_dirs = self.get_system_rom_directories()
        rom_extensions = {".zip", ".7z"}

        for rom_dir in rom_dirs:
            try:
                for root, _, files in os.walk(rom_dir):
                    depth = root[len(rom_dir):].count(os.sep)
                    if depth > max_depth:
                        continue

                    for file in files:
                        ext = os.path.splitext(file)[1].lower()
                        if ext not in rom_extensions:
                            continue

                        stem = os.path.splitext(file)[0].lower()
                        full_path = os.path.join(root, file)

                        # Detect platform / system (Arcade, SNES, Genesis, etc.)
                        sys_type = self._detect_rom_system(full_path, file)

                        # Determine friendly title and game_id from filename
                        display_name = ARCADE_DATABASE.get(stem)
                        if display_name:
                            game_id = stem
                        else:
                            # Auto-name cleanly
                            game_id = stem
                            tag = "Arcade" if sys_type == "arcade" else sys_type.upper()
                            display_name = f"{stem.upper()} ({tag})"

                        # Avoid overwriting already scanned higher-priority ROM path
                        if game_id in found_games:
                            continue

                        # Pick matching core
                        core_name, core_path = self._select_best_core_for_rom(stem, sys_type)
                        status = "ready" if core_path else "missing_core"

                        # Create ScannedGame entry dynamically
                        game = ScannedGame(
                            game_id=game_id,
                            display_name=display_name,
                            rom_file=file,
                            rom_path=full_path,
                            core_name=core_name,
                            core_path=core_path,
                            status=status
                        )
                        found_games[game_id] = game
            except Exception as e:
                logger.debug(f"Error scanning ROM directory {rom_dir}: {e}")

        # Fallback only when in explicit headless mock test environment with no ROMs
        if not found_games and os.environ.get("ARCADE_FORCE_MOCK_GAME"):
            mock_game = ScannedGame(
                game_id="sf2",
                display_name=ARCADE_DATABASE.get("sf2", "Street Fighter II"),
                rom_file="sf2.zip",
                rom_path="/mock/roms/sf2.zip",
                core_name="mame2003_plus",
                core_path="/mock/cores/mame2003_plus_libretro.so",
                rom_hashes={"sha1": "mock_hash_12345", "md5": "mock_hash_12345", "crc32": "00000000"},
                status="ready"
            )
            found_games["sf2"] = mock_game

        self.discovered_games = found_games
        return found_games

    def auto_scan(self) -> Dict[str, ScannedGame]:
        """Perform full dynamic system scan of cores and ROMs."""
        self.scan_installed_cores()
        return self.scan_roms()

    def get_ready_games(self) -> List[ScannedGame]:
        """Return only games that have both ROM and matching core ready."""
        if not self.discovered_games:
            self.auto_scan()
        return [g for g in self.discovered_games.values() if g.status == "ready"]

