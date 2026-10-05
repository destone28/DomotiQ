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
# what git ignores stays on the PC, and what the board downloads or writes stays on the board
EXTRA=()
[ -f .git/info/exclude ] && EXTRA=(--exclude-from=.git/info/exclude)
rsync -a --delete --exclude .git --filter=':- .gitignore' "${EXTRA[@]}" \
    --exclude venv --exclude piper-venv --exclude models --exclude var --exclude llama.cpp \
    ./ "$HOST:domotiq/"
# the fixed sentences of the voice prepared on the PC (scripts/voice_cache.py), if there are any
if [ -d models/voice-cache ]; then
    rsync -a --delete models/voice-cache/ "$HOST:domotiq/models/voice-cache/"
fi
if [ "${2:-}" = "--install" ]; then
    ssh -t "$HOST" "cd ~/domotiq && bash scripts/install.sh"
else
    ssh "$HOST" "sudo -n systemctl restart domotiq" && echo "domotiq restarted on $HOST"
fi
