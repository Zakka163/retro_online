"""System Diagnostic and Machine Identification Helper.

Provides detailed hardware, OS, network, emulator, and core inspection
for enhanced diagnostic logging across macOS, EmuELEC, Batocera, and Linux.
"""

import os
import sys
import glob
import json
import zlib
import socket
import hashlib
import platform
import subprocess
from typing import Dict, Any, Optional, Tuple, List


LAUNCHER_VERSION = "1.2.0"


def get_machine_hardware() -> str:
    """Detect underlying device or CPU model across platforms."""
    # 1. Linux / EmuELEC / Batocera device-tree model (TV boxes, SBCs)
    for model_path in ("/proc/device-tree/model", "/sys/firmware/devicetree/base/model"):
        if os.path.isfile(model_path):
            try:
                with open(model_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().replace("\x00", "").strip()
                    if content:
                        return content
            except Exception:
                pass

    # 2. Linux /proc/cpuinfo
    if sys.platform.startswith("linux") and os.path.isfile("/proc/cpuinfo"):
        try:
            hardware = None
            cpu_model = None
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        key = parts[0].strip().lower()
                        val = parts[1].strip()
                        if key in ("hardware", "model name", "cpu model name"):
                            if not cpu_model:
                                cpu_model = val
                        if key == "hardware":
                            hardware = val
            if cpu_model or hardware:
                return hardware or cpu_model or "Generic Linux SBC"
        except Exception:
            pass

    # 3. macOS sysctl CPU brand
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                stderr=subprocess.DEVNULL,
                timeout=1.0,
                text=True
            ).strip()
            if out:
                return out
        except Exception:
            pass

    return platform.processor() or platform.machine() or "Unknown Architecture"


