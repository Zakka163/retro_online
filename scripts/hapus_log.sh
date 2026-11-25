#!/usr/bin/env bash
set -euo pipefail

REMOTE="root@217.216.146.15"
PORT="20157"
REMOTE_PATH="~/log_testing"

if ! command -v ssh >/dev/null 2>&1; then
  echo "Error: ssh tidak ditemukan. Pasang OpenSSH Client terlebih dahulu." >&2
  exit 1
fi

echo "Target penghapusan: $REMOTE:$REMOTE_PATH"
read -r -p 'Ketik HAPUS untuk melanjutkan: ' CONFIRM

if [[ "$CONFIRM" != "HAPUS" ]]; then
  echo "Dibatalkan."
  exit 0
fi

ssh -p "$PORT" "$REMOTE" \
  'if [ -d "$HOME/log_testing" ]; then
     find "$HOME/log_testing" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
     echo "Isi log_testing berhasil dihapus."
   else
     echo "Direktori ~/log_testing tidak ditemukan." >&2
     exit 1
   fi'