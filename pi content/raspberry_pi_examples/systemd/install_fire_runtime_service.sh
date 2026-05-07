#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="fire-smart-runtime.service"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="${SOURCE_DIR}/${SERVICE_NAME}"
TARGET_FILE="/etc/systemd/system/${SERVICE_NAME}"

if [[ ! -f "${SOURCE_FILE}" ]]; then
  echo "Service file not found: ${SOURCE_FILE}"
  exit 1
fi

sudo systemctl disable --now fire-video-stream.service 2>/dev/null || true
sudo cp "${SOURCE_FILE}" "${TARGET_FILE}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl status "${SERVICE_NAME}" --no-pager

echo "Installed and started ${SERVICE_NAME}"
