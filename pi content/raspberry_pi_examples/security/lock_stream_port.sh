#!/usr/bin/env bash
set -euo pipefail

BACKEND_IP="${1:-}"

if [[ -z "${BACKEND_IP}" ]]; then
  echo "Usage: $0 <BACKEND_LAN_IP>"
  echo "Example: $0 192.168.100.4"
  exit 1
fi

if ! command -v ufw >/dev/null 2>&1; then
  echo "ufw not found. Install with: sudo apt update && sudo apt install -y ufw"
  exit 1
fi

# Allow local loopback and backend host to reach stream port.
sudo ufw allow from 127.0.0.1 to any port 5000 proto tcp
sudo ufw allow from "${BACKEND_IP}" to any port 5000 proto tcp

# Deny everyone else.
sudo ufw deny 5000/tcp

# Ensure ufw is enabled.
sudo ufw --force enable
sudo ufw status numbered

echo "Port 5000 is now restricted to localhost and backend ${BACKEND_IP}."
