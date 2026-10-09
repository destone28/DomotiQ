#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
#
# Let this PC reach a house over SSH with a key (asks the board password once).
#
#   bash scripts/add-pc.sh casa1            the board on the same network as the PC (casa1.local)
#   bash scripts/add-pc.sh casa1 10.42.1.1  the PC on the hotspot of the house

set -euo pipefail
NAME="${1:?usage: $0 casaN [address]}"
ADDR="${2:-$NAME.local}"
KEY="$HOME/.ssh/id_ed25519_domotiq"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
[ -f "$KEY" ] || ssh-keygen -t ed25519 -f "$KEY" -N "" -C "domotiq-$(hostname)"

# A board keeps the identity it made at its first start. A new or reinstalled board with the name of one this PC
# already knows has another, and ssh refuses it: say so, and forget the old one only if asked.
check=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes "arduino@$ADDR" true 2>&1 || true)
if grep -q "REMOTE HOST IDENTIFICATION HAS CHANGED" <<<"$check"; then
    echo "The board at $ADDR has another identity than the one this PC remembers for that name:"
    echo "a new or reinstalled board answers there."
    read -r -p "Forget the old identity and trust this board? [y/N] " answer
    case "$answer" in
        [yY]*) ssh-keygen -R "$ADDR" >/dev/null ;;
        *) exit 1 ;;
    esac
elif grep -qiE "could not resolve|no route to host|timed out|connection refused|network is unreachable" <<<"$check"; then
    echo "The board does not answer at $ADDR:"
    head -n 2 <<<"$check" | sed 's/^/  /'
    echo "With the board on the same network as the PC use its name (bash scripts/add-pc.sh casa1);"
    echo "with the PC on the hotspot of the house add the address (bash scripts/add-pc.sh casa1 10.42.1.1)."
    exit 1
fi

ssh-copy-id -i "$KEY.pub" "arduino@$ADDR"
if grep -q "^Host $NAME\$" "$HOME/.ssh/config" 2>/dev/null; then
    now=$(ssh -G "$NAME" | awk '$1 == "hostname" {print $2}')
    [ "$now" = "$ADDR" ] || echo "~/.ssh/config already has Host $NAME with the address $now (not $ADDR): left as it is."
else
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