def get_os_distro() -> str:
    """Detect OS distribution name and version (e.g., EmuELEC 4.6, Batocera, macOS 15.1)."""
    # 1. Check for EmuELEC specific version files
    for ee_path in ("/storage/.config/version", "/etc/emuelec_version"):
        if os.path.isfile(ee_path):
            try:
                with open(ee_path, "r", encoding="utf-8", errors="ignore") as f:
                    ver = f.read().strip()
                    if ver:
                        return f"EmuELEC {ver}"
            except Exception:
                pass

    # 2. Standard Linux /etc/os-release
    if os.path.isfile("/etc/os-release"):
        try:
            data = {}
            with open("/etc/os-release", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        data[k.strip()] = v.strip().strip('"').strip("'")
            name = data.get("PRETTY_NAME") or data.get("NAME") or "Linux"
            version = data.get("VERSION_ID") or data.get("VERSION") or ""
            return f"{name} {version}".strip()
        except Exception:
            pass

    # 3. macOS version
    if sys.platform == "darwin":
        try:
            mac_ver = platform.mac_ver()[0]
            if mac_ver:
                return f"macOS {mac_ver}"
        except Exception:
            pass

    return f"{platform.system()} {platform.release()}"


def get_retroarch_version_string(ra_bin: Optional[str]) -> str:
    """Query RetroArch binary for its release and Git hash."""
    if not ra_bin:
        return "Tidak terpasang"
    try:
        import shutil
        if not (os.path.isfile(ra_bin) or shutil.which(ra_bin)):
            return "Binary tidak ditemukan"

        proc = subprocess.run(
            [ra_bin, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0
        )
        lines = (proc.stdout or "").splitlines()
        if not lines and proc.stderr:
            lines = proc.stderr.splitlines()

        ver_str = None
        git_hash = None
        for line in lines:
            line_str = line.strip()
            # Linux format: "RetroArch 1.21.0 (Git bfa603828d)"
            if line_str.startswith("RetroArch ") and any(c.isdigit() for c in line_str):
                return line_str
            # macOS format: "Version: 1.22.2 Oct  9 2026"
            if line_str.lower().startswith("version:"):
                ver_str = line_str.split(":", 1)[1].strip()
            if "git" in line_str.lower() and not git_hash:
                git_hash = line_str

        if ver_str:
            return f"RetroArch v{ver_str}"
        return lines[0].strip() if lines else "Versi terpasang"
    except Exception as e:
        return f"Gagal mengecek versi ({e})"


def parse_core_info_file(info_path: str) -> Dict[str, str]:
    """Parse Libretro .info file (supports both key = 'value' and JSON)."""
    meta: Dict[str, str] = {}
    try:
        with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        if content.startswith("{"):
            try:
                js = json.loads(content)
                if isinstance(js, dict):
                    return {str(k): str(v) for k, v in js.items()}
            except Exception:
                pass

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return meta


def get_core_binary_version(core_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Query retro_get_system_info directly from the Libretro core binary (.dll/.dylib/.so)."""
    if not core_path or not os.path.isfile(core_path):
        return None, None

    # 1. Try ctypes retro_get_system_info
    try:
        import ctypes

        class RetroSystemInfo(ctypes.Structure):
            _fields_ = [
                ("library_name", ctypes.c_char_p),
                ("library_version", ctypes.c_char_p),
                ("valid_extensions", ctypes.c_char_p),
                ("need_fullpath", ctypes.c_bool),
                ("block_extract", ctypes.c_bool),
            ]

        lib = ctypes.CDLL(core_path)
        if hasattr(lib, "retro_get_system_info"):
            info = RetroSystemInfo()
            lib.retro_get_system_info(ctypes.byref(info))
            lib_name = info.library_name.decode("utf-8", errors="ignore").strip() if info.library_name else None
            lib_ver = info.library_version.decode("utf-8", errors="ignore").strip() if info.library_version else None
            if lib_name or lib_ver:
                return lib_name, lib_ver
    except Exception:
        pass

    # 2. Fallback: scan binary strings for FBNeo version pattern (e.g., "v1.0.0.03 c4c8b12")
    try:
        import re
        with open(core_path, "rb") as f:
            data = f.read()
        match = re.search(rb"(v\d+\.\d+\.\d+\.\d+(?:\s+[0-9a-fA-F]{7,10})?)", data)
        if match:
            return None, match.group(1).decode("ascii", errors="ignore")
    except Exception:
        pass

    return None, None


def get_core_info(core_path: Optional[str]) -> Dict[str, Any]:
    """Inspect core library file, extract metadata from binary & .info, and compute sha256."""
    if not core_path:
        return {"exists": False, "name": "Core belum disetel", "version": "unknown"}

    core_filename = os.path.basename(core_path)
    core_stem = os.path.splitext(core_filename)[0]

    result: Dict[str, Any] = {
        "exists": False,
        "path": core_path,
        "filename": core_filename,
        "name": core_stem,
        "version": "tidak diketahui",
        "size_bytes": 0,
        "size_str": "0 B",
        "sha256": "tidak tersedia",
        "sha256_short": "tidak tersedia"
    }

    if not os.path.isfile(core_path):
        return result

    result["exists"] = True
    try:
        sz = os.path.getsize(core_path)
        result["size_bytes"] = sz
        if sz >= 1024 * 1024:
            result["size_str"] = f"{sz / (1024 * 1024):.1f} MB"
        else:
            result["size_str"] = f"{sz / 1024:.1f} KB"
    except Exception:
        pass

    try:
        h = hashlib.sha256()
        with open(core_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        digest = h.hexdigest()
        result["sha256"] = digest
        result["sha256_short"] = digest[:12]
    except Exception:
        pass

    # Find matching .info file
    core_dir = os.path.dirname(core_path)
    info_candidates = [
        os.path.join(core_dir, core_stem + ".info"),
        os.path.join(core_dir, "..", "info", core_stem + ".info"),
        os.path.expanduser(f"~/Library/Application Support/RetroArch/info/{core_stem}.info"),
        os.path.expanduser(f"~/.config/retroarch/info/{core_stem}.info"),
        f"/storage/.config/retroarch/cores/info/{core_stem}.info",
        f"/storage/.config/retroarch/cores/{core_stem}.info",
        f"/tmp/cores/{core_stem}.info",
        f"/usr/lib/libretro/{core_stem}.info",
    ]

    for candidate in info_candidates:
        if os.path.isfile(candidate):
            meta = parse_core_info_file(candidate)
            if meta:
                display_name = meta.get("display_name") or meta.get("corename")
                version = meta.get("display_version") or meta.get("library_version")
                if display_name:
                    result["name"] = display_name
                if version:
                    result["version"] = version
                result["info_file"] = candidate
                break

    # Query actual compiled-in version directly from the core binary (.dll/.dylib/.so)
    bin_name, bin_ver = get_core_binary_version(core_path)
    if bin_name and result["name"] == core_stem:
        result["name"] = bin_name
    if bin_ver:
        result["version"] = bin_ver

    return result


def get_rom_file_info(rom_path: str) -> Dict[str, Any]:
    """Inspect ROM file, compute size and CRC32."""
    info: Dict[str, Any] = {
        "exists": False,
        "path": rom_path,
        "filename": os.path.basename(rom_path),
        "size_str": "0 B",
        "crc32": "unknown",
        "sha1": "unknown"
    }
    if not os.path.isfile(rom_path):
        return info

    info["exists"] = True
    try:
        sz = os.path.getsize(rom_path)
        if sz >= 1024 * 1024:
            info["size_str"] = f"{sz / (1024 * 1024):.2f} MB"
        else:
            info["size_str"] = f"{sz / 1024:.1f} KB"
    except Exception:
        pass

    try:
        sha1 = hashlib.sha1()
        crc = 0
        with open(rom_path, "rb") as f:
            while chunk := f.read(65536):
                sha1.update(chunk)
                crc = zlib.crc32(chunk, crc)
        info["crc32"] = f"{crc & 0xFFFFFFFF:08x}"
        info["sha1"] = sha1.hexdigest()
    except Exception:
        pass

    return info
