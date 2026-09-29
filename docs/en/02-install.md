# 2. Install the software

DomotiQ runs as native systemd services on the UNO Q, not as an App Lab app: App Lab on the UNO Q offers no offline speech recognition or synthesis, its apps run in Docker, download their dependencies on first start and do not restart by themselves. One script, `scripts/install.sh`, installs everything: system packages, Python environments, models, the language model server, the microcontroller firmware, the settings of the house, the services and the hotspot.

## Before you start

- The board is prepared as in [chapter 1](01-prepare-uno-q.md): password, name, Wi-Fi with internet, SSH, system update.
- The board has internet. It is needed once, for packages and models; later updates can be copied from a PC without internet (see [Updates](#updates)).
- About 2.3 GB are free in `/home/arduino` (models about 800 MB, Python environments about 500 MB, compilers and llama.cpp about 600 MB, plus a margin).
- You have time: building `llama-server` alone takes about twenty minutes.

## Get the code and run the installer

Log in as `arduino` (`ssh casa1`) and clone the repository into `/home/arduino/domotiq`, the folder the services expect:

```bash
git clone https://github.com/destone28/DomotiQ ~/domotiq
cd ~/domotiq && bash scripts/install.sh --house 1
```

If `git` is missing on the board, install it first with `sudo apt-get install -y git`.

The script asks the `sudo` password once, only if `sudo` needs one, and keeps it alive until the end. Every step skips what is already done, so running it again is safe and is also the way to update an installed house.

### Options

| Option | Meaning |
|---|---|
| `--house N` | House number, `1` or `2`. Sets the name (`casaN`), the Wi-Fi network (`DomotiQ-CasaN`), the channel and the address (`10.42.N.1`). Needed the first time; later runs read it from the saved settings. |
| `--hotspot MODE` | `now`, `boot` or `no`. Default `boot`: the hotspot is configured and starts at the next boot. See [The hotspot](#the-hotspot). |
| `--pin NNNN` | Staff PIN for the web app. Without it, the installer picks a random 4-digit PIN the first time and prints it at the end. Giving `--pin` on a later run replaces the PIN. |
| `--no-llm` | Skip llama.cpp and the language model. The house then understands only the phrases of its built-in parser. |
| `--skip-firmware` | Do not rebuild or reload the microcontroller firmware. |

## What each step does

The script prints numbered steps. The numbers shift when a step is skipped by an option.

1. **Checks.** It must run as the user `arduino`; it warns if the project is not in `/home/arduino/domotiq` or if the system is not Debian 13; it checks the free space and the internet connection, and which house this is.
2. **System packages.** It installs the ALSA library from `trixie-backports` (the fix described in [chapter 1](01-prepare-uno-q.md#if-the-update-stops-on-an-alsa-dependency)), then `python3-venv`, `python3-dev`, `build-essential`, `cmake`, `git`, `curl`, `rsync`, `unzip`, `alsa-utils`, `v4l-utils`, `iw`, `sqlite3`, `avahi-daemon`, `dnsmasq-base` and `libgomp1`, and enables `avahi-daemon`. The factory image has no compiler and no cmake, which llama.cpp needs.
3. **Python environment of the application.** `venv/` with the exact versions listed in `requirements.txt`. An environment that is broken or copied from elsewhere is made again.
4. **Speech synthesis.** A separate environment, `piper-venv/`, with `piper-tts` 1.8.0 and Flask. Piper is GPL-3.0 and runs as its own program: the application talks to it over HTTP on the loopback interface and never imports it.
5. **Models.** Downloaded into `models/` and checked against the SHA-256 sums in `scripts/models.sha256`: the Piper voices `it_IT-serena-medium` (at a fixed revision) and `en_US-ljspeech-medium`, the Vosk models `vosk-model-small-it-0.22` and `vosk-model-small-en-us-0.15`, YOLOX-Nano (`yolox_nano.onnx`) and, unless `--no-llm`, `qwen2.5-0.5b-instruct-q4_k_m.gguf`. A file already present with the right checksum is not downloaded again.
6. **llama.cpp.** Fetches llama.cpp at the commit tested on the UNO Q (`74a7c897`) and builds `llama-server` (about twenty minutes). Skipped when the same commit is already built, or with `--no-llm`.
7. **Microcontroller firmware.** Installs the core `arduino:zephyr` 1.0.0 and the library `Arduino_RouterBridge` 0.4.3, compiles `firmware/domotiq_mcu` in the "Immediate" start mode (`wait_linux_boot=no`) and loads it with the local `remoteocd`, which needs no password. It is reloaded only when the sketch, the core, the library or the board options change. Finally `arduino-app-cli properties set default none` makes sure no App Lab app replaces the firmware at boot. See `firmware/domotiq_mcu/README.md` to do the same by hand.
8. **House settings.** Sets the host name `casaN` and the time zone Europe/Rome; creates the staff PIN (if none exists yet) and the Wi-Fi password (if none exists yet); writes house number, names and network into `var/config/settings.json`.
9. **Services.** Installs `domotiq`, `domotiq-tts` and `domotiq-llm` in `/etc/systemd/system`, a `sudoers` rule, and a journald limit (200 MB, 7 days of logs). It disables the automatic `apt` timers and holds `alsa-ucm-conf`, `libasound2t64` and the running kernel: nothing should update the system at a fair.
10. **Hotspot.** Creates or updates the hotspot profile, then applies `--hotspot` (`now`, `boot` or `no`).
11. **Start.** Restarts the services and prints a summary.

The summary looks like this (password and PIN are chosen at random for each house):

```
DomotiQ casa1 is installed.
  Wi-Fi:    DomotiQ-Casa1   password: abcd-efgh-jkmn
  Address:  http://10.42.1.1/   (on the hotspot)   http://casa1.local/
  Staff PIN: 1234   (write it down: it is not shown again)
  Sign to print: http://10.42.1.1/sign
```

The Wi-Fi password is three groups of four characters, from an alphabet without the easily confused `i`, `l`, `o`, `0` and `1`. Write the password and the PIN on the printed [staff quick guide](quick-guide-staff.md); the PIN line appears only when the installer has just chosen a new PIN.

## Where things live

Everything is inside `/home/arduino/domotiq`:

| Path | Content |
|---|---|
| `venv/` | Python environment of the application |
| `piper-venv/` | separate environment of Piper |
| `models/` | Piper voices, Vosk models, YOLOX-Nano, Qwen2.5-0.5B |
| `llama.cpp/` | llama.cpp sources and the built `llama-server` |
| `var/config/` | `settings.json`, `rules.json`, `identities.json` |
| `var/calibration/` | camera calibration, empty-house reference, locked camera settings |
| `var/photos/` | photos of the characters |
| `var/domotiq.db` | SQLite: events (7 days), positions (24 hours), change log, bin |
| `var/dataset/`, `var/recordings/` | staff captures and recorded sequences |
| `var/firmware/` | the last firmware build |

`var/` is what the house remembers. It is never copied between houses and is excluded from the repository.

## The three services

| Service | What it runs |
|---|---|
| `domotiq` | The application (`python -m domotiq`): web app on port 80, rules, voice, audio, the link to the microcontroller, with the vision as a child process. Restarts by itself. It may bind port 80 and set the clock, nothing else. |
| `domotiq-tts` | Piper's HTTP server on `127.0.0.1:5010`, with the voices in `models/piper`. |
| `domotiq-llm` | `llama-server` with Qwen2.5-0.5B-Instruct on `127.0.0.1:8081`, always loaded so free questions get a fast answer, at a lower CPU priority than vision and voice. Not enabled with `--no-llm`. |

`domotiq` starts after `arduino-router` (the system service that links Linux and the microcontroller) and after `domotiq-tts`. All three restart automatically if they stop, and all three start at boot: after a reboot the house comes up by itself.

Useful commands:

```bash
systemctl status domotiq domotiq-tts domotiq-llm --no-pager
journalctl -u domotiq -f                 # follow the application log
sudo systemctl restart domotiq           # restart the application
```

The staff pages of the web app can also restart the application, reboot or power off the board (see [chapter 6](06-web-app.md#settings)).

## The hotspot

At the fair each house has its own Wi-Fi network, served by the board with NetworkManager in shared mode:

| | House 1 | House 2 |
|---|---|---|
| SSID | `DomotiQ-Casa1` | `DomotiQ-Casa2` |
| Security | WPA2, random password chosen by the installer | same |
| Band and channel | 2.4 GHz, channel 1 | 2.4 GHz, channel 11 |
| Address of the house | `10.42.1.1` | `10.42.2.1` |
| Names | `casa1.lan`, `casa1.local` | `casa2.lan`, `casa2.local` |

The DNS of the hotspot answers for `casaN.lan` (and `domotiq.lan`), and it makes the iCloud Private Relay names fail at once, so iPhones do not wait for them. There is no captive portal on purpose: the captive-portal window of phones does not allow the camera, and on iPhone it closes when you switch app. Phones join by scanning the QR code of the sign and open the numeric address, which always works.

The board is either on the lab Wi-Fi or on its hotspot. Switching to the hotspot drops the lab connection, and your SSH session with it.

The installer option chooses the starting point:

- `--hotspot boot` (default): the hotspot starts by itself at every boot. The other Wi-Fi profiles stop connecting automatically, so they do not compete with it at boot.
- `--hotspot now`: switch to the hotspot immediately.
- `--hotspot no`: configure it but leave the board on the lab Wi-Fi.

Later you can switch with `scripts/hotspot.sh`:

```bash
bash scripts/hotspot.sh on        # switch to the hotspot now (Wi-Fi client connections drop)
bash scripts/hotspot.sh off       # back to the Wi-Fi of the lab
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

**From a PC, without internet on the board** (for example over the hotspot at the fair). From the folder of the repository on the PC:

```bash
bash scripts/release.sh casa1              # copy code, web app and data, restart domotiq
bash scripts/release.sh casa1 --install    # then run install.sh on the board (needs internet on the board)
```

`release.sh` copies the working tree of the PC to `~/domotiq` on the board with `rsync` over SSH (the `casa1` alias from `add-pc.sh`), then restarts `domotiq`. It leaves out what git ignores and what belongs to the board: `.git`, `venv`, `piper-venv`, `models`, `var` and `llama.cpp`. The board does not need git for this. The copy mirrors the PC: a code file changed only on the board is overwritten or removed.

Without `--install`, a change to the firmware is copied but not loaded on the microcontroller, and new Python packages or models are not installed: use `--install` (or `install.sh` on the board) when those change.

## Installing the second house

The second house is installed exactly like the first, with its own number. The staff PIN is meant to be the same in both houses, so pass the PIN of house 1:

```bash
cd ~/domotiq && bash scripts/install.sh --house 2 --pin 1234
```

House 2 gets the host name `casa2`, the network `DomotiQ-Casa2` on channel 11 and the address `10.42.2.1`, so the two houses can stand next to each other.

The two houses are independent. The camera calibration belongs to each house and is never copied (a backup does not even contain it), and characters are registered on each house. Rules and settings can be copied with a backup from the staff settings of house 1 (see [chapter 6](06-web-app.md#settings)); a backup never carries the network, the house name, the PIN or the camera settings. A restore from the web app replaces rules, characters and settings together, so restore the backup on house 2 before registering its characters.

## Before the house leaves the lab

1. From every PC that must keep access, run `bash scripts/add-pc.sh casaN` once (it copies a key to the board).
2. On the board, allow only keys for SSH:

   ```bash
   cd ~/domotiq && bash scripts/lockdown.sh
   ```

   It lists the keys that will still get in and refuses to run if there are none; `bash scripts/lockdown.sh --undo` allows passwords again. `sudo` keeps asking for the password of the user `arduino`, except for the few commands the web app needs (restart, reboot, power off, hotspot).
3. Switch the hotspot on at every boot (`bash scripts/hotspot.sh boot`, then reboot) and print the sign from `/sign`.
4. Write the Wi-Fi password and the staff PIN on the stand's copy of the [quick guide](quick-guide-staff.md), never in the repository.

Both can be changed at any time from **More → Settings** in the web app (staff), or on the board:

```bash
cd ~/domotiq
venv/bin/python -m domotiq.admin pin 4821
venv/bin/python -m domotiq.admin wifi "a-new-password"
```

The command restarts the house so it reads the new values; a new Wi-Fi password also restarts the hotspot if it is on.

Next: [print and assemble](03-print-and-assemble.md).
