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

ssh -o ConnectTimeout=8 "${EMUELEC_USER}@${EMUELEC_IP}" "mkdir -p '${TARGET_DIR}'"

# Trailing slashes copy the contents of the project directory into TARGET_DIR.
# --delete makes the EmuELEC directory match the Mac source, including configs.
rsync -av --delete --progress \
  --exclude='/.git/' \
  --exclude='/**/__pycache__/' \
  --exclude='*.pyc' \
  "${SOURCE_DIR}/" "${EMUELEC_USER}@${EMUELEC_IP}:${TARGET_DIR}/"

echo "Sync complete: ${TARGET_DIR} now mirrors ${SOURCE_DIR}."
