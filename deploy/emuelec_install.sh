#!/bin/bash
# Installer untuk Autostart Arcade Online Launcher di EmuELEC
# Mendukung 2 mode:
# 1. Kiosk/Boot Mode (Langsung buka launcher begitu EmuELEC dinyalakan)
# 2. Ports Mode (Muncul di menu EmulationStation Ports)

MODE="${1:-boot}" # 'boot' atau 'ports'
TARGET_DIR="/storage/online_netplay"

echo "=== Memasang Arcade Online Launcher di EmuELEC (Mode: $MODE) ==="

if [ "$MODE" = "boot" ]; then
    # Mode 1: Boot langsung saat mesin menyala (Kiosk)
    CUSTOM_START="/storage/.config/custom_start.sh"
    mkdir -p /storage/.config

    cat << 'EOF' > "$CUSTOM_START"
#!/bin/bash
# Tunggu inisialisasi hardware selesai
sleep 2

# Hentikan EmulationStation agar layar tty1 bebas
systemctl stop emustation

# Bersihkan dan arahkan input/output ke layar arcade (tty1)
chvt 1
clear > /dev/tty1

# Jalankan Arcade Online Launcher
cd /storage/online_netplay
TERM=linux python3 -m launcher.main < /dev/tty1 > /dev/tty1 2>&1

# Jika pengguna keluar dari launcher (ESC), lanjutkan buka EmulationStation
systemctl start emustation
EOF

    chmod +x "$CUSTOM_START"
    echo "[✓] Berhasil! EmuELEC sekarang akan langsung membuka Arcade Launcher saat booting."
    echo "    (Jika keluar dari launcher via ESC, EmulationStation akan terbuka)."

elif [ "$MODE" = "ports" ]; then
    # Mode 2: Masuk ke menu Ports di EmulationStation
    PORTS_DIR="/storage/roms/ports"
    mkdir -p "$PORTS_DIR"

    cat << 'EOF' > "$PORTS_DIR/Arcade_Online.sh"
#!/bin/bash
# Skrip Menu Ports EmuELEC
if command -v textmode.sh >/dev/null 2>&1; then
    textmode.sh
fi
clear

cd /storage/online_netplay
TERM=linux python3 -m launcher.main

if command -v graphicalmode.sh >/dev/null 2>&1; then
    graphicalmode.sh
fi
EOF

    chmod +x "$PORTS_DIR/Arcade_Online.sh"
    echo "[✓] Berhasil! Launcher sekarang tersedia di menu 'Ports' -> 'Arcade_Online' pada EmulationStation."

else
    echo "Penggunaan: $0 [boot|ports]"
    exit 1
fi

