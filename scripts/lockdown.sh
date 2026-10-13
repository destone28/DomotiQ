#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
#
# Lock SSH down: it accepts only keys, no passwords.
#
#   bash scripts/lockdown.sh          on the board, after scripts/add-pc.sh from every PC that needs access
#   bash scripts/lockdown.sh --undo   passwords allowed again
#
# sudo keeps asking for the password of the user arduino, except for the few
# commands the web app needs (restart, reboot, power off, hotspot).

set -euo pipefail
CONF=/etc/ssh/sshd_config.d/10-domotiq.conf

if [ "${1:-}" = "--undo" ]; then
    sudo rm -f "$CONF"
    sudo systemctl reload ssh
    echo "SSH accepts passwords again."
    exit 0
fi

KEYS="$HOME/.ssh/authorized_keys"
if [ ! -s "$KEYS" ]; then
    echo "No key in $KEYS: run scripts/add-pc.sh from your PC first, or you will be locked out."
    exit 1
fi
echo "Keys that will still get in:"
awk '{print "  " $NF}' "$KEYS"
sudo tee "$CONF" >/dev/null <<'CONF'
# DomotiQ: log in only with a key (scripts/lockdown.sh)
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
CONF
sudo sshd -t
sudo systemctl reload ssh
echo "SSH now accepts only keys. To allow passwords again: bash scripts/lockdown.sh --undo"
