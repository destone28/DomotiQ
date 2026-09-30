#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
#
# DomotiQ - installs the house on an Arduino UNO Q.
#
#   git clone https://github.com/destone28/DomotiQ ~/domotiq
#   cd ~/domotiq && bash scripts/install.sh --house 1
#
# Needs internet once. Every step skips what is already done, so the same
# command also updates an installed house (after `git pull`).
#
# Options:
#   --house N          house number, 1 or 2 (sets name, Wi-Fi, address)
#   --hotspot MODE     now | boot | no   (default: boot = active from the next start)
#   --pin NNNN         staff PIN (default: generated and printed at the end)
#   --no-llm           skip llama.cpp and the language model
#   --skip-firmware    do not rebuild or reload the microcontroller firmware

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOUSE=""
HOTSPOT="boot"
PIN=""
STORY_MODEL="Qwen_Qwen3.5-0.8B-Q4_0.gguf"      # Apache-2.0; see docs/decisioni.md D-19
STORY_URL="https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF/resolve/main/$STORY_MODEL"
WITH_LLM=1
WITH_FIRMWARE=1
while [ $# -gt 0 ]; do
    case "$1" in
        --house) HOUSE="$2"; shift 2 ;;
        --hotspot) HOTSPOT="$2"; shift 2 ;;
        --pin) PIN="$2"; shift 2 ;;
        --no-llm) WITH_LLM=0; shift ;;
        --skip-firmware) WITH_FIRMWARE=0; shift ;;
        *) echo "unknown option: $1"; exit 2 ;;
    esac
done

CORE_MCU="arduino:zephyr@1.0.0"
LIBS_MCU="Arduino_RouterBridge@0.4.3"
FQBN="arduino:zephyr:unoq:wait_linux_boot=no"
LLAMA_REPO="https://github.com/ggml-org/llama.cpp"
LLAMA_COMMIT="74a7c897f049c17e7080423aa2111776eff6ebbf"   # tested on the UNO Q
PIPER_VERSION="1.8.0"
VOICES_REV="ea046e8458f6acd997706d6e6066a022b42f6fb1"
MODELS="$ROOT/models"
VAR="$ROOT/var"

B=$'\033[1m'; G=$'\033[32m'; R=$'\033[31m'; N=$'\033[0m'
[ -t 1 ] || { B=''; G=''; R=''; N=''; }
STEP=0
step() { STEP=$((STEP + 1)); echo; echo "${B}[$STEP] $*${N}"; }
ok() { echo "    ${G}ok${N} $*"; }
die() { echo "${R}ERROR:${N} $*" >&2; exit 1; }

# sudo asks for the password once, and only if it needs one
if ! sudo -n true 2>/dev/null; then
    echo "sudo needs the password of the user $(whoami):"
    sudo -v
fi
( while true; do sudo -n true; sleep 50; done ) 2>/dev/null &
KEEP_SUDO=$!
trap 'kill $KEEP_SUDO 2>/dev/null || true' EXIT

# ---------------------------------------------------------------------------
step "Checks"
[ "$(whoami)" = "arduino" ] || die "run this as the user arduino"
[ "$ROOT" = "/home/arduino/domotiq" ] || echo "    note: the services expect the project in /home/arduino/domotiq (it is in $ROOT)"
grep -q 'VERSION_ID="13"' /etc/os-release || echo "    note: tested on Debian 13 (trixie)"
FREE=$(df -Pm "$ROOT" | awk 'NR==2 {print $4}')
# what is still missing: models about 800 MB, environments 500 MB, compilers and llama.cpp 600 MB
NEED=400
[ -f "$MODELS/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf" ] || NEED=$((NEED + 800))
[ -f "$MODELS/llm/$STORY_MODEL" ] || NEED=$((NEED + 700))
[ -x venv/bin/python ] && [ -x piper-venv/bin/python ] || NEED=$((NEED + 500))
[ -x llama.cpp/build/bin/llama-server ] || NEED=$((NEED + 600))
[ "$FREE" -gt "$NEED" ] || die "at least $NEED MB free are needed in $ROOT (free: ${FREE} MB)"
curl -sfI https://deb.debian.org >/dev/null || die "no internet: the first installation downloads packages and models"
if [ -z "$HOUSE" ]; then
    HOUSE=$(python3 -c "import json;print(json.load(open('$VAR/config/settings.json'))['house']['number'])" 2>/dev/null || echo "")
