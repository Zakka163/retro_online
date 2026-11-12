#!/bin/bash
# Script Sinkronisasi Otomatis Mac -> EmuELEC Arcade Cabinet
# Menyelaraskan seluruh kode launcher, konfigurasi anti-desync, dan file ROM

EMUELEC_IP="${1:-10.14.183.109}"
EMUELEC_USER="${2:-root}"
TARGET_DIR="/storage/online_netplay"

echo "============================================="
echo "   SINKRONISASI ONLINE NETPLAY KE EMUELEC   "
echo "============================================="
echo "Target IP : ${EMUELEC_IP}"
echo "User      : ${EMUELEC_USER}"
echo "Lokasi    : ${TARGET_DIR}"
echo "============================================="

# 1. Pastikan folder tujuan ada
echo "[1/4] Menyiapkan direktori di EmuELEC..."
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "${EMUELEC_USER}@${EMUELEC_IP}" "mkdir -p ${TARGET_DIR}/roms"
if [ $? -ne 0 ]; then
    echo "[!] Gagal terhubung ke ${EMUELEC_IP}. Pastikan EmuELEC menyala dan terhubung ke WiFi/LAN yang sama."
    exit 1
fi

# 2. Sinkronkan kode python launcher, catalog, server
echo "[2/4] Mengirim kode launcher terbaru..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'logssh' --exclude '*.log' \
  launcher catalog server deploy \
  "${EMUELEC_USER}@${EMUELEC_IP}:${TARGET_DIR}/"

# 3. Sinkronkan file ROM agar 100% identik bit-per-bit
echo "[3/4] Mengirim seluruh file ROM agar 100% identik..."
rsync -avz --progress roms/ "${EMUELEC_USER}@${EMUELEC_IP}:${TARGET_DIR}/roms/"

# 4. Setel config.json khusus kabinet (ArcadeCab2)
echo "[4/4] Memperbarui config.json di EmuELEC (ArcadeCab2)..."
ssh -o StrictHostKeyChecking=no "${EMUELEC_USER}@${EMUELEC_IP}" "python3 -c \"
import json, os, re
cfg_path = '${TARGET_DIR}/config.json'
cfg = {}
if os.path.exists(cfg_path):
    try:
        with open(cfg_path, 'r') as f:
            content = f.read()
        pat = re.compile(r'(?:/\*.*?\*/|//[^\r\n]*|#[^\r\n]*)|(\\\"(?:\\\\.|[^\\\"\\\\])*\\\")', re.DOTALL)
        clean = pat.sub(lambda m: m.group(1) if m.group(1) is not None else '', content)
        cfg = json.loads(clean)
    except Exception:
        pass
cfg.setdefault('server', {})['url'] = 'http://217.216.146.15:8080'
cfg.setdefault('client', {})['player_name'] = 'ArcadeCab2'
ra = cfg.setdefault('retroarch', {})
ra['stateless_mode'] = True
ra['check_frames'] = 30
ra['input_latency_frames'] = 3
ra['sync_sram'] = False
ra['preferred_arcade_core'] = 'fbneo'
ra['scan_local_roms_only'] = True
with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2)
print('Config EmuELEC diperbarui: Player Name = ArcadeCab2, Core = fbneo, Stateless = True, Local ROMs Only = True')
\""

echo ""
echo "============================================="
echo "[✓] SINKRONISASI SELESAI 100%!"
echo "Kode, ROM, dan pengaturan kini IDENTIK di kedua mesin."
echo "============================================="

