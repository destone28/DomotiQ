# DomotiQ: quick guide for the stand staff

House: casa1 / casa2 · Wi-Fi `DomotiQ-Casa1` / `DomotiQ-Casa2` · web app `http://10.42.1.1/` / `http://10.42.2.1/`

Wi-Fi password: ____________________ Staff PIN: ____________

(Write them by hand on the printed copy only.)

## Power

- **On**: plug in the power supply. The lights breathe dimly for about 40 seconds while the board starts, then go off: the house is ready. The Wi-Fi of the house starts by itself.
- **Off at the end of the day**: web app, **More → Settings → Power off the board** (staff), then unplug.
- **After a power cut** the house restarts by itself. The barbecue fan stays off.

## The three buttons (left to right, as the visitor sees them)

- **Talk**: hold it down, speak, release. "Dov'è Marco?" · "Who's in the kitchen?" · "Fai festa!" · "Light the barbecue" · "Luce rossa in camera" · "Com'è la casa?"
- **Intercom**: the doorbell rings, the house asks "Who is it?": say a name. A known character is let in (move it through the front door within a minute); a new name is registered.
- **Language**: Italian ⇄ English. Lights flash green = Italian, red = English. LED on = English.

## Visitors' phones

Scan QR 1 on the sign (Wi-Fi), then QR 2 (the house). If the phone asks: *Stay connected* / *Use without Internet*. Android: turn mobile data off for a moment. Everyone can give commands, change rules and register characters.

## Register a figurine

**More → Characters and objects → + Add** → name (and a photo if you like) → **Next** → put the figurine on a free spot of the floor → choose what it is → **Save**. Names must be unique: add a surname if needed. Warnings about colours close to the floor or to another character are advice, not errors.

## If something misbehaves

| You see | Do |
|---|---|
| Banner *The webcam has moved: calibrate again* | Calibrate (below). |
| Ghost objects, or figurines not seen, after the hall light changed | Empty the house, **Calibration → Adjust to the light again**. |
| A **?** on a character, or *The house asks* | Tap the right name on the banner, or hold Talk and say it. |
| The house is silent | **Controls**: Talkativeness *Normal*, Volume up. Speaker knob at maximum. |
| "I don't know what time it is" | Open the web app on a phone, or hold Talk: "Sono le quindici e trenta". |
| Lights breathe dimly and nothing reacts | The software is (re)starting: wait a minute. Then **Settings → Restart the app**, then **Reboot the board**. |
| A red status dot at the top | **Diagnostics** shows which part. |
| A visitor broke a rule or deleted a character | **Events → Changes** shows what happened; **Settings → Bin → Restore** (24 hours); **Settings → Default rules** resets all rules. |
| Party or barbecue refuses | It is resting: wait 30 seconds. |
| A phone cannot open the page | Mobile data off; type `http://10.42.N.1/`. |

## Staff tools

**More → Staff PIN → Staff login** (valid 12 hours on that phone; after 5 wrong PINs wait a minute).

- **Calibration**: take figurines and car out → tap the 4 corners of the base (front left, front right, back right, back left; front = driveway) → **Use these corners** → check that the drawn walls sit on the real ones → **Adjust to the light again**. Calibrate before opening the house to visitors: until then the blur only guesses where the bathroom is.
- **Diagnostics**: modules, I2C scan, **Audio test**, **Microphone test (3 s)**, logs.
- **Settings**: brightness and durations, PIN, Wi-Fi password, **Use this phone's time**, backup, bin, restart, reboot, power off.
- **Controls → Make the house say**; **Simulation** on and off.

Full guide: `docs/en/` in the repository.
