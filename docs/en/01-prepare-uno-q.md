# 1. Prepare the UNO Q

A factory-new Arduino UNO Q needs a few steps before DomotiQ can be installed: a password for the `arduino` user, a name, a network connection, working SSH, a system update and key-based access from your PC. This chapter goes through them in order, with notes on the surprises you may meet.

Throughout this guide the board is called `casa1` and the password of the `arduino` user is `domotiq2026`. If you choose others, use yours instead.

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

On the factory image the `arduino` user has no password: the first `sudo` command asks for one. Run:

```bash
sudo -v
```

When the board asks for the new password, type `domotiq2026`. This password is the one `sudo`, SSH and `scripts/add-pc.sh` will ask for.

## 3. Name and time zone

Give the board the name `casa1` and the time zone. The installer sets both again later, but the name is needed now for `casa1.local` to work.

```bash
sudo hostnamectl set-hostname casa1
sudo timedatectl set-timezone Europe/Rome
```

## 4. Connect to the Wi-Fi

While you prepare it, the board sits on your normal Wi-Fi network, the same as the PC. With NetworkManager:

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

With the board on the same network as the PC, from the folder of the repository on the PC:

```bash
bash scripts/add-pc.sh casa1
```

If the board is already on its own hotspot (after the installation) and the PC is on the `DomotiQ-Casa1` network, add the address of the house:

```bash
bash scripts/add-pc.sh casa1 10.42.1.1
```

The script:

1. creates the key `~/.ssh/id_ed25519_domotiq` if this PC does not have it yet;
2. copies it to the board with `ssh-copy-id`, which asks the password of `arduino` (`domotiq2026`) once and, the first time, whether to trust the board: answer `yes`;
3. adds a `Host casa1` entry to `~/.ssh/config` (user `arduino`, that key, and the address you gave, or `casa1.local`);
4. connects once and prints `connected to casa1`.

From now on `ssh casa1` logs in without a password. The entry is added only if `~/.ssh/config` does not already contain `Host casa1`: if it has one with another address the script says so, and you change it by editing that file.

**A new board with a name already used.** Every board has its own identity, made at its first start, and the PC remembers the one of every name. If the PC already knew a `casa1` (a reinstalled board, or another one), the script says so and asks whether to forget the old identity: answer `y`. Without the script, `ssh` refuses with *REMOTE HOST IDENTIFICATION HAS CHANGED*; the fix is the same:

```bash
ssh-keygen -R casa1.local
```

If the board does not answer, the script prints the network error and reminds you which form to use. Run the same script on every other PC that needs to reach the house. App Lab in network mode is an alternative way in.

## 8. Update the system

Log in with `ssh casa1` and run the update **as the `arduino` user, without `sudo`**:

```bash
arduino-app-cli system update
```

`arduino-app-cli` refuses to run as root and calls `sudo apt-get` by itself.

Run it from an SSH session. Inside an `adb shell` the update stops if the adb session closes; if you have no other choice, start it detached with `systemd-run --uid=arduino`.

While this project was prepared, the update brought `arduino-app-cli` 0.13.0, `arduino-cli` 1.5.1, the Linux kernel 7.0 and the microcontroller core `arduino:zephyr` 1.0.0, which is the version DomotiQ uses. Reboot when it is done, so the new kernel is in use:

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

On the board used for the project the system partition had about 2 GB free out of 9.8 GB, while `/home/arduino` is a separate partition with about 15 GB free. DomotiQ lives in `/home/arduino/domotiq`, so the home partition is the one that matters:

```bash
df -h /home/arduino
```

A first installation needs about 2.3 GB there; the installer checks it before starting.

## Before others use the house

The password `domotiq2026` is written in this guide, so whoever reads it knows it. Before other people can join the network of the house:

- allow SSH with a key only: `bash scripts/lockdown.sh` on the board, after making sure your key works (see [Before the house leaves the lab](02-install.md#before-the-house-leaves-the-lab));
- if you like, choose another password for `arduino` with `passwd`;
- if you gave the `arduino` user password-less `sudo` during development, give `sudo` its password back (the small rule installed by DomotiQ, which only allows restarting its services, rebooting or powering off the board and changing the hotspot, can stay).

Next: [install the software](02-install.md).
