#!/usr/bin/env bash
set -euo pipefail

if ! command -v ufw >/dev/null 2>&1; then
  echo "ufw not found."
  exit 1
fi

sudo ufw delete allow from 127.0.0.1 to any port 5000 proto tcp || true
sudo ufw delete deny 5000/tcp || true
sudo ufw allow 5000/tcp
sudo ufw status numbered

echo "Port 5000 reopened to all hosts."
