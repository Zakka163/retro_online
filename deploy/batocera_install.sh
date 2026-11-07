#!/bin/bash
# Installer for Arcade Online Launcher on Batocera / EmuELEC Linux
set -e

echo "=== Memasang Arcade Online Launcher untuk Batocera / EmuELEC ==="

TARGET_DIR="/userdata/system/arcade_online"
PORTS_DIR="/userdata/roms/ports"

mkdir -p "$TARGET_DIR"
mkdir -p "$PORTS_DIR"

# Copy files
cp -r ../catalog "$TARGET_DIR/"
cp -r ../launcher "$TARGET_DIR/"
cp -r ../server "$TARGET_DIR/"
cp ../config.json "$TARGET_DIR/"

# Create launcher script in Batocera Ports
cat << 'EOF' > "$PORTS_DIR/ArcadeOnline.sh"
#!/bin/bash
# Batocera Ports Launcher script
cd /userdata/system/arcade_online
python3 -m launcher.main
EOF

chmod +x "$PORTS_DIR/ArcadeOnline.sh"

echo "Instalasi selesai!"
echo "Launcher dapat diakses melalui menu 'Ports' -> 'ArcadeOnline' pada EmulationStation."

