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
    BOOT_RUNNER="/storage/.config/arcade_boot.sh"
    mkdir -p /storage/.config

    cat << 'EOF' > "$BOOT_RUNNER"
#!/bin/bash
# Sembunyikan pesan kernel di konsol agar tidak menimpa UI
dmesg -n 1 >/dev/null 2>&1 || true

# Tunggu inisialisasi hardware & WiFi USB selesai
sleep 3

# Hentikan EmulationStation agar layar tty1 bebas
systemctl stop emustation >/dev/null 2>&1 || true

# Matikan blank layar & aktifkan tampilan via fbterm
echo 0 > /sys/class/graphics/fb0/blank 2>/dev/null || true
chvt 1

# Jalankan Arcade Online Launcher di atas fbterm agar menimpa logo splash EmuELEC
if command -v fbterm >/dev/null 2>&1; then
    fbterm -s 20 -- bash -c "cd /storage/online_netplay && python3 -m launcher.main" < /dev/tty1 > /dev/tty1 2>&1
else
    echo 1 > /sys/class/vtconsole/vtcon1/bind 2>/dev/null || true
    clear > /dev/tty1
    cd /storage/online_netplay
    TERM=linux python3 -m launcher.main < /dev/tty1 > /dev/tty1 2>&1
fi

# Jika pengguna keluar dari launcher (ESC/Back), kembalikan mode grafis & buka EmulationStation
if command -v graphicalmode.sh >/dev/null 2>&1; then
    graphicalmode.sh >/dev/null 2>&1
fi
systemctl start emustation
EOF
    chmod +x "$BOOT_RUNNER"

    cat << 'EOF' > "$CUSTOM_START"
#!/bin/bash
# EmuELEC memanggil custom_start.sh dengan argumen 'before' dan 'after'
if [ -n "$1" ] && [ "$1" != "before" ]; then
    exit 0
fi

# Jalankan di unit systemd terpisah agar emuelec-autostart.service langsung selesai
# dan tidak memunculkan pesan "A start job is running for emuelec-autostart.service"
if command -v systemd-run >/dev/null 2>&1; then
    systemd-run --no-block --unit=arcade-launcher /storage/.config/arcade_boot.sh >/dev/null 2>&1
else
    /storage/.config/arcade_boot.sh &
fi
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

