"""Arcade Online Self-Diagnostic and Preflight Health Check Tool.

Runs a complete 5-point system check:
1. RetroArch installation & executable path
2. Libretro arcade cores (MAME, FBNeo), including core version/fingerprint
3. ROM directories & detected arcade games
4. Matchmaking server reachability & ping
5. Netplay network port availability (55435, 55436)
"""

import os
import sys
import socket
import subprocess
import json
import urllib.request
import urllib.error
import hashlib
import glob

from catalog.validator import find_retroarch_binary
from catalog.scanner import SystemScanner
from launcher.connection_manager import get_local_ip

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_header(title: str):
    print(f"\n{BOLD}{CYAN}[+] {title}{RESET}")


def print_ok(text: str):
    print(f"  {GREEN}[✓] PASS:{RESET} {text}")


def print_warn(text: str):
    print(f"  {YELLOW}[!] WARN:{RESET} {text}")


def print_err(text: str):
    print(f"  {RED}[X] FAIL:{RESET} {text}")


def check_port(port: int) -> bool:
    """Check if a local TCP port is free to bind."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.close()
        return True
    except Exception:
        return False


def read_core_metadata(core_path: str):
    """Read Libretro core name/version from its matching .info file."""
    core_dir = os.path.dirname(core_path)
    core_stem = os.path.splitext(os.path.basename(core_path))[0]
    candidates = [os.path.join(core_dir, core_stem + ".info")]
    # Some installations keep .info files in a separate info directory.
    for directory in (
        os.path.join(core_dir, "..", "info"),
        os.path.expanduser("~/Library/Application Support/RetroArch/info"),
        os.path.expanduser("~/.config/retroarch/info"),
        "/storage/.config/retroarch/cores/info",
    ):
        candidates.extend(glob.glob(os.path.join(directory, core_stem + ".info")))

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as info_file:
                info = json.load(info_file)
            version = info.get("library_version")
            name = info.get("display_name") or info.get("corename") or info.get("library_name")
            if version or name:
                return name or "Unknown", version or "not declared", path
        except (OSError, ValueError, TypeError):
            continue
    return None


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as core_file:
        for chunk in iter(lambda: core_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_diagnostics(server_url: str = "http://localhost:8080"):
    if sys.platform == "win32":
        os.system("")  # Enable ANSI color escape codes on Windows CMD/PowerShell
    print(f"{BOLD}===================================================={RESET}")
    print(f"{BOLD}{YELLOW}   ARCADE ONLINE PREFLIGHT DIAGNOSTIC TOOL        {RESET}")
    print(f"{BOLD}===================================================={RESET}")

    all_passed = True

    # 1. Check RetroArch Binary
    print_header("1. PEMERIKSAAN EMULATOR RETROARCH")
    ra_bin = find_retroarch_binary()
    if ra_bin:
        print_ok(f"Binary RetroArch ditemukan: {ra_bin}")
        try:
            out = subprocess.check_output([ra_bin, "--version"], text=True, stderr=subprocess.STDOUT)
            ver_line = out.strip().split("\n")[0]
            print_ok(f"Versi: {ver_line}")
        except Exception:
            print_warn("Tidak dapat mengecek versi RetroArch secara langsung.")
    else:
        print_err("Executable RetroArch TIDAK DITEMUKAN di sistem!")
        print("      Saran: Pasang RetroArch atau set ARCADE_RETROARCH_BIN=/path/to/retroarch")
        all_passed = False

    # 2. Check Libretro Cores
    print_header("2. PEMERIKSAAN CORE LIBRETRO")
    scanner = SystemScanner()
    cores = scanner.scan_installed_cores()
    arcade_cores = [c for c in cores if any(k in c for k in ("mame", "fb", "arcade", "neo"))]
    other_cores = [c for c in cores if c not in arcade_cores]

    if cores:
        print_ok(f"Ditemukan total {len(cores)} core libretro:")
        for c in arcade_cores:
            metadata = read_core_metadata(cores[c])
            if metadata:
                core_title, core_version, info_path = metadata
                print(f"      - [Arcade] {c}: {core_title} {core_version} ({cores[c]})")
                print(f"        Core info: {info_path}")
            else:
                print(f"      - [Arcade] {c}: versi tidak ditemukan di file .info ({cores[c]})")
                print_warn(f"Versi {c} tidak bisa dibaca; bandingkan core yang dipakai di kedua perangkat.")
            try:
                print(f"        SHA-256 binary: {sha256_file(cores[c])}")
            except OSError as e:
                print_warn(f"Tidak dapat menghitung sidik jari core {c}: {e}")
        for c in other_cores:
            print(f"      - [Console] {c}: {cores[c]}")
    else:
        print_err("Tidak ada core libretro yang terdeteksi di direktori standar!")
        print("      Saran: Buka RetroArch -> Online Updater -> Core Downloader untuk mengunduh core.")
        all_passed = False

    # 3. Check ROM Directories & Games
    print_header("3. PEMERIKSAAN FOLDER ROM & GAME")
    rom_dirs = scanner.get_system_rom_directories()
    print_ok(f"Direktori pencarian ROM aktif ({len(rom_dirs)} lokasi):")
    for d in rom_dirs:
        print(f"      - {d}")

    games = scanner.scan_roms()
    ready_games = [g for g in games.values() if g.status == "ready"]
    if ready_games:
        print_ok(f"Ditemukan {len(ready_games)} game arcade siap main:")
        for g in ready_games:
            print(f"      - {g.display_name} [{g.rom_file}] -> Core: {g.core_name}")
    else:
        print_warn("Belum ada file ROM arcade (.zip) yang terdeteksi.")
        print("      Saran: Letakkan ROM arcade di salah satu direktori ROM di atas.")

    # 4. Check Network & Server
    print_header("4. KONEKTIVITAS JARINGAN & SERVER")
    local_ip = get_local_ip()
    print_ok(f"IP Jaringan Lokal: {local_ip}")

    try:
        import time
        start = time.time()
        req = urllib.request.Request(f"{server_url}/api/health", headers={"User-Agent": "ArcadeDiagnose/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            rtt = (time.time() - start) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "online":
                print_ok(f"Server Matchmaking terhubung: {server_url} (RTT: {rtt:.1f}ms)")
            else:
                print_warn(f"Server terhubung tetapi status: {data.get('status')}")
    except Exception as e:
        print_warn(f"Tidak dapat menghubungi server di {server_url}: {e}")
        print("      Info: Pastikan server sudah dijalankan (python3 -m server.app).")

    # 5. Check Ports
    print_header("5. KETERSEDIAAN PORT NETPLAY")
    p55435 = check_port(55435)
    p55436 = check_port(55436)

    if p55435:
        print_ok("Port Netplay Default (55435) BEBAS / SIAP DIGUNAKAN.")
    else:
        print_warn("Port 55435 sedang digunakan oleh proses lain.")

    if p55436:
        print_ok("Port Relay Default (55436) BEBAS / SIAP DIGUNAKAN.")
    else:
        print_warn("Port 55436 sedang digunakan oleh proses lain (mungkin server relay sedang berjalan).")

    # Final Verdict
    print(f"\n{BOLD}===================================================={RESET}")
    if all_passed and ready_games:
        print(f"{BOLD}{GREEN}HASIL DIAGNOSA: SISTEM 100% SIAP UNTUK ARCADE MULTIPLAYER!{RESET}")
    elif all_passed:
        print(f"{BOLD}{YELLOW}HASIL DIAGNOSA: SISTEM SIAP, TINGGAL MASUKKAN FILE ROM (.zip).{RESET}")
    else:
        print(f"{BOLD}{RED}HASIL DIAGNOSA: ADA BEBERAPA KOMPONEN YANG PERLU DIPERSIAPKAN.{RESET}")
    print(f"{BOLD}===================================================={RESET}\n")


if __name__ == "__main__":
    url = None
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                content = f.read()
            import re
            pattern = re.compile(r"(?:/\*.*?\*/|//[^\r\n]*|#[^\r\n]*)|(\"(?:\\.|[^\"\\])*\")", re.DOTALL)
            clean_json = pattern.sub(lambda m: m.group(1) if m.group(1) is not None else "", content)
            cfg = json.loads(clean_json)
            url = cfg.get("server", {}).get("url")
        except Exception:
            pass
    url = url or "http://localhost:8080"
    run_diagnostics(server_url=url)