fi
[ "$HOUSE" = "1" ] || [ "$HOUSE" = "2" ] || die "which house is this? use --house 1 or --house 2"
ok "house $HOUSE, ${FREE} MB free"

# ---------------------------------------------------------------------------
step "System packages"
# The image prefers the audio profiles from trixie-backports but not the ALSA
# library they need: without this the system update stops on a dependency.
if ! dpkg -l libasound2t64 2>/dev/null | grep -q "bpo13"; then
    sudo NEEDRESTART_SUSPEND=1 DEBIAN_FRONTEND=noninteractive apt-get install -y -t trixie-backports \
        libasound2t64 libasound2-data libatopology2t64 alsa-ucm-conf >/dev/null
    ok "ALSA library from backports"
fi
sudo NEEDRESTART_SUSPEND=1 DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-venv python3-dev build-essential cmake git curl rsync unzip \
    alsa-utils v4l-utils iw sqlite3 avahi-daemon dnsmasq-base libgomp1 >/dev/null
sudo systemctl enable --now avahi-daemon >/dev/null 2>&1 || true
ok "packages installed"

# ---------------------------------------------------------------------------
step "Python environment of the application"
# an environment copied from elsewhere or half made does not work: make it again
venv_ok() { [ -x "$1/bin/python" ] && "$1/bin/python" -m pip --version >/dev/null 2>&1; }
venv_ok venv || { rm -rf venv; python3 -m venv venv; }
./venv/bin/python -m pip install -q --upgrade pip
./venv/bin/python -m pip install -q -r requirements.txt
ok "$(./venv/bin/python --version) with $(./venv/bin/python -m pip freeze | wc -l) packages"

# ---------------------------------------------------------------------------
step "Speech synthesis (Piper, separate environment)"
# Piper is GPL-3.0: it runs as its own program, in its own environment, and
# the application talks to it over HTTP on the loopback interface.
venv_ok piper-venv || { rm -rf piper-venv; python3 -m venv piper-venv; }
./piper-venv/bin/python -m pip install -q "piper-tts==$PIPER_VERSION" flask
ok "piper-tts $PIPER_VERSION"

# ---------------------------------------------------------------------------
step "Models"
mkdir -p "$MODELS"/{piper,vosk,llm,vision}
fetch() {  # fetch <url> <destination>, checked against scripts/models.sha256
    local url="$1" dest="$2" name
    name="$(basename "$dest")"
    if [ -f "$dest" ] && grep " $name\$" scripts/models.sha256 | (cd "$(dirname "$dest")" && sha256sum -c --status); then
        return 0
    fi
    curl -fL --retry 3 -o "$dest.part" "$url"
    mv "$dest.part" "$dest"
    grep " $name\$" scripts/models.sha256 | (cd "$(dirname "$dest")" && sha256sum -c --status) \
        || die "checksum mismatch for $name"
}
HF="https://huggingface.co/rhasspy/piper-voices/resolve/$VOICES_REV"
fetch "$HF/it/it_IT/serena/medium/it_IT-serena-medium.onnx" "$MODELS/piper/it_IT-serena-medium.onnx"
fetch "$HF/it/it_IT/serena/medium/it_IT-serena-medium.onnx.json" "$MODELS/piper/it_IT-serena-medium.onnx.json"
fetch "$HF/en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx" "$MODELS/piper/en_US-ljspeech-medium.onnx"
fetch "$HF/en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx.json" "$MODELS/piper/en_US-ljspeech-medium.onnx.json"
for m in vosk-model-small-it-0.22 vosk-model-small-en-us-0.15; do
    if [ ! -d "$MODELS/vosk/$m" ]; then
        fetch "https://alphacephei.com/vosk/models/$m.zip" "$MODELS/vosk/$m.zip"
        (cd "$MODELS/vosk" && unzip -q "$m.zip" && rm "$m.zip")
    fi
