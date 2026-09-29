# 5. Testing and commissioning

Go through this chapter on every house after assembly and wiring, and again before each fair. Each step says what to do and what you should see. When something does not match, the [troubleshooting](11-troubleshooting.md) chapter has the likely causes.

You need the staff PIN printed by the installer, and a phone or PC connected to the same network as the board: the lab Wi-Fi (`http://casa1.local/`) or the hotspot of the house (`http://10.42.1.1/`).

## 1. Power on

Switch on the power supply. What happens:

1. The microcontroller starts at once: relay off, lights off, then a dim **breathing** light in every room while Linux boots (about 40 seconds).
2. When the application is up, it takes over the lights: with nobody in the house they go off.

Check the services from an SSH session:

```bash
systemctl status domotiq domotiq-tts domotiq-llm --no-pager
journalctl -u domotiq -f
```

## 2. Open the web app and log in as staff

Open the address of the house in a browser. At the top right, next to the house name, three dots show the state of the **Microcontroller**, the **Webcam** and the **Audio** (green = working). Go to **More**, type the PIN under *Staff PIN* and tap **Staff login**. The staff pages (**Calibration**, **Diagnostics**, **Settings**) are now open on this phone for 12 hours.

## 3. Microcontroller and modules

Open **More → Diagnostics**.

- The **Modulino** card shows a green dot and `v1`, the protocol version of the firmware. A red dot means Linux cannot talk to the microcontroller.
- Below it, every module has a green or red dot: Hub, Latch Relay, the five Pixels (garage, bedroom, kitchen, living room, bathroom), the two Thermo (bathroom, sideboard), Buttons and Distance.
- **I2C scan** lists the addresses that answer on each Hub channel. Expected, besides the Hub (0x70–0x77) and the Latch Relay (0x02, 0x15 or 0x10), which sit on the main bus and answer on every channel:

  | Channel | Expected |
  |---|---|
  | ch0, ch1, ch2, ch3, ch5 | 0x36 (Pixels) |
  | ch4 | 0x44 (Thermo) |
  | ch6 | 0x44, 0x3e, 0x29 (Thermo, Buttons, Distance) |
  | ch7 | nothing |

## 4. Lights

In **Controls → Lights**, choose a room, a colour and **On**; repeat for all five rooms, then choose *All rooms* and **Automatic** to give the lights back to the house. A light switched on by hand stays on for two minutes; **Off** keeps a room dark for one minute.

## 5. Buttons, LEDs and the Distance sensor

- **Language**: all lights flash green (Italian) or red (English) for about a second, the house says "Italiano" or "English", and the LED of the Language button is on while the house speaks English. Press it again to go back to Italian.
- **Talk**: hold it. A beep, its LED lights up while the house listens, another beep when you release it.
- **Intercom**: a doorbell rings and the house asks "Chi è?" / "Who is it?"; its LED blinks during the conversation. Say nothing twice and the house lets you in as a guest.
- **Distance**: keep a hand less than 30 cm from the front of the totem for 2 seconds. The **House** screen shows *Someone at the doorbell*.

## 6. Thermostat and bathroom

On the **House** screen the cards show the thermostat temperature and humidity and the bathroom humidity.

- Put a finger on the Thermo of the sideboard: the temperature rises slowly, because the sensor board has thermal inertia. Breathing on it is faster: humidity jumps, the thermostat goes to **hot**, the house says "It's hot! Turning on the air conditioning." and a cool blue wave runs in every room for up to two minutes, or until the reading settles back.
- Breathe on the bathroom Thermo: when humidity rises 8 points above its recent average the shower rule starts ("Turning on the bathroom fan.", cool light in the bathroom, notification *Shower running*).

The thresholds are relative to the average of the last 5 minutes, so give the sensors a few minutes after power-up.

## 7. Barbecue fan

In **Controls**, tap **Barbecue**. The house says "Lighting the barbecue!", the fan runs for 20 seconds, then "The barbecue is ready, everyone to the garden!". **Stop the barbecue** stops it at once.

Then test a power cut: start the barbecue and unplug the power while the fan runs. When power comes back, the fan must stay off.

## 8. Sound and microphone

In **Diagnostics**:

- **Audio test** plays a chime and says "Audio test: can you hear me?". The speaker knob must be at maximum; set the level with **Controls → Volume**.
- **Microphone test (3 s)** records three seconds: speak towards the totem cap. The result shows the level, the peak and the text recognized. A level close to zero means no sound reaches the microphone input.

## 9. Camera calibration

