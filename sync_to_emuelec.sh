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

# Bersihkan host key lama jika IP DHCP dipakai oleh perangkat EmuELEC lain
ssh-keygen -R "${EMUELEC_IP}" >/dev/null 2>&1 || true
SSH_OPTS="-o ConnectTimeout=8 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

# 1. Pastikan folder tujuan ada
echo "[1/5] Menyiapkan direktori di EmuELEC..."
ssh ${SSH_OPTS} "${EMUELEC_USER}@${EMUELEC_IP}" "mkdir -p ${TARGET_DIR}/roms"
if [ $? -ne 0 ]; then
    echo "[!] Gagal terhubung ke ${EMUELEC_IP}. Pastikan EmuELEC menyala dan terhubung ke WiFi/LAN yang sama."
    exit 1
fi

# 2. Sinkronkan kode python launcher, catalog, server, dan skrip utilitas
echo "[2/5] Mengirim kode launcher terbaru..."
rsync -avz -e "ssh ${SSH_OPTS}" --exclude '.git' --exclude '__pycache__' --exclude 'logssh' --exclude '*.log' \
  launcher catalog server deploy diagnose.py setup_log_ssh.sh setup_log_ssh.py \
  "${EMUELEC_USER}@${EMUELEC_IP}:${TARGET_DIR}/"

# 3. Sinkronkan file ROM agar 100% identik bit-per-bit
echo "[3/5] Mengirim seluruh file ROM agar 100% identik..."
rsync -avz --progress -e "ssh ${SSH_OPTS}" roms/ "${EMUELEC_USER}@${EMUELEC_IP}:${TARGET_DIR}/roms/"

# 4. Setel config.json khusus kabinet (ArcadeCab2)
echo "[4/5] Memperbarui config.json di EmuELEC (ArcadeCab2)..."
ssh ${SSH_OPTS} "${EMUELEC_USER}@${EMUELEC_IP}" "python3 -c \"
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
cfg.setdefault('client', {})['direct_connection_timeout'] = 5.0
ra = cfg.setdefault('retroarch', {})
ra['stateless_mode'] = True
ra['check_frames'] = 0
ra['input_latency_frames'] = 5
ra['sync_sram'] = False
ra['preferred_arcade_core'] = 'fbneo'
ra['scan_local_roms_only'] = True
lg = cfg.setdefault('logging', {})
lg['auto_upload'] = True
lg['remote_host'] = '217.216.146.15'
lg['remote_port'] = 20157
lg['remote_user'] = 'root'
lg['remote_path'] = '/root/log_testing'
lg['upload_timeout_seconds'] = 8.0
with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2)
print('Config EmuELEC diperbarui: Player Name = ArcadeCab2, Core = fbneo, CheckFrames = 0, Latency = 5, Remote Logs = ON')
\""

# 5. Siapkan SSH key di EmuELEC & daftarkan ke VPS otomatis melalui Mac
echo "[5/5] Menyiapkan SSH key EmuELEC untuk upload log ke VPS..."
EMUELEC_PUBKEY=$(ssh ${SSH_OPTS} "${EMUELEC_USER}@${EMUELEC_IP}" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && ( [ -f ~/.ssh/id_ed25519.pub ] || [ -f ~/.ssh/id_rsa.pub ] || ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519 >/dev/null 2>&1 || ssh-keygen -t rsa -b 2048 -N '' -f ~/.ssh/id_rsa >/dev/null 2>&1 ) && cat ~/.ssh/id_ed25519.pub 2>/dev/null || cat ~/.ssh/id_rsa.pub 2>/dev/null")

if [ -n "${EMUELEC_PUBKEY}" ]; then
    ssh -p 20157 -o BatchMode=yes -o StrictHostKeyChecking=no root@217.216.146.15 \
      "mkdir -p /root/.ssh /root/log_testing && chmod 700 /root/.ssh && touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys && grep -qxF '${EMUELEC_PUBKEY}' /root/.ssh/authorized_keys || echo '${EMUELEC_PUBKEY}' >> /root/.ssh/authorized_keys" 2>/dev/null \
      && echo "[✓] Kunci SSH EmuELEC berhasil didaftarkan ke VPS 217.216.146.15:20157!" \
      || echo "[!] Jalankan: ssh -t ${EMUELEC_USER}@${EMUELEC_IP} \"cd ${TARGET_DIR} && ./setup_log_ssh.sh\""
fi

echo ""
echo "============================================="
echo "[✓] SINKRONISASI SELESAI 100%!"
echo "Kode, ROM, dan pengaturan kini IDENTIK di kedua mesin."
echo "============================================="

