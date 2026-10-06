# DomotiQ: quick guide for the stand staff

House: casa1 / casa2 · Wi-Fi `DomotiQ-Casa1` / `DomotiQ-Casa2` · web app `http://10.42.1.1/` / `http://10.42.2.1/`

Wi-Fi password: ____________________

(Write it by hand on the printed copy only.)

## Power

- **On**: plug in the power supply. The lights breathe dimly for about 40 seconds while the board starts, then go off: the house is ready. The Wi-Fi of the house starts by itself.
- **Off at the end of the day**: web app, **More → Settings → Power off the board**, then unplug.
- **After a power cut** the house restarts by itself. The barbecue fan stays off.

## The three buttons (left to right, as the visitor sees them)

- **Talk**: hold it down, speak, release. "Dov'è Marco?" · "Who's in the kitchen?" · "Fai festa!" · "Light the barbecue" · "Luce rossa in camera" · "Com'è la casa?"
- **Intercom**: the doorbell rings, the house asks "Who is it?": say a name. A known character is let in (move it through the front door within a minute); a new name is registered.
- **Language**: Italian ⇄ English. Lights flash green = Italian, red = English. LED on = English.

All three button LEDs on: the house is listening, answer without pressing anything. LEDs breathing: the house is working out its answer.

## Visitors' phones

Scan QR 1 on the sign (Wi-Fi), then QR 2 (the house). If the phone asks: *Stay connected* / *Use without Internet*. Android: turn mobile data off for a moment. Everyone can do everything: commands, rules, characters, calibration and settings. Every change goes into the log and deleted things wait in the bin for 24 hours.

## Register a figurine

**Characters → + Add** → name (and a photo if you like) → **Next** → put the figurine on a free spot of the floor → choose what it is → **Save**. Names must be unique: add a surname if needed. Warnings about colours close to the floor or to another character are advice, not errors.

## If something misbehaves

| You see | Do |
|---|---|
| Banner *The webcam has moved: calibrate again* | Calibrate (below). |
| Ghost objects, or figurines not seen, after the hall light changed | Usually the house adapts by itself within a few seconds: the characters stay where they were, the webcam sets itself again and the empty house is learned again in the new light (*Diagnostics* counts the adaptations). If not: empty the house, **Calibration → Set the light and save the empty house**. |
| The house does not recognize a character it knows, or calls it by the wrong name | On the question pick **Someone already known…** and tap **This one**; or tap the character on the plan → **Who is it?** / **Someone else: change** and pick it from the list. The house learns that look. |
| A figurine in the house does not show on the plan | **House → Unrecognized item**, then tap where it is on the plan (or in **Live**, in the picture), and choose who it is. |
| A **?** on a character, or *The house asks* | Answer aloud right after the question, with no Talk, with any sentence: a name, "no, it's a dog", "there's nobody", "both of them". Or tap the name on the question, or **Both**; for a newcomer you can type a new name, choose its kind and tap **Add**, or tap **Nothing there**. |
| The house does not notice the characters, and *Diagnostics* always shows a hand | Something big lies on the edge of the base (a module, a cable): remove it or fix it down. After 8 seconds still, the house stops taking it for a hand anyway. |
| The house asks about somebody who is not there | Answer "there's nobody" or tap **Nothing there**: the house forgets it. If it is already on the plan, tap it and choose **Not really there: remove**. If it keeps coming back in the same spot, look for a module, an LED or a cable to fix down, then **Save the empty house only** with the house empty. |
| A red alarm notice | **Switch off** turns the alarm off like a burglar alarm (switch it on again from the **House** page); the **✕** closes it on every phone and it comes back only if the alarm happens again. An amber notice is a warning. |
| The house is silent | **Controls**: Talkativeness *Normal*, Volume up. Speaker knob at maximum. |
| "I don't know the time: what time is it now?" | Answer aloud, with no Talk: "It's half past three". Or open the web app on a phone. |
| Lights breathe dimly and nothing reacts | The software is (re)starting: wait a minute. Then **Settings → Restart the app**, then **Reboot the board**. |
| A red status dot at the top | **Diagnostics** shows which part. |
| A visitor broke a rule or deleted a character | **Events → Changes** shows what happened; **Settings → Bin → Restore** (24 hours); **Settings → Default rules** resets all rules. |
| Party or barbecue refuses | It is resting: wait 30 seconds. |
| During a party the plan does not follow the figurines | That is on purpose: with the coloured lights the house does not look. It starts again by itself when the party is over and the lights stand still. |
| A phone cannot open the page | Mobile data off; type `http://10.42.N.1/`. |

## Setting up (More)

- **Calibration**: take figurines and car out → tap the 4 corners of the base (front left, front right, back right, back left; front = driveway) → **Use these corners**: the house sets the light and saves the empty house by itself (about 15 seconds, with a spinner; do not touch the house) → check that the drawn walls sit on the real ones. Calibrate before opening the house to visitors: until then the blur only guesses where the bathroom is.
- **Diagnostics**: modules, I2C scan, **Audio test**, **Microphone test (3 s)**, logs.
- **Settings**: brightness and durations, Wi-Fi password, **Use this phone's time**, backup, bin, restart, reboot, power off.
- **Controls → Make the house say**; **Controls → Ask a question** (the house asks a character something and keeps it); **Simulation** on and off.
- **Settings → Voice → Wake up with a keyword**: once the word is said (for example *Casa*), the LEDs blink at once and, if you do not go on, the house answers "Yes?" and listens as with Talk. You can also say it all in one go: "Casa, turn on the kitchen light".
- **Alarm**: box at the bottom of the **House** page, **Switch on** / **Switch off**.

Full guide: `docs/en/` in the repository.
