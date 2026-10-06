# 11. Troubleshooting

Each entry gives the symptom, the likely cause and the fix. Two tools help with almost everything:

- **More → Diagnostics** in the web app: the state of board, microcontroller, modules, camera, audio, voice and clock.
- The log of the application, over SSH:

  ```bash
  journalctl -u domotiq -f
  systemctl status domotiq domotiq-tts domotiq-llm --no-pager
  ```

## Board and access

### SSH does not answer on a new board
**Cause.** On a factory image the SSH host keys do not exist (App Lab creates them in its first setup); the log says `sshd: no hostkeys available`.

**Fix.** From an `adb shell`: `sudo ssh-keygen -A` and `sudo systemctl restart ssh`.

### `casa1.local` does not resolve
**Cause.** `avahi-daemon` is off on the factory image. Some phones and PCs do not resolve `.local` names at all.

**Fix.** `sudo systemctl enable --now avahi-daemon` (the installer does it too). On the hotspot, use `http://10.42.N.1/` or `casaN.lan`; the numeric address always works.

### The system update stops on an ALSA dependency
**Cause.** `alsa-ucm-conf : Depends: libasound2t64 (>= 1.2.15)`: the image takes the audio profiles from `trixie-backports`, but not the ALSA library they need.

**Fix.**

```bash
sudo apt-get install -y -t trixie-backports libasound2t64 libasound2-data libatopology2t64 alsa-ucm-conf
arduino-app-cli system update
```

### `arduino-app-cli system update` refuses to run, or stops halfway
**Cause.** It must run as the user `arduino`, not with `sudo` (it calls `sudo apt-get` by itself). Started inside `adb shell`, it stops when the adb session closes.

**Fix.** Run it as `arduino` from an SSH session, or detached with `systemd-run --uid=arduino`.

### SSH drops when the hotspot starts
**Cause.** Expected: the board is either on the lab Wi-Fi or on its hotspot.

**Fix.** Join `DomotiQ-CasaN` from the PC and use `ssh arduino@10.42.N.1` (or `bash scripts/add-pc.sh casaN 10.42.N.1` for an alias). `bash scripts/hotspot.sh off` brings the board back to the lab Wi-Fi.

## Installation and updates

### `install.sh` stops at the checks
- *run this as the user arduino*: log in as `arduino`, not root.
- *at least N MB free are needed*: free space in `/home/arduino` (see `df -h /home/arduino`).
- *no internet*: the first installation downloads packages and models; connect the board to a network with internet.
- *which house is this? use --house 1 or --house 2*: the first run needs `--house`.

### *checksum mismatch* for a model
**Cause.** A download was interrupted or altered.

**Fix.** Run `install.sh` again: a file with a wrong checksum is downloaded again.

### The firmware step fails
**Cause.** *remoteocd or the OpenOCD configuration not found* means the `arduino:zephyr` core is not installed as expected; *loading the firmware failed* means the upload to the microcontroller did not work.

**Fix.** Check that `arduino-cli core list` shows `arduino:zephyr` 1.0.0 and run `install.sh` again. The manual procedure is in `firmware/domotiq_mcu/README.md`.

### After `release.sh` the firmware or new packages did not change
**Cause.** Without `--install`, `release.sh` only copies the files and restarts `domotiq`.

**Fix.** Use `bash scripts/release.sh casaN --install` (the board needs internet), or run `install.sh` on the board.

### Audio broke after a manual system update
**Cause.** The installer holds `alsa-ucm-conf`, `libasound2t64` and the running kernel and disables the automatic updates, so that nothing changes before a fair.

**Fix.** Do not update the system of a house that works. If you did, repeat the ALSA fix above and reboot.

## Microcontroller and modules

### The *Microcontroller* dot is red
**Right after a reboot of Linux** this is normal for about half a minute. The sketch starts at power-up without waiting for Linux (so the barbecue relay is switched off at once after a blackout); when Linux reboots, the router resets the microcontroller as it stops, and the sketch then starts before the new router listens. The house notices that the router answers but the sketch does not, resets the microcontroller once more through its reset line, and the dot turns green, about 70 seconds after the reboot. The log says *the microcontroller does not answer: resetting it*. It tries three times, one minute apart.

**Cause, if it stays red.** Linux cannot talk to the sketch: `arduino-router` is not running, the firmware is not loaded, an App Lab app replaced it at boot, or the firmware speaks another protocol version (the log says *the MCU speaks protocol N, expected 1: reload the firmware*).

**Fix.**

```bash
systemctl status arduino-router --no-pager
arduino-app-cli properties set default none
cd ~/domotiq && bash scripts/install.sh
```

The installer (which needs internet) reloads the firmware when needed; without internet, follow the manual build and upload in `firmware/domotiq_mcu/README.md`. Without the microcontroller the house keeps working and the web app shows the lights on the plan only.