done
fetch "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx" "$MODELS/vision/yolox_nano.onnx"
if [ "$WITH_LLM" = 1 ]; then
    fetch "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf" \
          "$MODELS/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf"
    # the storyteller (domotiq-story): a model that writes Italian and English well enough for stories
    fetch "$STORY_URL" "$MODELS/llm/$STORY_MODEL"
    ln -sfn "$STORY_MODEL" "$MODELS/llm/story.gguf"
fi
ok "$(du -sh "$MODELS" | cut -f1) of models"

# ---------------------------------------------------------------------------
if [ "$WITH_LLM" = 1 ]; then
    step "llama.cpp (language model server)"
    if [ -x llama.cpp/build/bin/llama-server ] && [ "$(git -C llama.cpp rev-parse HEAD 2>/dev/null)" = "$LLAMA_COMMIT" ]; then
        ok "already built at ${LLAMA_COMMIT:0:7}"
    else
        if [ ! -d llama.cpp/.git ]; then
            rm -rf llama.cpp
            git init -q llama.cpp
            git -C llama.cpp remote add origin "$LLAMA_REPO"
        fi
        git -C llama.cpp fetch -q --depth 1 origin "$LLAMA_COMMIT"
        git -C llama.cpp checkout -q --force FETCH_HEAD
        echo "    building llama-server (about twenty minutes)"
        cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DLLAMA_CURL=OFF >/dev/null
        cmake --build llama.cpp/build -j"$(nproc)" --target llama-server >/dev/null
        ok "llama-server built at ${LLAMA_COMMIT:0:7}"
    fi
fi

