#!/bin/bash
# Setup SSH key (sekali saja per mesin) agar launcher bisa mengirim log ke VPS
# tanpa kata sandi. Kata sandi VPS hanya diminta SATU KALI saat menyalin public key,
# dan tidak pernah disimpan di kode/skrip.
set -euo pipefail

VPS_HOST="${1:-217.216.146.15}"
VPS_PORT="${2:-20157}"
VPS_USER="${3:-root}"
REMOTE_DIR="/root/log_testing"

# EmuELEC memakai /storage sebagai HOME
SSH_DIR="${HOME}/.ssh"
KEY="${SSH_DIR}/id_ed25519"

mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"

if [[ ! -f "$KEY" ]]; then
  echo "[1/3] Membuat SSH key baru: $KEY"
  ssh-keygen -t ed25519 -N "" -C "arcade-$(hostname)" -f "$KEY" \
    || ssh-keygen -t rsa -b 4096 -N "" -C "arcade-$(hostname)" -f "${SSH_DIR}/id_rsa"
else
  echo "[1/3] SSH key sudah ada: $KEY"
fi
PUB="$(ls "${SSH_DIR}"/id_ed25519.pub "${SSH_DIR}"/id_rsa.pub 2>/dev/null | head -n1)"

echo "[2/3] Mendaftarkan public key ke ${VPS_USER}@${VPS_HOST}:${VPS_PORT} (masukkan password VPS sekali)..."
ssh -p "$VPS_PORT" -o StrictHostKeyChecking=accept-new "${VPS_USER}@${VPS_HOST}" \
  "mkdir -p ~/.ssh '${REMOTE_DIR}' && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && \
   chmod 600 ~/.ssh/authorized_keys && grep -qxF '$(cat "$PUB")' ~/.ssh/authorized_keys || \
   echo '$(cat "$PUB")' >> ~/.ssh/authorized_keys"

echo "[3/3] Menguji login tanpa password..."
if ssh -p "$VPS_PORT" -o BatchMode=yes "${VPS_USER}@${VPS_HOST}" "test -d '${REMOTE_DIR}' && echo OK"; then
  echo "[✓] Berhasil! Mesin ini siap mengirim log otomatis ke ${REMOTE_DIR}"
else
  echo "[X] Login tanpa password gagal. Periksa kembali key / izin di VPS." >&2
  exit 1
fi

