# 2. Install the software

DomotiQ runs as native systemd services on the UNO Q, not as an App Lab app: App Lab on the UNO Q offers no offline speech recognition or synthesis, its apps run in Docker, download their dependencies on first start and do not restart by themselves. One script, `scripts/install.sh`, installs everything: system packages, Python environments, models, the language model server, the microcontroller firmware, the settings of the house, the services and the hotspot.

## Before you start

- The board is prepared as in [chapter 1](01-prepare-uno-q.md): password, name, Wi-Fi with internet, SSH, system update.
- The board has internet. It is needed once, for packages and models; later updates can be copied from a PC without internet (see [Updates](#updates)).
- About 2.9 GB are free in `/home/arduino` (models about 1.4 GB, Python environments about 500 MB, compilers and llama.cpp about 600 MB, plus a margin).
- You have time: building `llama-server` alone takes about twenty minutes.

## Get the code and run the installer

Log in as `arduino` (`ssh casa1`) and clone the repository into `/home/arduino/domotiq`, the folder the services expect:

```bash
git clone https://github.com/destone28/DomotiQ ~/domotiq
cd ~/domotiq && bash scripts/install.sh --wifi domotica2026
```

In this guide the password of the Wi-Fi of the house is `domotica2026`; without `--wifi` the installer chooses one at random.

If `git` is missing on the board, install it first with `sudo apt-get install -y git`.

If the board cannot download the repository (for example because it is not public), copy it from the PC that has a copy. The board needs `rsync` (`sudo apt-get install -y rsync`); then, from the folder of the repository on the PC:

```bash
bash scripts/release.sh casa1 --install --wifi domotica2026
```

After `--install` come the options of the installer, the same as in the table below.

The script asks the `sudo` password (`domotiq2026`, the one of [chapter 1](01-prepare-uno-q.md)) once, only if `sudo` needs one, and keeps it alive until the end. Every step skips what is already done, so running it again is safe and is also the way to update an installed house.

### Options

| Option | Meaning |
|---|---|
| `--house N` | Number of the house, 1 to 254; without it the house is number 1. Sets the name (`casaN`), the Wi-Fi network (`DomotiQ-CasaN`), the channel (1, 11 or 6) and the address (`10.42.N.1`). Later runs read it from the saved settings. |
| `--wifi PASSWORD` | The password of the Wi-Fi of the house, 8 to 63 characters. Without it the installer chooses one at random the first time and then keeps it. |
| `--hotspot MODE` | `now`, `boot` or `no`. Default `boot`: the hotspot is configured and starts at the next boot. See [The hotspot](#the-hotspot). |
| `--no-llm` | Skip llama.cpp and the two language models. The house then understands only the phrases of its built-in parser, and writes no answers to questions about the world (it asks whoever asked, [chapter 8](08-voice.md#when-it-does-not-know-it-asks-and-learns)). |
| `--skip-firmware` | Do not rebuild or reload the microcontroller firmware. |

## What each step does

The script prints numbered steps. The numbers shift when a step is skipped by an option.

1. **Checks.** It must run as the user `arduino`; it warns if the project is not in `/home/arduino/domotiq` or if the system is not Debian 13; it checks the free space and the internet connection, and which house this is.
2. **System packages.** It installs the ALSA library from `trixie-backports` (the fix described in [chapter 1](01-prepare-uno-q.md#if-the-update-stops-on-an-alsa-dependency)), then `python3-venv`, `python3-dev`, `build-essential`, `cmake`, `git`, `curl`, `rsync`, `unzip`, `alsa-utils`, `v4l-utils`, `iw`, `sqlite3`, `avahi-daemon`, `dnsmasq-base` and `libgomp1`, and enables `avahi-daemon` and `ssh` at every boot. The factory image has no compiler and no cmake, which llama.cpp needs.
3. **Python environment of the application.** `venv/` with the exact versions listed in `requirements.txt`. An environment that is broken or copied from elsewhere is made again.
4. **Speech synthesis.** A separate environment, `piper-venv/`, with `piper-tts` 1.8.0 and Flask. Piper is GPL-3.0 and runs as its own program: the application talks to it over HTTP on the loopback interface and never imports it.
5. **Models.** Downloaded into `models/` and checked against the SHA-256 sums in `scripts/models.sha256`: the Piper voices `it_IT-serena-medium` (at a fixed revision) and `en_US-ljspeech-medium`, the Vosk models `vosk-model-small-it-0.22` and `vosk-model-small-en-us-0.15`, YOLOX-Nano (`yolox_nano.onnx`) and, unless `--no-llm`, `qwen2.5-0.5b-instruct-q4_k_m.gguf` (the commands) and `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (the free answers to questions about the world, service `domotiq-chat`). A file already present with the right checksum is not downloaded again.
6. **llama.cpp.** Fetches llama.cpp at the commit tested on the UNO Q (`74a7c897`), applies the kernels written for its processor, in the patch `scripts/llama/arm-nodot.patch`, and builds `llama-server` (about twenty minutes). Skipped when the same commit is already built with the same patch, or with `--no-llm`.
7. **Microcontroller firmware.** Installs the core `arduino:zephyr` 1.0.0 and the library `Arduino_RouterBridge` 0.4.3, compiles `firmware/domotiq_mcu` in the "Immediate" start mode (`wait_linux_boot=no`) and loads it with the local `remoteocd`, which needs no password. It is reloaded only when the sketch, the core, the library or the board options change. Finally `arduino-app-cli properties set default none` makes sure no App Lab app replaces the firmware at boot. See `firmware/domotiq_mcu/README.md` to do the same by hand.
8. **House settings.** Sets the host name `casaN` and the time zone Europe/Rome; creates the Wi-Fi password (if none exists yet); writes house number, names and network into `var/config/settings.json`.
9. **Services.** Installs `domotiq`, `domotiq-tts`, `domotiq-llm` and `domotiq-chat` in `/etc/systemd/system`, a `sudoers` rule, the script the web app uses to change the hotspot password (`/usr/local/sbin/domotiq-hotspot-psk`, which takes no arguments) and a journald limit (200 MB, 7 days of logs). It enables `domotiq-llm` and `domotiq-chat` only without `--no-llm`. It disables the automatic `apt` timers and holds `alsa-ucm-conf`, `libasound2t64` and the running kernel: nothing should update the system while the house is in use.
10. **Hotspot.** Creates or updates the hotspot profile, then applies `--hotspot` (`now`, `boot` or `no`).
11. **Start.** Restarts the services and prints a summary.

The summary looks like this:

```
DomotiQ casa1 is installed.
  Wi-Fi:    DomotiQ-Casa1   password: domotica2026
  Address:  http://10.42.1.1/   (on the hotspot)   http://casa1.local/
```

A password chosen by the installer is three groups of four characters, from an alphabet without the easily confused `i`, `l`, `o`, `0` and `1`. Write it down: every phone that joins the network of the house needs it. It is also in the web app, under **More → Settings → Wi-Fi of the house**. Never write it in the repository.

## Where things live

Everything is inside `/home/arduino/domotiq`:

| Path | Content |
|---|---|
| `venv/` | Python environment of the application |
| `piper-venv/` | separate environment of Piper |
| `models/` | Piper voices, Vosk models, YOLOX-Nano, Qwen2.5-0.5B, Qwen3.5-0.8B; the figurine network, if you trained it (`models/vision/figures.onnx` and `figures.json`, [chapter 7](07-recognition-and-identities.md#the-network-that-knows-the-figurines)); the voice sentences prepared ahead of time (`models/voice-cache/`) |
| `llama.cpp/` | llama.cpp sources and the built `llama-server` |
| `var/config/` | `settings.json`, `rules.json`, `identities.json`, `knowledge.json` (what the house learned by voice), `clock.json` |
| `var/calibration/` | camera calibration, empty-house reference (also in more lights, in `empties/`), locked camera settings |
| `var/photos/` | photos of the characters |
| `var/domotiq.db` | SQLite: events (7 days), positions (24 hours), change log, bin |
| `var/dataset/`, `var/recordings/` | captures and sequences recorded from the calibration page |
| `var/journal/` | the entries of **Image training**: the new presences, the names given and the blobs the network turned down, with their crops |
| `var/collect/` | the continuous collection of pictures for the network, when it is on |
| `var/voice/` | the sentences the voice has already synthesized, 3000 at most |
| `var/firmware/` | the last firmware build |

`var/` is what the house remembers. It belongs to that board and is excluded from the repository.

## The services

| Service | What it runs |
|---|---|
| `domotiq` | The application (`python -m domotiq`): web app on port 80, rules, voice, audio, the link to the microcontroller, with the vision as a child process. Restarts by itself, also when it stays stuck for two minutes. It may bind port 80 and set the clock, nothing else. |
| `domotiq-tts` | Piper's HTTP server on `127.0.0.1:5010`, with the voices in `models/piper`. |
| `domotiq-llm` | `llama-server` with Qwen2.5-0.5B-Instruct on `127.0.0.1:8081`, always loaded so free questions get a fast answer, at a lower CPU priority than vision and voice. The instructions it has read are saved in `/var/lib/domotiq-llm` and come back in a few seconds at the next starts instead of about 10 minutes ([chapter 8](08-voice.md)). Not enabled with `--no-llm`. |
| `domotiq-chat` | A second `llama-server`, with Qwen3.5-0.8B on `127.0.0.1:8082`, for the free answers to questions about the world, when the visitor chooses to wait for them ([chapter 8](08-voice.md)). Same low priority as `domotiq-llm`. Not enabled with `--no-llm`. |

`domotiq` starts after `arduino-router` (the system service that links Linux and the microcontroller) and after `domotiq-tts`. All the services restart automatically if they stop, and all of them start at boot: after a reboot the house comes up by itself.

Useful commands:

```bash
systemctl status domotiq domotiq-tts domotiq-llm domotiq-chat --no-pager
journalctl -u domotiq -f                 # follow the application log
sudo systemctl restart domotiq           # restart the application
```

The settings of the web app can also restart the application, reboot or power off the board (see [chapter 6](06-web-app.md#settings)).

## The hotspot

The house has its own Wi-Fi network, served by the board with NetworkManager in shared mode:

| | |
|---|---|
| SSID | `DomotiQ-Casa1` |
| Security | WPA2, password `domotica2026` (option `--wifi`) |
| Band and channel | 2.4 GHz, channel 1 |
| Address of the house | `10.42.1.1` |
| Names | `casa1.lan`, `casa1.local` |

With `--house N` they become `DomotiQ-CasaN`, `10.42.N.1` and `casaN`, and the channel goes through 1, 11 and 6.

The DNS of the hotspot answers for `casaN.lan` (and `domotiq.lan`), and it makes the iCloud Private Relay names fail at once, so iPhones do not wait for them. There is no captive portal on purpose: the captive-portal window of phones does not allow the camera, and on iPhone it closes when you switch app. Phones join the network with the Wi-Fi password and open the numeric address, which always works.

The board is either on your Wi-Fi network or on its hotspot. Switching to the hotspot drops the connection to your network, and your SSH session with it.

The installer option chooses the starting point:

- `--hotspot boot` (default): the hotspot starts by itself at every boot. The other Wi-Fi profiles stop connecting automatically, so they do not compete with it at boot.
- `--hotspot now`: switch to the hotspot immediately.
- `--hotspot no`: configure it but leave the board on your Wi-Fi network.

Later you can switch with `scripts/hotspot.sh`:

```bash
bash scripts/hotspot.sh on        # switch to the hotspot now (Wi-Fi client connections drop)
bash scripts/hotspot.sh off       # back to your Wi-Fi network
bash scripts/hotspot.sh boot      # the hotspot starts by itself at every boot
bash scripts/hotspot.sh status    # state of wlan0 and the active connections
```

`off` also lets the other Wi-Fi profiles connect automatically again. With the board on its hotspot, reach it from a PC joined to `DomotiQ-CasaN` with `ssh arduino@10.42.N.1`, or add an alias with `bash scripts/add-pc.sh casaN 10.42.N.1`.

## Updates

There are two ways to update an installed house.

**On the board, with internet.** Pull the new code and run the installer again; it redoes only what changed, and it remembers the house number:

```bash
cd ~/domotiq && git pull && bash scripts/install.sh
```

**From a PC, without internet on the board** (for example over the hotspot). From the folder of the repository on the PC:

```bash
bash scripts/release.sh casa1              # copy code, web app and data, restart domotiq
bash scripts/release.sh casa1 --install    # then run install.sh on the board (needs internet on the board)
```

`release.sh` copies the working tree of the PC to `~/domotiq` on the board with `rsync` over SSH (the `casa1` alias from `add-pc.sh`), then restarts `domotiq`. It leaves out what git ignores and what belongs to the board: `.git`, `venv`, `piper-venv`, `models`, `var` and `llama.cpp`. The board does not need git for this. The copy mirrors the PC: a code file changed only on the board is overwritten or removed. The exception is `models/voice-cache/`, the fixed sentences of the voice prepared ahead of time: if the PC has it, it is copied too.

**The sentences of the voice prepared ahead of time.** The fixed sentences of the house, the ones with no name or number in them, are synthesized once with `scripts/voice_cache.py` and copied to the house, so the first start does not wait for Piper:

```bash
venv/bin/python scripts/voice_cache.py                   # on the board, with its own Piper (quite a few minutes)
python scripts/voice_cache.py --url http://127.0.0.1:5010/synthesize   # on a PC (the Python environment of the repository)
```

The script writes to `models/voice-cache/` only the sentences that are missing, and with `--list` it only lists them. On a PC, start the Piper server as the `domotiq-tts` service does (the same version and voices as `install.sh`).

Without `--install`, a change to the firmware is copied but not loaded on the microcontroller, and new Python packages, models and service files in `scripts/systemd` (such as `domotiq-llm.service`) are not installed: use `--install` (or `install.sh` on the board) when those change. For one service alone, even with no internet, this on the board is enough (it asks for the password of `arduino`):

```bash
cd ~/domotiq && sudo install -m644 scripts/systemd/domotiq-llm.service /etc/systemd/system/ \
  && sudo systemctl daemon-reload && sudo systemctl restart domotiq-llm
```

## Protect access

The password `domotiq2026` of the `arduino` user, the one of [chapter 1](01-prepare-uno-q.md), is written in this guide, so whoever reads it knows it. When the house is ready, allow SSH with a key only:

1. From every PC that must keep reaching the board, run `bash scripts/add-pc.sh casaN` once (it copies a key to the board). If the board is already on its hotspot, join the PC to `DomotiQ-CasaN` and use `bash scripts/add-pc.sh casaN 10.42.N.1`.
2. On the board, allow only keys for SSH:

   ```bash
   cd ~/domotiq && bash scripts/lockdown.sh
   ```

   The script lists the keys that will still get in and refuses to run if there are none; `bash scripts/lockdown.sh --undo` allows passwords again. `sudo` keeps asking for the password of the user `arduino`, except for the few commands the web app needs (restart, reboot, power off, hotspot).
3. If you gave the `arduino` user password-less `sudo`, remove that rule: `sudo` must ask for the password. The small rule installed by DomotiQ, which only allows the commands of the web app, can stay.

The password of the Wi-Fi of the house can be changed at any time from **More → Settings** in the web app, or on the board:

```bash
cd ~/domotiq
PYTHONPATH=src venv/bin/python -m domotiq.admin wifi "a-new-password"
```

The command restarts the house so it reads the new value, and restarts the hotspot too if it is on.

Next: [print and assemble](03-print-and-assemble.md).
