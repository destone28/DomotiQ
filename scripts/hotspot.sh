#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
#
# The Wi-Fi hotspot of the house (NetworkManager, shared mode, 2.4 GHz).
#
#   bash scripts/hotspot.sh setup N PASSWORD CHANNEL   create or update the profile of house N
#   bash scripts/hotspot.sh on        switch to the hotspot now (Wi-Fi client connections drop)
#   bash scripts/hotspot.sh off       back to the Wi-Fi of the lab
#   bash scripts/hotspot.sh boot      the hotspot starts by itself at every boot
#   bash scripts/hotspot.sh status
#
# No captive portal: phones join with the Wi-Fi password and open the address
# of the house. The DNS of the hotspot answers for casaN.lan and makes the
# iCloud Private Relay names fail fast, so iPhones do not wait for it.

set -euo pipefail
CON="domotiq-hotspot"

case "${1:-status}" in
    setup)
        HOUSE="$2"; PASS="$3"; CHANNEL="${4:-1}"
        ADDR="10.42.$HOUSE.1"
        if ! nmcli -t -f NAME connection show | grep -qx "$CON"; then
            sudo nmcli connection add type wifi ifname wlan0 con-name "$CON" ssid "DomotiQ-Casa$HOUSE" >/dev/null
        fi
        sudo nmcli connection modify "$CON" \
            802-11-wireless.ssid "DomotiQ-Casa$HOUSE" 802-11-wireless.mode ap 802-11-wireless.band bg \
            802-11-wireless.channel "$CHANNEL" wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn \
            wifi-sec.pairwise ccmp wifi-sec.group ccmp wifi-sec.psk "$PASS" \
            ipv4.method shared ipv4.addresses "$ADDR/24" ipv6.method disabled \
            connection.autoconnect no connection.autoconnect-priority 100
        sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
        sudo tee /etc/NetworkManager/dnsmasq-shared.d/domotiq.conf >/dev/null <<EOF
# DomotiQ: names of the house on its own hotspot
address=/casa$HOUSE.lan/$ADDR
address=/domotiq.lan/$ADDR
local=/lan/
# fail the iCloud Private Relay names at once (Apple's advice for local networks)
address=/mask.icloud.com/
address=/mask-h2.icloud.com/
EOF
        ;;
    on)
        sudo nmcli connection up "$CON"
        ;;
    off)
        sudo nmcli connection down "$CON" || true
        sudo nmcli connection modify "$CON" connection.autoconnect no
        for c in $(nmcli -t -f NAME,TYPE connection show | awk -F: '$2=="802-11-wireless" {print $1}'); do
            [ "$c" = "$CON" ] && continue
            sudo nmcli connection modify "$c" connection.autoconnect yes
        done
        nmcli device wifi rescan >/dev/null 2>&1 || true
        ;;
    boot)
        sudo nmcli connection modify "$CON" connection.autoconnect yes connection.autoconnect-priority 100
        # other Wi-Fi profiles would compete with the hotspot at boot
        for c in $(nmcli -t -f NAME,TYPE connection show | awk -F: '$2=="802-11-wireless" {print $1}'); do
            [ "$c" = "$CON" ] && continue
            sudo nmcli connection modify "$c" connection.autoconnect no
        done
        ;;
    status)
        nmcli -f GENERAL.STATE,IP4.ADDRESS device show wlan0 2>/dev/null || true
        nmcli -t -f NAME,DEVICE,TYPE connection show --active
        iw dev wlan0 info 2>/dev/null | grep -E "type|channel|ssid" || true
        ;;
    *)
        echo "usage: $0 setup N PASSWORD CHANNEL | on | off | boot | status"; exit 2 ;;
esac