# ---------------------------------------------------------------------------
if [ "$WITH_FIRMWARE" = 1 ]; then
    step "Microcontroller firmware"
    arduino-cli core update-index >/dev/null
    arduino-cli core install "$CORE_MCU" >/dev/null
    # shellcheck disable=SC2086
    arduino-cli lib install $LIBS_MCU >/dev/null
    SIGN=$( (cat firmware/domotiq_mcu/*.ino; echo "$CORE_MCU $LIBS_MCU $FQBN") | sha256sum | cut -c1-16)
    OUT="$VAR/firmware"
    mkdir -p "$OUT"
    if [ "$(cat "$OUT/.loaded" 2>/dev/null)" = "$SIGN" ]; then
        ok "already loaded"
    else
        arduino-cli compile -b "$FQBN" --output-dir "$OUT" firmware/domotiq_mcu >/dev/null
        P="$HOME/.arduino15/packages/arduino"
        OCD=$(find "$P/tools/remoteocd" -name remoteocd -type f | sort -V | tail -1)
        VARIANT="$P/hardware/zephyr/${CORE_MCU##*@}"
        CFG="$VARIANT/variants/arduino_uno_q_stm32u585xx/flash_sketch.cfg"
        LOADER="$VARIANT/firmwares/zephyr-arduino_uno_q_stm32u585xx.elf"
        [ -x "$OCD" ] && [ -f "$CFG" ] && [ -f "$LOADER" ] || die "remoteocd or the OpenOCD configuration not found"
        "$OCD" upload -f "$CFG" "$LOADER" "$OUT/domotiq_mcu.ino.elf-zsk.bin" >/dev/null 2>&1 \
            || die "loading the firmware failed"
        echo "$SIGN" > "$OUT/.loaded"
        ok "firmware loaded"
    fi
    # an App Lab app started at boot would replace this firmware
    arduino-app-cli properties set default none >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------------------
step "House settings"
mkdir -p "$VAR/config"
arduino-app-cli system set-name "casa$HOUSE" >/dev/null 2>&1 || sudo hostnamectl set-hostname "casa$HOUSE"
sudo timedatectl set-timezone Europe/Rome
if [ -z "$PIN" ] && ! python3 -c "import json,sys;d=json.load(open('$VAR/config/settings.json'));sys.exit(0 if d['staff']['pin_hash'] else 1)" 2>/dev/null; then
    PIN=$(python3 -c "import secrets;print(''.join(secrets.choice('0123456789') for _ in range(4)))")
    NEW_PIN="$PIN"
fi
WIFI_PASS=$(python3 -c "import json;print(json.load(open('$VAR/config/settings.json'))['network']['password'])" 2>/dev/null || echo "")
if [ -z "$WIFI_PASS" ]; then
    WIFI_PASS=$(python3 -c "import secrets;a='abcdefghjkmnpqrstuvwxyz23456789';print('-'.join(''.join(secrets.choice(a) for _ in range(4)) for _ in range(3)))")
fi
CHANNEL=$([ "$HOUSE" = 1 ] && echo 1 || echo 11)
PYTHONPATH=src ./venv/bin/python - "$HOUSE" "$WIFI_PASS" "$CHANNEL" "${PIN:-}" <<'EOF'
import sys
from domotiq.settings import Paths, Settings
house, password, channel, pin = sys.argv[1:5]
s = Settings(Paths())
s.update({"house": {"number": int(house), "name": {"it": f"Casa {house}", "en": f"House {house}"}},
          "network": {"ssid": f"DomotiQ-Casa{house}", "password": password, "channel": int(channel),
                      "address": f"10.42.{house}.1", "hostname": f"casa{house}"}})
if pin:
    s.set_pin(pin)
EOF
ok "casa$HOUSE, Wi-Fi DomotiQ-Casa$HOUSE"

# ---------------------------------------------------------------------------
step "Services"
sudo install -m644 scripts/systemd/domotiq.service scripts/systemd/domotiq-tts.service \
    scripts/systemd/domotiq-llm.service scripts/systemd/domotiq-story.service /etc/systemd/system/
# the only way the web app changes the hotspot password: a root-owned script, no wildcard sudo rule
sudo install -o root -g root -m755 scripts/systemd/domotiq-hotspot-psk /usr/local/sbin/domotiq-hotspot-psk
# check the rules before they go live: a broken sudoers file would lock sudo out
sudo visudo -cf scripts/systemd/domotiq.sudoers >/dev/null || die "scripts/systemd/domotiq.sudoers is not valid"
sudo install -o root -g root -m440 scripts/systemd/domotiq.sudoers /etc/sudoers.d/60-domotiq
sudo install -m644 scripts/systemd/journald-domotiq.conf /etc/systemd/journald.conf.d/60-domotiq.conf 2>/dev/null \
    || { sudo mkdir -p /etc/systemd/journald.conf.d && sudo install -m644 scripts/systemd/journald-domotiq.conf /etc/systemd/journald.conf.d/60-domotiq.conf; }
sudo systemctl daemon-reload
sudo systemctl enable domotiq-tts domotiq >/dev/null
if [ "$WITH_LLM" = 1 ]; then sudo systemctl enable domotiq-llm domotiq-story >/dev/null; fi
# nothing should update the system at a fair
sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
sudo apt-mark hold alsa-ucm-conf libasound2t64 "linux-image-$(uname -r)" >/dev/null 2>&1 || true
ok "domotiq, domotiq-tts$([ "$WITH_LLM" = 1 ] && echo ", domotiq-llm, domotiq-story")"

# ---------------------------------------------------------------------------
step "Hotspot"
bash scripts/hotspot.sh setup "$HOUSE" "$WIFI_PASS" "$CHANNEL"
case "$HOTSPOT" in
    now)  bash scripts/hotspot.sh on;   ok "hotspot active now" ;;
    boot) bash scripts/hotspot.sh boot; ok "hotspot active from the next start" ;;
    no)   ok "hotspot configured but not active (bash scripts/hotspot.sh on)" ;;
esac

# ---------------------------------------------------------------------------
step "Start"
sudo systemctl restart domotiq-tts
[ "$WITH_LLM" = 1 ] && sudo systemctl restart domotiq-llm domotiq-story || true
sudo systemctl restart domotiq
echo
echo "${B}DomotiQ casa$HOUSE is installed.${N}"
echo "  Wi-Fi:    DomotiQ-Casa$HOUSE   password: $WIFI_PASS"
echo "  Address:  http://10.42.$HOUSE.1/   (on the hotspot)   http://casa$HOUSE.local/"
[ -n "${NEW_PIN:-}" ] && echo "  Staff PIN: $NEW_PIN   (write it down: it is not shown again)"
echo "  Sign to print: http://10.42.$HOUSE.1/sign"
