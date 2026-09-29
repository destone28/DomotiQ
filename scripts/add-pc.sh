#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
#
# Let this PC reach a house over SSH with a key (asks the board password once).
#
#   bash scripts/add-pc.sh casa1            on the lab network (casa1.local)
#   bash scripts/add-pc.sh casa1 10.42.1.1  on the hotspot of the house

set -euo pipefail
NAME="${1:?usage: $0 casaN [address]}"
ADDR="${2:-$NAME.local}"
KEY="$HOME/.ssh/id_ed25519_domotiq"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
[ -f "$KEY" ] || ssh-keygen -t ed25519 -f "$KEY" -N "" -C "domotiq-$(hostname)"
ssh-copy-id -i "$KEY.pub" "arduino@$ADDR"
if ! grep -q "^Host $NAME\$" "$HOME/.ssh/config" 2>/dev/null; then
    cat >> "$HOME/.ssh/config" <<CFG

Host $NAME
    HostName $ADDR
    User arduino
    IdentityFile $KEY
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
CFG
fi
ssh "$NAME" 'echo "connected to $(hostname)"'
