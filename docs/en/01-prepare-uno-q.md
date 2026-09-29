# 1. Prepare the UNO Q

A factory-new Arduino UNO Q needs a few steps before DomotiQ can be installed: a password for the `arduino` user, a name, a network connection, working SSH, a system update and key-based access from your PC. This chapter follows the way the first house (`casa1`) was prepared, with notes on the surprises found along the way.

You can do the first setup with Arduino App Lab (it sets name, password and Wi-Fi, and it also prepares SSH and the `.local` name) or by hand from a shell. The steps below are the manual way; if you used App Lab, skip to [SSH key access from a PC](#7-ssh-key-access-from-a-pc) and check the SSH and avahi sections if something does not work.

## What you need

- An Arduino UNO Q 4GB. DomotiQ is tested on the factory image of 10 December 2025 (Debian 13 "trixie"), updated as described below.
- A PC with `adb` (Android platform tools) for the first shell, and a USB-C cable.
- A Wi-Fi network with internet access. The board needs internet for the system update and, once, for the DomotiQ installation.
- On the PC, a copy of the repository (for `scripts/add-pc.sh` and `scripts/release.sh`):

  ```bash
  git clone https://github.com/destone28/DomotiQ
  ```

## 1. Open a shell

Connect the board to the PC with the USB-C cable and open a shell on it:

```bash
adb shell
```

## 2. Set the password of the `arduino` user

On the factory image the `arduino` user has no password. Set one with the first-configuration script of the image:

```bash
/usr/local/bin/arduino-passwd
```

This password is the one `sudo`, SSH and `scripts/add-pc.sh` will ask for.

## 3. Name and time zone

Give the board the name of its house (`casa1` or `casa2`) and the Italian time zone. The installer sets both again later, but the name is needed now for `casa1.local` to work.

```bash
arduino-app-cli system set-name casa1      # or: sudo hostnamectl set-hostname casa1
sudo timedatectl set-timezone Europe/Rome
```

## 4. Connect to the Wi-Fi of the lab

During development the board sits on your normal Wi-Fi network. With NetworkManager:

```bash
sudo nmcli device wifi connect "YOUR-NETWORK" password "YOUR-PASSWORD"
```

## 5. Make SSH work

On a new image SSH does not start: the log says `sshd: no hostkeys available`. App Lab creates the host keys during its first setup; without App Lab, create them yourself:

```bash
sudo ssh-keygen -A
sudo systemctl restart ssh
```

## 6. Turn on avahi (the `.local` name)

`avahi-daemon` is off on the factory image (App Lab switches it on when you use its network mode). Without it, `casa1.local` does not resolve from the PC.

```bash
sudo systemctl enable --now avahi-daemon
```

From the PC, `ping casa1.local` should now answer. The installer also enables avahi, so the name keeps working after the installation.

## 7. SSH key access from a PC

On the PC, from the folder of the repository:

```bash
bash scripts/add-pc.sh casa1              # the board is on the lab network (casa1.local)
bash scripts/add-pc.sh casa1 10.42.1.1    # the board is on its own hotspot
```

The script:

1. creates the key `~/.ssh/id_ed25519_domotiq` if this PC does not have it yet;
2. copies it to the board with `ssh-copy-id` (it asks the password of `arduino` once);
3. adds a `Host casa1` entry to `~/.ssh/config` (user `arduino`, that key, and the address you gave, or `casa1.local`);
4. connects once and prints `connected to casa1`.

From now on `ssh casa1` logs in without a password. The entry is added only if `~/.ssh/config` does not already contain `Host casa1`: to point an existing alias to another address, edit that file.

Run the same script on every other PC that needs to reach the house. App Lab in network mode is an alternative way in.

## 8. Update the system

Log in with `ssh casa1` and run the update **as the `arduino` user, without `sudo`**:

```bash
arduino-app-cli system update
```

`arduino-app-cli` refuses to run as root and calls `sudo apt-get` by itself.

Run it from an SSH session. Inside an `adb shell` the update stops if the adb session closes; if you have no other choice, start it detached with `systemd-run --uid=arduino`.

On `casa1` the update brought `arduino-app-cli` 0.13.0, `arduino-cli` 1.5.1, the Linux kernel 7.0 and the microcontroller core `arduino:zephyr` 1.0.0, which is the version DomotiQ uses. Reboot when it is done, so the new kernel is in use:

```bash
sudo reboot
```

### If the update stops on an ALSA dependency

On the factory image the update can stop with:

```
alsa-ucm-conf : Depends: libasound2t64 (>= 1.2.15)
```

The image takes the audio profiles, the kernel, firmware and mesa from `trixie-backports`, but not the ALSA library that the new audio profiles need. Install the library from backports too, then repeat the update:

```bash
sudo apt-get install -y -t trixie-backports libasound2t64 libasound2-data libatopology2t64 alsa-ucm-conf
arduino-app-cli system update
```

`scripts/install.sh` applies the same fix, so on a board you install later this is handled for you.

## 9. Check the free space

On `casa1` the system partition had about 2 GB free out of 9.8 GB, while `/home/arduino` is a separate partition with about 15 GB free. DomotiQ lives in `/home/arduino/domotiq`, so the home partition is the one that matters:

```bash
df -h /home/arduino
```

A first installation needs about 2.3 GB there; the installer checks it before starting.

## Before the house goes to a fair

When development is over:

- allow SSH login with a key only (for example `PasswordAuthentication no` in a file under `/etc/ssh/sshd_config.d/`, then `sudo systemctl restart ssh`), and make sure your key works first;
- if you gave the `arduino` user password-less `sudo` during development, give `sudo` its password back (the small rule installed by DomotiQ, which only allows restarting its services, rebooting or powering off the board and changing the hotspot, can stay);
- write the Wi-Fi password and the staff PIN on the printed [quick guide for the staff](quick-guide-staff.md), never in the repository.

Next: [install the software](02-install.md).
