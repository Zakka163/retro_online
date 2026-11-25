"""HTTP Auto-Updater for Arcade Online Launcher.

Checks the VPS server (/api/version) for newer releases, downloads the
tar.gz bundle (/api/update/bundle), verifies its SHA-256 checksum, and
extracts updated files without overwriting local config.json or logs.
"""

import hashlib
import json
import logging
import os
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("Arcade.Updater")

PROTECTED_BASENAMES = {"config.json", "arcade_launcher.log"}


def parse_version(ver: str) -> Tuple[int, ...]:
    """Convert semantic version string like '1.2.1' into a comparable tuple."""
    parts = []
    for chunk in str(ver).strip().lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def get_effective_version(launcher_version: str, target_dir: str) -> str:
    """Return the higher of launcher_version and .applied_release.json."""
    state_file = os.path.join(os.path.abspath(target_dir), ".applied_release.json")
    if os.path.isfile(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                applied = str(json.load(f).get("version", "")).strip()
            if applied and parse_version(applied) > parse_version(launcher_version):
                return applied
        except Exception:
            pass
    return launcher_version


def _save_applied_version(target_dir: str, version: str) -> None:
    state_file = os.path.join(os.path.abspath(target_dir), ".applied_release.json")
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"version": version}, f)
    except Exception:
        pass


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def check_for_update(
    server_url: str,
    current_version: str,
    timeout: float = 4.0,
) -> Optional[Dict[str, Any]]:
    """Query server /api/version; return manifest dict if a newer version exists."""
    url = f"{server_url.rstrip('/')}/api/version"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            manifest = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"[Updater] Lewati cek update ({url}): {e}")
        return None

    if not manifest.get("update_available"):
        return None

    remote_ver = str(manifest.get("version", "")).strip()
    if not remote_ver:
        return None

    if parse_version(remote_ver) > parse_version(current_version):
        logger.info(f"[Updater] Versi baru tersedia: v{remote_ver} (saat ini: v{current_version})")
        return manifest

    return None


def download_and_apply_update(
    server_url: str,
    manifest: Dict[str, Any],
    target_dir: str,
    timeout: float = 25.0,
) -> Tuple[bool, str]:
    """Download bundle, verify SHA-256, and extract safely into target_dir."""
    bundle_url = f"{server_url.rstrip('/')}/api/update/bundle"
    expected_sha = str(manifest.get("sha256", "")).strip().lower()
    remote_ver = str(manifest.get("version", "baru"))

    if not manifest.get("filename"):
        _save_applied_version(target_dir, remote_ver)
        logger.info(f"[Updater] Rilis v{remote_ver} (tanpa paket kode) ditandai aktif.")
        return True, f"Rilis v{remote_ver} diterapkan."

    fd, tmp_path = tempfile.mkstemp(prefix="arcade_update_", suffix=".tar.gz")
    os.close(fd)

    try:
        logger.info(f"[Updater] Mengunduh paket update v{remote_ver} dari {bundle_url}...")
        req = urllib.request.Request(bundle_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp_path, "wb") as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)

        if expected_sha:
            actual_sha = _sha256_file(tmp_path).lower()
            if actual_sha != expected_sha:
                msg = f"Checksum SHA-256 tidak cocok (harap {expected_sha[:12]}, dapat {actual_sha[:12]})"
                logger.error(f"[Updater] {msg}")
                return False, msg

        abs_target = os.path.abspath(target_dir)
        extracted_count = 0
        with tarfile.open(tmp_path, "r:gz") as tf:
            members = tf.getmembers()
            for m in members:
                rel_name = m.name.lstrip("./")
                if not rel_name:
                    continue
                if os.path.isabs(m.name) or ".." in rel_name.split("/"):
                    return False, f"Path arsip tidak aman: {m.name}"
                base = os.path.basename(rel_name)
                if base in PROTECTED_BASENAMES or base.endswith(".log"):
                    continue
                dest_path = os.path.abspath(os.path.join(abs_target, rel_name))
                if not (dest_path == abs_target or dest_path.startswith(abs_target + os.sep)):
                    return False, f"Path arsip keluar dari target: {m.name}"

            for m in members:
                rel_name = m.name.lstrip("./")
                if not rel_name:
                    continue
                base = os.path.basename(rel_name)
                if base in PROTECTED_BASENAMES or base.endswith(".log"):
                    continue
                tf.extract(m, path=abs_target)
                extracted_count += 1

        _save_applied_version(abs_target, remote_ver)
        logger.info(f"[Updater] Update v{remote_ver} berhasil diterapkan ({extracted_count} item).")
        return True, f"Update v{remote_ver} berhasil diterapkan."
    except Exception as e:
        logger.warning(f"[Updater] Gagal menerapkan update: {e}")
        return False, str(e)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def sync_roms_from_server(
    server_url: str,
    roms_dir: str,
    timeout: float = 20.0,
) -> Tuple[int, int]:
    """Download new/updated ROMs from /api/roms/manifest and remove deleted ones.

    Returns (downloaded_count, removed_count).
    """
    import urllib.parse

    manifest_url = f"{server_url.rstrip('/')}/api/roms/manifest"
    try:
        req = urllib.request.Request(manifest_url, method="GET")
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status != 200:
                return 0, 0
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"[Updater] Lewati sinkronisasi ROM ({manifest_url}): {e}")
        return 0, 0

    os.makedirs(roms_dir, exist_ok=True)
    downloaded = 0
    removed = 0

    server_files = {}
    for g in data.get("games", []):
        safe = os.path.basename(str(g.get("filename", ""))).strip()
        if safe:
            server_files[safe] = g

    # Remove any local .zip/.7z in roms_dir not present on server (exact mirror)
    for local_name in os.listdir(roms_dir):
        if local_name.startswith("."):
            continue
        if not local_name.lower().endswith((".zip", ".7z")):
            continue
        if local_name not in server_files:
            target = os.path.join(roms_dir, local_name)
            if os.path.isfile(target):
                try:
                    os.remove(target)
                    removed += 1
                    logger.info(f"[Updater] ROM dihapus agar sinkron dengan server: {local_name}")
                except Exception:
                    pass

    for safe, g in server_files.items():
        expected_sha = str(g.get("sha256", "")).strip().lower()
        dest = os.path.join(roms_dir, safe)
        if os.path.isfile(dest) and expected_sha:
            try:
                if _sha256_file(dest).lower() == expected_sha:
                    continue
            except Exception:
                pass

        file_url = f"{server_url.rstrip('/')}/api/roms/file/{urllib.parse.quote(safe)}"
        tmp_rom = os.path.join(roms_dir, f".tmp_{safe}")
        try:
            logger.info(f"[Updater] Mengunduh game '{g.get('display_name', safe)}' ({safe})...")
            req = urllib.request.Request(file_url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp_rom, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
            if expected_sha and _sha256_file(tmp_rom).lower() != expected_sha:
                logger.warning(f"[Updater] SHA-256 ROM tidak cocok untuk {safe}, dibatalkan.")
                os.remove(tmp_rom)
                continue
            os.replace(tmp_rom, dest)
            downloaded += 1
        except Exception as e:
            logger.warning(f"[Updater] Gagal mengunduh ROM {safe}: {e}")
            if os.path.exists(tmp_rom):
                try:
                    os.remove(tmp_rom)
                except Exception:
                    pass

    return downloaded, removed

