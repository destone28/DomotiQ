# 6. The web app

Every house serves its own web app from the board. It needs no internet and nothing to install: any phone browser on the house's Wi-Fi opens it. It is plain HTML, CSS and JavaScript with no external libraries, in Italian and English, with a light and a dark theme that follow the phone. The state of the house arrives in real time over a WebSocket, so what you see changes as soon as something moves in the house.

## Opening it

- **At the fair**: scan the two QR codes of the sign next to the house. The first joins the Wi-Fi `DomotiQ-CasaN`, the second opens `http://10.42.N.1/`. The names `http://casaN.lan/` and `http://casaN.local/` work too, but the numeric address always does.
- **In the lab**: `http://casaN.local/`, with the board on your Wi-Fi.
- Phones can add the page to the home screen; it then opens like an app.
- The first time a phone opens it, the house greets it aloud and a card asks for the name and invites the visitor to add a character (see [chapter 8](08-voice.md#talking-without-pressing-talk)).
- The web app uses plain `http://`. There are no system notifications (they would need HTTPS); photos are taken with the phone's own camera through the normal file picker, which works without HTTPS.

## Who can do what

Anyone on the Wi-Fi of the house can do everything, with no PIN and no login: look, give commands, change rules and characters, answer the questions of the house, calibrate the camera, read the diagnostics, change the settings, download a backup, restart or power off the board. The actions that cannot be undone (restoring a backup, default rules, restart, power off, a new Wi-Fi password) ask *Are you sure?* first.

That is on purpose: this is a house for playing. Every change is recorded with the time, the phone and an optional nickname (**More → Events → Changes**), and deleted rules and characters wait in the bin for 24 hours (**More → Settings → Bin**; see [Rules](09-rules.md#who-can-change-the-rules)).

## What every screen shares

- **Top bar**: the name of the house, three status dots (**Microcontroller**, **Webcam**, **Audio**: green when working, red when not; a fourth dot appears while the simulation is on), and the **IT / EN** button that switches the language of the web app on this phone only. The first time, the web app picks the language of the phone. The language the house speaks is a different setting, in **Controls**.
- **Bottom bar**: **House**, **Live**, **Controls**, **Characters** (characters and objects), **More**. Every page scrolls to its end, above the bar.
- **Every page starts the same way**: the title, one line about what it is for and, right of the title, its main action (**+ Add**, **+ New rule**).
- **Notices at the top**, one colour per kind:
  - **red**: an alarm going off (someone in the utility room), with who and where, the **Switch off** button that turns the alarm off like a burglar alarm, and the **✕**; on the plan the room flashes red;
  - **amber**: a warning (too many people in the bathroom, the camera moved, the light of the camera to be set, the Modulino bus stuck), with the **✕**; on the plan the room is outlined in amber;
  - **grey**: the connection with the house lost (*Lost the connection with the house: retrying…*); the web app reconnects by itself;
  - **white card with a teal edge**: a question of the house (*The house asks*).

  The **✕** closes the notice on every phone: an alarm or a warning comes back only if it ends and happens again; a closed question disappears everywhere and the house stops listening. The files of the web app load under a version that changes with every update: after an update of the house every phone reloads by itself and gets the new version.
- **Questions of the house**: when the house is unsure it asks, for example "Is it Viola or Rosaria in the living room?", with one button per answer and, when more than one name is proposed, **Both** (or **All of them**): two figurines touching are a single blob for the camera. Any phone can answer; the first answer wins and the question disappears everywhere. The house also asks aloud and listens for the answer by itself, with no Talk button. When it asks who a newcomer is there are also **Nothing there**, a field to type a new name, its kind and the **Add** button (see [chapter 7](07-recognition-and-identities.md#a-newcomer)).
- **Subtitles**: everything the house says appears as a subtitle at the bottom of every phone, even when the house is set to *Silent*.
- **Short messages**: they pop up at the bottom, in the same colours as the notices (a character registered, the barbecue is ready, a rule's notification, the alarm switched on or off), and close with a tap. Alarm ones also vibrate the phone, where the browser allows it.
- **Clock**: when the house does not know the time, the first phone that opens the web app sets it (*House time set from this phone*). Once it knows it, visitors' phones no longer touch it (one with a wrong clock would move it for everybody): it is corrected from **More → Settings → Use this phone's time**, or by voice.
- **Nickname**: the first time you change a rule or register a character, the web app asks *What's your name? (optional, shown in the log)*. You can change it in **More → Your nickname**. Each phone also has an automatic identifier.

## House

<img src="../images/screens/en/home.png" alt="House" width="260">

*The house: who is in and what is going on, live.*

**Plan.** The virtual house, drawn from the CAD model, with the driveway, where visitors stand, at the bottom.

- Rooms, walls, doors and furniture; each room light glows in its current colour and effect.
- The two thermometers, the thermostat on the sideboard and the bathroom one, each with the temperature in degrees Celsius and, below, the humidity (*humidity 45%*); a counter for each room with somebody in it.
- Every character with the silhouette of its kind (person, dog, cat, animal, car, object) in its colour and with its name; a **?** marks a character the house is not sure about.
- The car, flames on the barbecue while it is on, rooms with an alarm in red and with a warning in amber.

**How the house is.** Cards with the people inside, **Thermostat** (temperature in °C, *Humidity* in per cent, *Air conditioning on* or *Heating on*), **Bathroom** (temperature in °C, *Humidity*, *Shower running*), **Car** (*just arrived*, *parked*, *just left*, *not here*), **Scene**, and **Party** and **Barbecue** while they are on.

**Who is in.** The list of everything the house sees, with name (or *Guest* for an unknown person, *Unknown* for anything else), kind and room. Tap a character, on the plan or in the list, to open its card: photo or silhouette, kind, room, and *I'm not sure who this is* when in doubt. **Who is it?** (for an unknown one) or **Someone else: change** (for one recognized wrongly) opens the list of every character and object the house knows, with the room each is in now, and below it a new name with its kind. Choosing one already known moves the name there from wherever it was, since a name is never in two places, and the house learns that look of the character even if the light changes it a lot; with a new name the character is registered with the colours the house sees. If the house sees something that is not there (a reflection, a light, a module lying around), **Not really there: remove**, after a confirmation, takes it out of the house at once: the house treats it as a mistake of the camera, forgets that spot and lets nothing be born there for a while.

**Unrecognized item.** Under the plan: tap the button, then the spot on the plan where something stands that the house does not follow (a figurine it did not see being put down, or took for the empty house). Around that spot the house takes back the empty house as it was saved, so what stands there shows again, and it follows it from then on; then it asks who it is, with the same list. If it sees nothing different from the empty house there it says so: move the item a little and try again. With the simulation on, the tap puts a virtual figurine there.

**Alarm.** At the bottom of the page, the alarm box, switched on and off like a burglar alarm:
- **On** (green shield): the alarm rules (utility room off limits, bathroom for one and the ones you make with *Alert*) work;
- **Off** (grey shield): those rules stay quiet, no siren and no warnings; everything else (lights, voice, other rules) goes on as usual;
- **Alarm going off** (red edge): an alarm rule is sounding.

The **Switch off** / **Switch on** button changes it for the whole house, with a beep and a message on every phone (*Alarm off by Marco*). Switching off stops the alarms going off at once, with their lights; switching on again notices whoever is already in a watched place, as if they had just come in. The state survives a restart.

## Live

<img src="../images/screens/en/live.png" alt="Live" width="260">

*Live from the webcam*: the image of the camera, about 5 frames per second. The switch **Names and rooms** writes the name and the room over each character. **Unrecognized item** works as on the House page, tapping the spot in the picture. On the board, before the image reaches any phone, everything around the house is blurred and, by default, the bathroom (see **Settings**).

When the camera is missing for more than a few seconds the screen says *The webcam is not connected.*, and the line goes away by itself when it is back; while the simulation is on it shows a drawing of the house marked *SIMULAZIONE - SIMULATION*.

## Controls

<img src="../images/screens/en/commands.png" alt="Controls" width="260">

- **Party!**: 20 seconds of dance music composed by the house's own code, with a light show on every Pixels. There is a 30-second pause before the next party.
- **Barbecue** / **Stop the barbecue**: starts or stops the fan of the barbecue.
- **Scenes**: Normal, Cinema, Relax, Night, Away (see [chapter 9](09-rules.md#scenes)).
- **Lights**: choose a room or *All rooms*; every choice reaches the house at once, with no other button. One of ten colours turns the light on, **A** gives it back to the house, the crossed circle turns it off; the effect (*Steady*, *Breathe*, *Blink*, *Wave*, *Rainbow*, *Sparkle*, *Fire*) and the brightness change the light already on. Choosing a room shows how its light is right now. A light turned on here lasts two minutes, turned off it stays dark for one minute, then the room goes back to the house. The switch **Lights follow people** turns the follow-me lights on or off for the whole house.
- **Voice of the house**: **Language of the house** (Italiano, English), **Talkativeness** (Silent, Normal, Chatty), **Volume**, **Ring the doorbell** (starts the intercom conversation as if the button of the totem had been pressed).
- **Questions to the characters**: **Ask a question** makes the house ask, right away, a question to a character picked at random among those in the house, preferring what it does not know about it yet (the favourite colour, whether it loves dancing or barbecues, the favourite dish, where it comes from...). The answer is heard without Talk and kept among its facts; then the house uses it: the light in its favourite colour when it comes into a room or with "turn on Marco's favourite colour", a party if it loves dancing, the barbecue if it loves barbecues (see [chapter 8](08-voice.md#what-the-house-knows-about-the-characters)). The same button, for one character, is on its card in **Characters**. It works outside chatty mode too, but not in silent mode.
- **Make the house say**: type a sentence and tap **Make it speak**: the house says it.

When a command cannot run right now (a party is already on, or resting), a message says *Already running or resting, try again in a moment*.

## Events

<img src="../images/screens/en/events.png" alt="Events" width="260">

Four tabs:

- **Events**: who entered or left which room (people, animals and the car), the car, the rules that fired, notifications, thermostat and shower, scene and language changes, new characters, barbecue, party, and every command from a phone, with the nickname.
- **Said by the house**: every sentence the house said.
- **Changes**: the change log. Who (nickname or *A phone*) created, changed, deleted or restored which rule or character, changed the settings or the calibration, with the time and the phone identifier.
- **History**: for each character, the rooms it went through in the last 24 hours.

The house keeps events for 7 days and positions for 24 hours.

## More

Every other page, in three groups, plus your nickname:

- **The house**: **Events**, **Rules**, **Simulation**;
- **Setting up**: **Calibration**, **Diagnostics**, **Settings**;
- **For the stand**: **Printable sign**, **About**;
- **You**: **Your nickname**, shown in the change log.

### Rules

<img src="../images/screens/en/rules.png" alt="Rules" width="260">

The list of rules, each with a switch to turn it on or off, and the **+ New rule** button. Tapping a rule opens the When / If / Then editor. Everything about rules is in [chapter 9](09-rules.md).

### Characters and objects

<img src="../images/screens/en/identities.png" alt="Characters and objects" width="260">

The list of registered characters, pets, cars and objects, with photo or silhouette, kind, and where they are now (*Now: Kitchen*, or *Not in sight*). **+ Add** starts the guided registration; tapping one opens its card, where you can change **Name**, **Kind**, **English pronunciation (optional)** and **Who they are (for the stories)** (one thing per line, as it would follow the name: *is a doctor*, *loves jazz*, *is afraid of spiders*; the house uses them in stories and answers, see [chapter 8](08-voice.md#stories-memories-and-free-questions)), or **Delete** it (it stays in the bin for 24 hours). See [chapter 7](07-recognition-and-identities.md).

### Simulation

<img src="../images/screens/en/sim.png" alt="Simulation" width="260">

Virtual characters dragged on the plan instead of real figurines, virtual sensors (thermostat and bathroom temperature and humidity) and the three buttons of the totem (**Talk** is held down as on the totem). Anyone can turn it on or off. **Real lights and voice muted** keeps the real house quiet while you try. While the simulation is on, the house ignores the webcam. Drag a virtual character out of the house to remove it.

### Calibration

<img src="../images/screens/en/calibration.png" alt="Calibration" width="260">

The four corners of the base (after **Use these corners** the house sets the light and saves the empty house by itself), the overlay check, **Set the light and save the empty house** and **Save the empty house only**. While the house works, a box with a spinner says what it is doing and the buttons stay locked, so an operation never starts twice; at the end the result appears (see [chapter 5](05-testing.md#9-camera-calibration)). Below are the dataset tools: **Capture**, **Burst (10)**, **Record a sequence (60 s)** and **Download the dataset** (see [chapter 7](07-recognition-and-identities.md#datasets-and-recordings)).

### Diagnostics

Refreshed every few seconds:

- **Board**: host name and version, uptime, CPU load and temperature, memory, free disk, number of Wi-Fi clients, clock and where its time came from, audio device, voice (speech recognition and language model), camera (device, frames per second, processing time of a picture and how it splits between segmentation, recognition and the rest, *not calibrated*, *moved, calibrate again*).
- **Modulino**: the state of the link with the microcontroller, the firmware protocol version, and a green or red dot for each module.
- Buttons: **I2C scan** (addresses answering on each Hub channel), **Audio test**, **Microphone test (3 s)**, **Download the logs** (shows the last 500 lines of the application log and saves them as a file).

### Settings

<img src="../images/screens/en/settings.png" alt="Settings" width="260">

- **House**: the name of the house in Italian and English; **Buttons mounted upside down**, for a totem assembled the other way round; **Bathroom blurred in the live view**, on by default.
- **Lights · Party · Barbecue · Climate**: *Maximum brightness (%)*, *Pixels current limit (mA)*, *Brightness of the follow-me lights*, *Off after (s)*, *Colour of the follow-me lights*, **Light in the favourite colour of who comes in** (in the Normal scene the light of a room takes the favourite colour of whoever is in, if it told the house), party *Duration (s)* (10–60), *Fan duration (s)* (5–120), *Hot: rise over the baseline (°C)*, *Shower: humidity rise (%)*. Then **Save**. Brightness and current limit go to the microcontroller at once.
- **Voice**: **Greet new phones**, **Questions to the characters (chatty mode)** and *One question every (s)* (see [chapter 8](08-voice.md#talking-without-pressing-talk)); **Wake up with a keyword** and *Keyword* (for example *Casa*): once the word is said, the house does what the Talk button does (see [chapter 8](08-voice.md#the-word-of-activation)). On saving, below appears how the house will hear the word (*Casa 2* becomes *casa due*) and which of its words the speech recognizer does not know.
- **Time**: the time of the phone and **Use this phone's time**, which sets the clock of the house.
- **Wi-Fi of the house**: the network name and *Wi-Fi password* (8 to 63 characters). **Save**, after *Are you sure?*, writes it into the hotspot; if the hotspot is on, it restarts after a couple of seconds and every phone, yours included, must join again with the new password. The printable sign updates by itself: print it again.
- **Backup**: **Download the backup** (a zip with rules, characters with their photos, and settings; never the network, the house name or the camera calibration), **Restore from a backup** (replaces rules, characters and settings), **Default rules** (replaces all rules with the ones the house started with).
- **Bin**: rules and characters deleted in the last 24 hours, each with **Restore**.
- **System**: **Restart the app**, **Reboot the board**, **Power off the board**, each after *Are you sure?*.

### Printable sign

<img src="../images/screens/sign.png" alt="The printable sign" width="360">

An A4 portrait page, ready to print, with the name of the house and two QR codes: **1 Join the Wi-Fi** (with SSID and password written below) and **2 Open the house** (with the address). A note in Italian and English explains what to do if the phone complains about the missing internet, and how to use the buttons of the totem. It opens at `/sign`.

### Booth display

It is not in the menu: open it by typing `/board` after the address of the house. It shows the plan, the live view, the last sentence said and the latest events, for a monitor or a tablet at the stand, and has no controls.

### About

What the project is, the credit line, and the licences of voices and models.

## Trying the web app on a PC

The whole house runs on a PC in simulation, without any hardware. From a clone of the repository:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m domotiq --simulate
```

Then open `http://localhost:8080/`. The house keeps its data in `var/` inside the repository folder.

## For makers: the API

| Method and path | Use |
|---|---|
| `GET /api/state` | the complete state |
| `WS /ws` | the complete state on connection, then every change, questions and subtitles |
| `GET /api/stream` | live view (MJPEG) |
| `GET/POST/PUT/DELETE /api/rules` | rules |
| `GET/PUT/DELETE /api/identities` | characters |
| `POST /api/commands/{name}` | party, grill, grill_stop, scene, light, lights_off, lights_auto, language, verbosity, volume, follow, intercom, say, alarm (`{"armed": false}` switches the alarm off) |
| `POST /api/confirm/{id}` | answer a question of the house (`{"value": ...}`; `{"together": [...]}` for *both*, `{"nothing": true}` for *nothing there*) |
| `POST /api/time` | time from a phone (only if the house does not know it) |
| `POST /api/clock` | time from the settings |
| `GET/PUT /api/settings` | settings |
| `GET /api/diagnostics` | diagnostics |
| `POST /api/vision/{name}` | calibration: corners, adjust, empty, capture, record |
| `GET /api/events` | events |

Next: [recognition and identities](07-recognition-and-identities.md).
