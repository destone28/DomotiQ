#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
#
# Copy the working tree from a PC to a house and restart the application,
# without git on the board and without internet (it works over the hotspot).
#
#   bash scripts/release.sh casa1            code, web app, data
#   bash scripts/release.sh casa1 --install  and then run install.sh on the board (needs internet)

set -euo pipefail
HOST="${1:-casa1}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
rsync -a --delete --exclude .git --exclude .venv --exclude venv --exclude piper-venv \
    --exclude models --exclude var --exclude llama.cpp --exclude __pycache__ --exclude .pytest_cache \
    ./ "$HOST:domotiq/"
if [ "${2:-}" = "--install" ]; then
    ssh -t "$HOST" "cd ~/domotiq && bash scripts/install.sh"
else
    ssh "$HOST" "sudo -n systemctl restart domotiq" && echo "domotiq restarted on $HOST"
fi
