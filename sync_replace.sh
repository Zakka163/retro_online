#!/bin/bash
set -euo pipefail

# Run this from the Mac project directory. The remote directory will be made
# an exact copy of that directory; remote-only files will be removed.
EMUELEC_IP="${1:-10.90.147.109}"
EMUELEC_USER="${2:-root}"
TARGET_DIR="/storage/online_netplay"
SOURCE_DIR="$(pwd -P)"

if [[ ! -d "$SOURCE_DIR/launcher" ]]; then
  echo "Error: $SOURCE_DIR does not look like the project directory (launcher/ is missing)." >&2
  exit 1
fi

echo "Source      : $SOURCE_DIR"
echo "Destination : ${EMUELEC_USER}@${EMUELEC_IP}:${TARGET_DIR}"
echo "This replaces the destination contents and deletes remote-only files."
read -r -p 'Type REPLACE to continue: ' answer
if [[ "$answer" != "REPLACE" ]]; then
  echo "Cancelled."
  exit 1
fi

ssh-keygen -R "${EMUELEC_IP}" >/dev/null 2>&1 || true
SSH_OPTS="-o ConnectTimeout=8 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

ssh ${SSH_OPTS} "${EMUELEC_USER}@${EMUELEC_IP}" "mkdir -p '${TARGET_DIR}'"

# Trailing slashes copy the contents of the project directory into TARGET_DIR.
# --delete makes the EmuELEC directory match the Mac source, including configs.
rsync -av --delete --progress \
  -e "ssh ${SSH_OPTS}" \
  --exclude='/.git/' \
  --exclude='/**/__pycache__/' \
  --exclude='*.pyc' \
  --exclude='/log_testing/' \
  --exclude='/logssh/' \
  --exclude='/*.log' \
  "${SOURCE_DIR}/" "${EMUELEC_USER}@${EMUELEC_IP}:${TARGET_DIR}/"

echo "Menyiapkan SSH key EmuELEC untuk upload log otomatis ke VPS..."
EMUELEC_PUBKEY=$(ssh ${SSH_OPTS} "${EMUELEC_USER}@${EMUELEC_IP}" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && ( [ -f ~/.ssh/id_ed25519.pub ] || [ -f ~/.ssh/id_rsa.pub ] || ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519 >/dev/null 2>&1 || ssh-keygen -t rsa -b 2048 -N '' -f ~/.ssh/id_rsa >/dev/null 2>&1 ) && cat ~/.ssh/id_ed25519.pub 2>/dev/null || cat ~/.ssh/id_rsa.pub 2>/dev/null" || true)

if [[ -n "${EMUELEC_PUBKEY}" ]]; then
  ssh -p 20157 -o BatchMode=yes -o StrictHostKeyChecking=no root@217.216.146.15 \
    "mkdir -p /root/.ssh /root/log_testing && chmod 700 /root/.ssh && touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys && grep -qxF '${EMUELEC_PUBKEY}' /root/.ssh/authorized_keys || echo '${EMUELEC_PUBKEY}' >> /root/.ssh/authorized_keys" 2>/dev/null \
    && echo "[OK] Kunci SSH EmuELEC terdaftar di VPS 217.216.146.15:20157." \
    || echo "[INFO] Untuk mendaftarkan SSH key log secara manual di EmuELEC: ssh -t ${EMUELEC_USER}@${EMUELEC_IP} 'cd ${TARGET_DIR} && ./setup_log_ssh.sh'"
fi

echo "Sync complete: ${TARGET_DIR} now mirrors ${SOURCE_DIR}."