The calibration tells the house where the base is in the image. Until it is done the house sees nothing, and the blur of the bathroom in the live view is only approximate (see [chapter 7](07-recognition-and-identities.md#privacy)): calibrate before the house is open to visitors.

Open **More → Calibration**.

1. **Take characters and car out of the house (furniture stays).** Leave the furniture exactly where it will stay.
2. **Tap the 4 corners of the base, in the order shown**: front left, front right, back right, back left. Front is the driveway edge; left is the kitchen and garden side. A chip shows which corner is next; ↶ removes the last one. Tap **Use these corners**. If the four points are not a plausible outline of the base, the house refuses them: tap them again, in order.
3. **Check the overlay.** With *Overlay* on, the image shows the outline of the base, the rooms, the doors in green, the walls drawn at their real height and the excluded zones darkened (wall lights, the tree canopy, the pole). The drawn walls must sit on the walls in the image. If they do not, tap the corners again.
4. **Adjust the camera and save the empty house.** The first time, tap **Adjust to the light again**: the camera finds exposure and white balance on its own for 3 seconds, the house locks them with 25 % less exposure (so the floor under the coloured house lights does not saturate) and then saves the empty house, the median of 20 frames. The house must be empty for this.

Later:

- **Save the empty house** takes a new reference without touching the camera settings, for example after moving a piece of furniture.
- **Adjust to the light again** is for when the light of the hall changes a lot. Slow changes are followed automatically on the free floor.
- If the camera gets bumped, the web app shows *The webcam has moved: calibrate again*: repeat the whole procedure.

**Diagnostics → Webcam** now shows the frame rate (about 10 per second) and the processing time, without *not calibrated*.

## 10. The first figurine

1. **More → Characters and objects → + Add.** Type a name, optionally take a photo, tap **Next**.
2. Put the figurine on a free spot of the house. The house finds it and asks what it is, proposing a kind; tap the right one and **Save**.
3. On the **House** screen the figurine appears with its name. Move it into another room: that room's light turns on, and turns off 3 seconds after the room is empty.
4. Pick it up with your hand and put it down in another room: it keeps its name.

[Chapter 7](07-recognition-and-identities.md) explains the registration and its warnings in detail.

## 11. Voice

Hold **Talk** and ask, in Italian, "Dov'è Marco?" (with the name you registered); release and wait for the answer. Switch to English with the Language button and ask "Where is Marco?".

Then ask something the fixed phrases do not cover, such as "Quanta gente c'è in cucina?". The house says "Vediamo…" / "Let me see…" and passes the sentence to the language model. **Diagnostics → Voice** shows *LLM* with a green dot when the language model server is available.

## 12. Intercom and rules

- Press **Intercom**, say the name of the registered character, and within 60 seconds move that figurine from the driveway through the front door into the living room: it takes that name.
- Put two person figurines in the bathroom: after 2 seconds the bathroom blinks orange and the house says "The bathroom is taken! Please wait your turn."
- Leave a person figurine in the utility room for more than 5 seconds: red alarm lights in living room and garage, "Warning: the utility room is off limits!", and a red banner on the phones until it leaves.
- Drive the car through the garage gate: "Welcome home!" and the garage light. Leave it still in the parking area for 3 seconds: it counts as parked and the garage light goes off 10 seconds later.
- **Controls → Party!**: "Let's dance!", 20 seconds of music and lights, "The party is over!".

## 13. Hotspot and phones

1. Switch the board to its hotspot (`bash scripts/hotspot.sh on`, or reboot if you installed with the default `--hotspot boot`).
2. Print the sign: **More → Printable sign** (or `http://10.42.N.1/sign`), A4 portrait.
3. With an Android phone and an iPhone: scan QR code 1 to join `DomotiQ-CasaN`, then QR code 2 to open the house. If the phone asks, choose *Stay connected* or *Use without Internet*. On Android, if the page does not open, turn mobile data off for a moment.
4. **Diagnostics → Wi-Fi** shows how many devices are connected to the hotspot. Open **Live** on several phones at the same time to check that the stream keeps up.

## 14. Clock

The UNO Q has no battery for its clock and there is no internet at a fair. After a restart, the first phone that opens the web app sets the time of the house (a message says *House time set from this phone*). **Diagnostics → Clock** shows where the time came from. See [chapter 8](08-voice.md#setting-the-clock-by-voice) for setting it by voice.

## Testing without figurines

**More → Simulation** (switching it on needs the staff PIN) replaces the webcam with virtual characters you drag on the plan, plus virtual sensors and buttons. Lights, voice and rules react as they do to real figurines. The switch *Real lights and voice muted* keeps the real house quiet while you try things. Remember to switch the simulation off: while it is on, the house ignores the webcam.

Next: [the web app](06-web-app.md).