### All lights breathe dimly and do not react
**Cause.** The microcontroller is waiting for Linux: the board is still booting, or the application has been silent for 30 seconds (it stopped or crashed). In this state the relay is off.

**Fix.** Wait for the boot to finish. An application that crashes starts again after 2 seconds; one that hangs is restarted by systemd after 2 minutes. When it talks to the microcontroller again, the house sends it lights and LEDs by itself. If they still breathe after 3 minutes, check `systemctl status domotiq`.

### A module is red in *Diagnostics*
**Cause.** A loose Qwiic cable, the module on the wrong Hub channel, or a module that does not answer.

**Fix.** Run **I2C scan** and compare with the table in [chapter 5](05-testing.md#3-microcontroller-and-modules). Each Hub channel must show the addresses of its modules: 0x36 for a Pixels, 0x44 for a Thermo, 0x3E for the Buttons. The Latch Relay may be at 0x02, 0x15 or 0x10 and the Hub anywhere between 0x70 and 0x77: both are fine. A module plugged in again shows up within 5 seconds.

### Every module is red and the alert "The Modulino bus is stuck" is shown
**Cause.** One of the two lines of the Qwiic bus (SCL or SDA) is held low, and while it is no module can answer. It is almost always a cable with reversed wires: 4-pin JST-SH cables are also sold in a "reverse" version (pin 1 wired to pin 4), which on Qwiic puts the ground of a module on a data line. On the main run (UNO Q → Hub → Relay) it stops everything at once; on a Hub channel it stops the bus as soon as the firmware opens that channel. A typical sign: the green power LEDs of the modules after that cable stay off or dim. More rarely it is a damaged connector.

**Fix.** Unplug the power and check the cables: hold the two connectors of the same cable side by side, turned the same way; on a proper Qwiic cable the wire colours are in the same order on both. With wires all of one colour use a continuity tester: the leftmost pin of one connector must beep with the leftmost pin of the other. If the cables are right, with the house on unplug the cables from the Hub one at a time: the alert goes away within 5 seconds of removing the faulty one. The line above the modules in *Diagnostics* and `scripts/bench_mcu.py` show the state of SCL and SDA.

### The house says the thermostat or the sensor is not answering
**Cause.** No reading from that Thermo (channel 6 for the sideboard, channel 4 for the bathroom).

**Fix.** Check the module in *Diagnostics* and its cable.

### The buttons do the wrong thing
**Cause.** The Buttons module is mounted the other way round.

**Fix.** **Settings → Buttons mounted upside down**.

## Lights, relay and fan

### Lights are dimmer than expected, and get dimmer with more rooms on
**Cause.** The firmware protects the 3.3 V line of the Qwiic connector: brightness is capped at 30 % and all lights are scaled down when the estimated current goes above 450 mA.

**Fix.** This is intended. The values can be raised in **Settings** (*Maximum brightness (%)*, *Pixels current limit (mA)*), but the connector is rated 1 A and the regulator of the board is shared: test at the new values for 10 minutes before using them (see [chapter 4](04-wiring.md#power-of-the-pixels)).

### A light switched on from the phone went off by itself
**Cause.** Manual lights last two minutes, then the room goes back to the house (follow-me lights, scene, rules).

**Fix.** Normal behaviour; use a rule for a light that must stay.

### The fan does not start
**Cause.** The barbecue is resting (30 seconds after the previous one: "The barbecue is already on, or cooling down."), the Latch Relay is missing, or the fan is not on the normally open contact.

**Fix.** Check the relay in *Diagnostics* and the wiring in [chapter 4](04-wiring.md#relay-and-fan).

### The fan ran after a power cut
**Cause.** The latching relay keeps its position without power; the firmware switches it off at power-up only if it was built in the "Immediate" mode.

**Fix.** Load the firmware with `install.sh`, which builds it with `wait_linux_boot=no`.

## Camera and recognition

### Banner *The webcam has moved: calibrate again*
**Cause.** The walls in the image no longer match the empty house: the pole or the camera was bumped.

**Fix.** Repeat the calibration ([chapter 5](05-testing.md#9-camera-calibration)).

### The *Webcam* dot is red, or *The webcam is not connected.*
**Cause.** The C270 is unplugged or not found.

**Fix.** Check the USB cable and `ls /dev/v4l/by-id/`. If the house picks the wrong camera, write the `by-id` path in `var/config/settings.json` under `"camera": {"device": "…"}` and restart `domotiq`.

### The live view shows a drawing marked *SIMULAZIONE - SIMULATION*
**Cause.** The simulation is on: the house ignores the webcam.

**Fix.** **More → Simulation** and switch it off.

### Nothing is recognized, or *Diagnostics* says *not calibrated*
**Cause.** The corners or the empty house are missing.

**Fix.** Calibrate ([chapter 5](05-testing.md#9-camera-calibration)).

### Banner *The webcam sees almost nothing*
**Cause.** For more than five seconds the picture has been below a third of the brightness of the empty house: the hall is too dark (on casa1 in the evening, with the room light off, the camera reached 9-17 out of 50 even at the highest gain) or something covers the camera.

**Fix.** Turn on a light, or remove what covers the camera. Meanwhile the characters stay where they were and the house learns nothing from that picture. When the light comes back, the house adapts by itself.

### Banner *The webcam sees the whole house changed*
**Cause.** For more than five seconds, more than a third of the house looks different from the empty house: the hall light changed a lot, something covers the camera, or the camera was knocked.

**Fix.** Check the camera and its view; then, with the house empty, **More → Calibration → Set the light and save the empty house** (or **Save the empty house only**). The banner goes away by itself when the view is normal again.

### Ghost objects appear, or real ones are missed, after the hall light changed
**Cause.** The locked exposure and the empty-house reference no longer fit the light of the hall.

**Fix.** Usually the house copes by itself. It notices the change of light and keeps the characters as they were just before. If needed it sets the camera again at once, without losing the calibration. Then it learns the empty house again in the new light, except around the characters. In *Diagnostics* the adaptations counter goes up by one. If that is not enough, empty the house and tap **Set the light and save the empty house**.

### The house does not notice the characters I put down
**Cause.** The house thinks a hand is over the house and waits for it to leave (*Diagnostics* shows a hand even when nobody touches the house). It happens when something big lies on the edge of the base: a module, a cable, a visitor's arm.

**Fix.** Remove or fix down what is on the edge. A "hand" still for 8 seconds is taken as an object anyway and becomes part of the empty house; a character put down meanwhile appears 2 seconds later.

### Animals or objects that are not there, mostly on the driveway
**Cause.** The arms of the players move loose modules or cables, and every move is a real change from the empty house.

**Fix.** Mount the totem and run the cables along the walls, then with the house empty **More → Calibration → Save the empty house only**.

### The house asks about somebody who is not there
**Cause.** Something a hand moved or left behind (a shadow, a reflection, a cable) passed the double check of the house.

**Fix.** Answer "there's nobody" (or "that's my hand", "it's a shadow"), or tap **Nothing there** on a phone. The house forgets what it saw, nothing is born there for 30 seconds, and for two minutes it is stricter in that room. If it keeps happening in the same spot, look at the live view: it may be a module, an LED or a cable to fix down or cover.

### The web app says *The webcam is not connected*
**Cause.** For a few seconds the house received no pictures: a restart, a USB reset of the C270 (it happens at every opening, and when the desktop session of the board probes it, for instance at every ssh login).

**Fix.** The line goes away by itself when the pictures are back. If it stays, check the webcam cable and *Diagnostics*; turning off the desktop of the board avoids the resets caused by ssh logins.

### Ghost objects where a piece of furniture was moved
**Cause.** Furniture is part of the empty house.

**Fix.** Put it back, or empty the house and tap **Save the empty house only**.

### A figurine is not seen, or keeps disappearing
**Cause.** Its colour is too close to the floor, the walls or the lawns; or it stands where the vision does not look: under a wall light, under the tree canopy, next to the pole, on a wall top, outside the base.

**Fix.** Move it to a clearer spot, or use a figurine of another colour. The registration warns about these cases.

### A known character is taken for a newcomer
**Cause.** Seen now, its colour differs from when it was registered: another light, the character lying down, on a coloured background. The house still recognizes it if it looks much more like it than like anybody else.

**Fix.** Answer the question with its name: the house assigns it and updates its colours at once, so next time it recognizes it by itself. If that character is already in sight somewhere else in the house, the house concludes the newcomer was not there.

### A character has a **?**, or the house keeps asking who is who
**Cause.** Two figurines of similar colour, picked up together or touching: the house cannot tell them apart by colour.

**Fix.** Answer the question on a phone or by voice. Different colours avoid it.

### A figurine lost its name after being held in the hand
**Cause.** It was held for more than 60 seconds, so the house stopped following it.

**Fix.** Put it down: it is recognized again by its colour, or the house asks.

### The blurred area does not match the bathroom
**Cause.** The camera is not calibrated yet: until then the house blurs a wide area where the bathroom should be if the camera is mounted as designed. If the pole or the camera cradle is turned, that area is in the wrong place.

**Fix.** Calibrate before the house is open to visitors: from then on the blur follows the real bathroom.

## Audio and voice

### The *Audio* dot is red, or the house is silent
**Cause.** The USB sound card is missing or not found, the volume is at 0, the house is set to *Silent*, or the speech synthesis service is down.

**Fix.** Check `aplay -l` for a USB audio card, **Controls → Volume** and **Talkativeness**, and `systemctl status domotiq-tts`. The house uses the first USB audio card that can play; to force another device, add `Environment=DOMOTIQ_AUDIO=plughw:CARD=<name>,DEV=0` with `sudo systemctl edit domotiq` and restart it. If the card disappears or resets by itself while running (the US205 sometimes does, and comes back with a low volume), the house notices within a couple of seconds, opens it again and sets the levels back to 0 dB; the audio *restarts* counter in *Diagnostics* goes up by one. If it happens often, check that the card is plugged in firmly and power the speakers from another USB socket. Without any sound card, the house still writes what it would say as subtitles.

### The first English sentence is slow
**Cause.** The English voice is loaded at its first use.

**Fix.** Normal; the house prepares its frequent sentences at start-up.

### The house does not hear anything
**Cause.** The lavalier is not in the microphone input of the US205, or it is too far from the speaker's mouth.

**Fix.** **Diagnostics → Microphone test (3 s)**: a level near zero means no signal. Check the plug, and speak close to the totem cap while holding **Talk** for the whole sentence.

### "I didn't get that." for sentences that should work
**Cause.** A misheard sentence, or the language model is not available.

**Fix.** Check that the house language is the one being spoken (Language LED on = English). **Diagnostics → Voice** shows *LLM* with a green dot when the language model answers; otherwise `systemctl status domotiq-llm`. Installed with `--no-llm`, the house understands only its fixed phrases.

### A name is never recognized by voice
**Cause.** The speech recognition model does not know the words of the name.

**Fix.** Choose a common name, or fill in **English pronunciation (optional)** in the character's card for the English recognizer.

## Phones and hotspot

### A phone joins the Wi-Fi but the page does not open
**Cause.** The hotspot has no internet, and the phone sends the traffic through mobile data instead (typical on Android), or it waits for the network to prove it is online.

**Fix.** When the phone asks, choose *Stay connected* or *Use without Internet*. On Android, turn mobile data off for a moment. Open `http://10.42.N.1/` exactly, with `http://`.

### The hotspot `DomotiQ-CasaN` is not visible
**Cause.** The board is still on the lab Wi-Fi, or the hotspot did not start.

**Fix.** `bash scripts/hotspot.sh status`, then `bash scripts/hotspot.sh on`; `bash scripts/hotspot.sh boot` makes it start at every boot. It is a 2.4 GHz network.

### *Lost the connection with the house: retrying…*
**Cause.** The phone left the Wi-Fi range, or the board is restarting.

**Fix.** Wait: the web app reconnects by itself.

## Clock

### The house asks "I don't know the time: what time is it now?"
**Cause.** The board has no battery for its clock and no internet at the fair, and no phone has opened the web app since the start.

**Fix.** Answer at once aloud, with no button ("it's half past three"), open the web app from a phone (it sets the time), or use **Settings → Use this phone's time** ([chapter 8](08-voice.md#setting-the-clock-by-voice)). **Diagnostics → Clock** shows where the time came from. Rules with *it is a given time* need a known time.

## Web app and alarm

### An alarm goes off and nobody is there
**Cause.** The alarm rules count only sure presences: a character the house knows, or something still and clearly visible for at least 6 seconds. If it goes off anyway, the house really sees something in that spot: an LED, a reflection, a module lying there.

**Fix.** **Switch off** the alarm from the red notice or from the box on the **House** page: the alarm rules stay quiet until you switch it on again. Then answer "there's nobody" to the question of the house, if there is one, and look at what is in that spot (**Live**, with **Names and rooms**); if it is a fixed object, remove it or fix it down and save the empty house.

### The alarm no longer goes off
**Cause.** It is switched off: the **Alarm** box on the **House** page says *Off*.

**Fix.** Tap **Switch on**.

## Rules and characters

### A rule does not fire
**Cause.** It is disabled; its pause between two runs is not over; a condition is false; the *Who* field excludes what moved (the default rules count people only, not pets); a time rule with an unknown clock.

**Fix.** Check the rule in the editor and **Events** for what the house saw.

### A rule or a character was deleted by mistake
**Fix.** **Settings → Bin → Restore**, within 24 hours. A restored character whose name was taken in the meantime gets " 2" after its name. **Settings → Default rules** brings back the original rules (it replaces all the current ones).

### *The name Marco is already used*
**Cause.** Names are unique in the house, regardless of case, English pronunciations included.

**Fix.** Add a surname or a nickname.

### *I didn't find anything new. Try again.*
**Cause.** During the registration no unknown figurine appeared within two and a half minutes, or it was too close to something else.

**Fix.** Put the figurine on a free spot of the floor, away from walls and furniture, and start again.

### The party does not start
**Cause.** A party is running, or the 30-second pause after the last one is not over (*Already running or resting, try again in a moment*).

**Fix.** Wait a moment.
