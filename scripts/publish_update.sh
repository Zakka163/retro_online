#!/bin/bash
# Script Rilis Update dari Mac -> VPS (Pendekatan 1: HTTP Bundle + SHA-256)
# Mengemas kode launcher terbaru, menghitung SHA-256, dan mengunggah ke VPS.

set -e

VPS_HOST="217.216.146.15"
VPS_PORT="20157"
VPS_USER="root"
VPS_UPDATES_DIR="/opt/arcade_online/updates"
NEW_VERSION=""
INCLUDE_ROMS=false
NOTES=""

print_usage() {
    cat << 'EOF'
Pemakaian:
  ./publish_update.sh [opsi]

Opsi:
  --version <X.Y.Z>   Naikkan LAUNCHER_VERSION di launcher/system_info.py sebelum rilis
  --notes "<TEKS>"    Catatan rilis singkat
  --with-roms         Sertakan folder roms/ ke dalam paket update
  -h, --help          Tampilkan bantuan ini

Contoh:
  ./publish_update.sh --version 1.2.1 --notes "Perbaikan menu dan koneksi"
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            print_usage
            exit 0
            ;;
        --version)
            NEW_VERSION="$2"
            shift 2
            ;;
        --notes)
            NOTES="$2"
            shift 2
            ;;
        --with-roms)
            INCLUDE_ROMS=true
            shift
            ;;
        *)
            echo "[!] Opsi tidak dikenal: $1"
            print_usage
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ -n "$NEW_VERSION" ]; then
    python3 - "$NEW_VERSION" << 'PYEOF'
import re, sys
ver = sys.argv[1].strip()
path = "launcher/system_info.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()
new_text, count = re.subn(r'LAUNCHER_VERSION\s*=\s*"[^"]+"', f'LAUNCHER_VERSION = "{ver}"', text, count=1)
if count != 1:
    print("[!] Gagal memperbarui LAUNCHER_VERSION di launcher/system_info.py", file=sys.stderr)
    sys.exit(1)
with open(path, "w", encoding="utf-8") as f:
    f.write(new_text)
print(f"[✓] LAUNCHER_VERSION diperbarui menjadi {ver}")
PYEOF
fi

VERSION=$(python3 -c '
import re
with open("launcher/system_info.py", "r", encoding="utf-8") as f:
    m = re.search(r"LAUNCHER_VERSION\s*=\s*\"([^\"]+)\"", f.read())
print(m.group(1) if m else "1.0.0")
')

BUNDLE_NAME="arcade_update_${VERSION}.tar.gz"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

BUNDLE_PATH="${TMP_DIR}/${BUNDLE_NAME}"
MANIFEST_PATH="${TMP_DIR}/manifest.json"

TARGETS=(launcher catalog server deploy scripts)
if [ "$INCLUDE_ROMS" = true ] && [ -d "roms" ]; then
    TARGETS+=(roms)
fi

echo "[1/3] Mengemas update v${VERSION} (${BUNDLE_NAME})..."
COPYFILE_DISABLE=1 tar -czf "$BUNDLE_PATH" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.log' \
    --exclude='.DS_Store' \
    "${TARGETS[@]}"

SHA256=$(shasum -a 256 "$BUNDLE_PATH" | awk '{print $1}')
SIZE=$(wc -c < "$BUNDLE_PATH" | tr -d ' ')

python3 - "$MANIFEST_PATH" "$VERSION" "$BUNDLE_NAME" "$SHA256" "$SIZE" "$NOTES" << 'PYEOF'
import json, sys, datetime
out_path, ver, fname, sha, size, notes = sys.argv[1:7]
data = {
    "update_available": True,
    "version": ver,
    "filename": fname,
    "sha256": sha,
    "size": int(size),
    "notes": notes,
    "released_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PYEOF

echo "[2/3] Mengunggah ke VPS ${VPS_HOST}:${VPS_UPDATES_DIR}..."
ssh -p "${VPS_PORT}" -o BatchMode=yes -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" \
    "mkdir -p ${VPS_UPDATES_DIR}"
scp -P "${VPS_PORT}" -o BatchMode=yes -o StrictHostKeyChecking=no \
    "$BUNDLE_PATH" "$MANIFEST_PATH" "${VPS_USER}@${VPS_HOST}:${VPS_UPDATES_DIR}/"

echo "[3/3] Verifikasi endpoint /api/version..."
ssh -p "${VPS_PORT}" -o BatchMode=yes -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" \
    "curl -s http://127.0.0.1:8080/api/version"
echo ""
echo "[✓] Rilis v${VERSION} selesai! Semua mesin akan otomatis update saat dinyalakan."

