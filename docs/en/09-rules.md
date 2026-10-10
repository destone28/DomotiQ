# 9. Rules

The behaviour of the house is written as rules of the form **When** something happens, **If** some conditions are true, **Then** do these actions. The house starts with a set of default rules, and anyone can change them, switch them off or write new ones from the web app, in **More → Rules**.

## The structure of a rule

| Field | Meaning |
|---|---|
| **Name** (IT) and (EN) | the name, in both languages |
| **Priority** | 1 to 98: the layer of the rule's lights; a higher number wins over a lower one (see [Priorities and light layers](#priorities-and-light-layers)) |
| **Pause between two runs (s)** | after running, the rule ignores the same event for this many seconds |
| **Enabled** | the rule is active |
| **It is an alarm (stays on while it lasts)** | see [Alarms](#alarms) |
| **When** | exactly one event |
| **If** | any number of conditions, all of which must be true; with none the editor shows *Always* |
| **Then** | one or more actions, run in order |

There is no "or": to react to two different situations, write two rules.

Rules are plain JSON, stored on the board in `var/config/rules.json`. This is the default bathroom rule:

```json
{
  "id": "r-bathroom-max",
  "name": {"it": "Bagno al massimo 1", "en": "Bathroom for one"},
  "priority": 95, "alert": true, "cooldown_s": 0,
  "when": {"type": "count_above", "room": "bathroom", "value": 1, "grace_s": 2,
           "repeat_s": 15, "who": {"category": "person"}},
  "then": [
    {"type": "light", "room": "bathroom", "effect": "blink", "color": "#ff8000", "brightness": 80},
    {"type": "say", "text": {"it": "Il bagno è occupato! Aspetta il tuo turno.",
                             "en": "The bathroom is taken! Please wait your turn."}},
    {"type": "notify", "level": "warning",
     "text": {"it": "{count} persone in bagno", "en": "{count} people in the bathroom"}}
  ]
}
```

### Who

Many events and conditions have a **Who** field with two choices: the kind (*anyone*, *person*, *animal*, *dog*, *cat*, *car*, *object*) and the character (*anyone* or one registered character). *animal* covers dogs, cats and every other pet. The rule format also accepts a list of characters to leave out, `"who": {"category": "person", "except": ["<character id>"]}`, which the editor does not show. If the chosen character is deleted, the rule stays as it was and no longer fires for it: the list of rules and the editor show ⚠️ *deleted character*, so that saving it does not turn it into a rule for anyone by mistake. Restoring the character from the bin makes the rule work again.

## When: the events

| Event (as in the editor) | Fields | Fires when |
|---|---|---|
| **enters a room** | Room, Who | someone matching *Who* enters the room. The room can also be *Every room of the house* (kitchen, living room, bedroom, bathroom, utility room, garage) or *Anywhere*. |
| **leaves a room** | Room, Who | the same, leaving. |
| **stays in a room** | Room, Seconds, Repeat every (s, 0 = no), Who | someone stays in the room longer than *Seconds*; it fires again every *Repeat every* seconds while they stay. Whoever leaves in time triggers nothing. |
| **a room has more than** | Room, Value, Confirm after (s), Repeat every, Who | the number of matching things in the room goes above *Value* and stays there for *Confirm after* seconds. It fires again only after the number went back, or every *Repeat every* seconds. |
| **a room has fewer than** | Room, Value, Confirm after (s), Who | the same, below the value. |
| **a character shows up** | Who | a registered character appears in view. |
| **a character disappears** | Who | a registered character is no longer seen anywhere. |
| **it is a given time** | Time | the clock of the house reaches that time (HH:MM), every day. It needs a known time (see [chapter 8](08-voice.md#setting-the-clock-by-voice)). |
| **a sensor goes above** / **goes below** | Sensor, Measure, Value | the thermostat (sideboard) or bathroom sensor crosses the value, in temperature (°C) or humidity (%). It fires once, and again only after the reading has moved back by 0.3 °C or 2 %. |
| **the thermostat changes** | State: hot, cold, normal | the virtual climate changes state (see below). |
| **the shower** | State: starts, ends | the bathroom humidity rises 8 points above its recent average (starts), or comes back within 3 points (ends). |
| **a button is pressed** | Button: Talk, Doorbell, Language | that button of the totem is pressed. The button also keeps doing its normal job. |
| **the car** | State: arrives, parked, leaves, away | the car enters the garage, stands still for 3 seconds in the parking area, leaves the garage, or has been out of it for 10 seconds. |
| **the scene changes** | Scene | the house switches to that scene. |
| **the barbecue** | State: starts, ready | the fan starts, or the barbecue is ready (the fan has finished). |
| **the party** | State: starts, over | a party starts or ends. |

**The virtual climate.** The Thermo in the sideboard is a thermostat you warm with a finger. Its reference is the average of the last 5 minutes. It goes **hot** when the temperature rises 1 °C above the reference, or rises faster than 0.1 °C per second, or when the humidity jumps 10 points (someone breathes on it, which is quicker than a finger); **cold** when it falls 1 °C below the reference; **normal** again when it is back within 0.5 °C. The thresholds are in **More → Settings**, under **Lights · Party · Barbecue · Climate**.

## If: the conditions

| Condition | Fields | True when |
|---|---|---|
| **the room is occupied** | Room, Who | at least one matching thing is in the room |
| **the room is empty** | Room, Who | no matching thing is in the room |
| **the number in a room** | Room, Comparison, Value, Who | the count compares as chosen (`>`, `>=`, `<`, `<=`, `=`) |
| **a character is home** | Character | the character is in view |
| **a character is away** | Character | the character is not in view |
| **the time is between** | From, To | the time is in the range; a range can cross midnight (20:00 to 07:00) |
| **a sensor** | Sensor, Measure, Comparison, Value | the current reading compares as chosen |
| **the scene is** | Scene | the current scene is that one |
| **the barbecue is** | On | the barbecue is on (or off) |
| **the car is** | State | the car is in that state |
| **the thermostat is** | State | the virtual climate is hot, cold or normal |

## Then: the actions

| Action | Fields | Does |
|---|---|---|
| **turn on a light** | Room (or *All rooms*), Colour, Effect, Brightness, Duration (s) | lights the room's Pixels. Brightness is relative to the house maximum. In a normal rule the light lasts *Duration* seconds, 30 if left empty; in an alarm rule, leave it empty and the light lasts as long as the alarm. |
| **turn off this rule's lights** | Rule | removes the lights set by this rule, or by another rule you choose (the default *Thermostat: back to normal* rule removes the lights of *hot* and *cold*) |
| **play** | Sound: short chime, doorbell, alarm, beep, notification | plays a sound |
| **say a sentence** | Italian text, English text, Speak also in mode | the house says the text in its current language. *Normal* is spoken in Normal and Chatty mode, *Chatty* only in Chatty mode. In Silent mode it only appears as a subtitle. |
| **send a notification** | Kind: information, good news, warning, alarm; texts | a message on every phone and in the events; *alarm* also vibrates the phones |
| **change scene** | Scene | switches scene |
| **throw a party** | | starts a party (if one is not running or resting) |
| **light the barbecue** | | runs the barbecue fan for its set duration |
| **wait** | Seconds | pauses before the next action (up to 10 minutes) |

The texts can contain these fields in braces, filled in from the event:

| Field | Becomes |
|---|---|
| `{name}` | the character's name, or "someone" |
| `{room}` | the room's name ("Kitchen") |
| `{room_in}` | the room as a place ("in cucina", "in the kitchen") |
| `{count}` | the count that fired the rule |
| `{temp}`, `{rh}` | temperature and humidity of the sensor |
| `{time}` | the current time |

**Effects**: *Steady*, *Breathe*, *Blink*, *Wave*, *Rainbow*, *Sparkle*, *Fire*, *Alarm* (red flashing at 2 Hz), *Cool air* (a light-blue wave), *Warmth* (an orange glow). No effect flashes more than 3 times per second.

## Alarms

A rule marked **It is an alarm (stays on while it lasts)**:

- draws its lights on the alarm layer, above everything except the language flash;
- shows a notice on every phone: **red** (alarm) if the rule sounds the alarm or sends a notification of kind *alarm*, **amber** (warning) otherwise; on the plan the room is red or amber in the same way;
- is recorded as a warning in the events;
- lasts as long as the situation that fired it: when the person leaves the room, or the count goes back, the lights and the notice go away.

This fits **stays in a room** and **a room has more than / fewer than**, whose situations have an end. With any other trigger (someone enters a room, a button, a time of day) nothing says when the situation is over, so the alarm ends by itself after 30 seconds.

**Only sure presences.** The alarm rules count only the presences the house is sure of: a character it knows (confirmed or recognized well), or something unknown that has stood there, still and clearly visible, for at least 6 seconds. A blob just born, a reflection or a figurine still in a hand set nothing off; if the presence becomes sure while it is still in the watched place, the alarm fires then. The other rules and the follow-me lights work on everything the house sees.

**On and off.** The alarm of the house is switched on and off like a burglar alarm, from the **Alarm** box on the **House** page or with the **Switch off** button of the red notice (chapter 6). Off, no alarm rule fires and those going off stop at once, with their lights; the other rules go on. Switched on again, whoever is already in a watched place is noticed again, as if they had just come in. The state survives a restart.

## Priorities and light layers

Each light has a stack of layers. The highest active layer decides what the light shows; when it expires or is removed, the layer below shows again. From the bottom:

| Layer | Priority |
|---|---|
| follow-me lights | 10 |
| scene | 30 |
| rules | the rule's own priority (1–98), 50 by default |
| lights switched on or off from **Controls** or by voice | 55 |
| alarm rules | 95 |
| the language flash (green or red for a second) | 99 |

During a party the microcontroller runs the light show by itself, in time with the music; when the party ends the house redraws every light from its layers.

**Follow-me lights.** A room with at least one person gets a warm white light at 60 % (of the house maximum); it goes off 3 seconds after the last person leaves. Animals do not turn lights on. In the garage the car counts too: the light stays on while the car arrives and until it has been parked for 10 seconds. The garden and the driveway have no light; the light of the utility room is the LED matrix of the UNO Q. Colour, brightness and delay are in the settings, and **Controls → Lights follow people** switches them off.

## Scenes

| Scene | Lights |
|---|---|
| **Normal** | the lights follow people, in their favourite colour if they told the house |
| **Cinema** | in the living room the flickering blue glow of a screen (*Sparkle*), every other room off, even where people are |
| **Relax** | a fire in the living room (*Fire*), an orange light breathing in the bedroom; warm dim lights where people are |
| **Night** | everything off but a small orange night light in the bathroom; whoever gets up finds a very dim orange courtesy light |
| **Away** | the empty house looks lived in: one room at a time (kitchen, living room, bedroom or bathroom) lights up for 15-30 seconds, then another one. The default *Intruder while Away* rule watches the house |

Scenes are chosen from **Controls**, by voice ("Scenario cinema", "Good night") or by a rule, and the house says the name of the new scene.

## The default rules

| Rule | When | Then | At start |
|---|---|---|---|
| **Utility room off limits** (alarm) | a person stays in the utility room more than 5 s (repeats every 10 s) | living room and garage flash red, alarm sound, "Warning: the utility room is off limits!", alarm notification "{name} is in the utility room" | on |
| **Bathroom for one** (alarm) | more than 1 person in the bathroom for 2 s (repeats every 15 s) | the bathroom blinks orange, "The bathroom is taken! Please wait your turn.", warning "{count} people in the bathroom" | on |
| **Shower** | the shower starts | light-blue wave in the bathroom for up to 3 minutes, "Turning on the bathroom fan.", notification "Shower running" | on |
| **Shower over** | the shower ends | removes the lights of *Shower* | on |
| **Thermostat: hot** | the thermostat goes hot | light-blue wave everywhere for up to 2 minutes, "It's hot! Turning on the air conditioning.", notification with the temperature | on |
| **Thermostat: cold** | the thermostat goes cold | warm orange glow everywhere for up to 2 minutes, "It's cold: turning on the heating." | on |
| **Thermostat: back to normal** | the thermostat is normal again | removes the lights of *hot* and *cold*; in Chatty mode "The temperature is back to normal." | on |
| **Car arrived** | the car arrives | "Welcome home!", notification "The car is in the garage" | on |
| **Car left** | the car leaves | "Have a good trip!", notification "The car left the garage" | on |
| **Barbecue ready** | the barbecue is ready | "The barbecue is ready, everyone to the garden!", notification | on |
| **Intruder while Away** | a person enters any room of the house, if the scene is Away | all lights flash red for 10 s, alarm sound, "Intruder in the house! {name} is {room_in}.", alarm notification | on |
| **Living room party** | more than 3 people in the living room for 3 s | throws a party | off |
| **Barbecue with friends** | more than 1 person in the garden for 10 s | lights the barbecue | off |

Who counts: the default rules about people use the kind *person*, so pets never trigger the utility room or the bathroom alarm. The garage light for the car comes from the follow-me lights, not from a rule.

## Who can change the rules

- **Anyone**, from the web app. The first time, the web app asks for an optional nickname, shown in the change log.
- **Every change is logged** on the board: time, phone identifier, nickname, what was created, changed, switched, deleted or restored, with the rule before and after. Read it in **Events → Changes**.
- **Deleted rules go to the bin** for 24 hours and are restored from **Settings → Bin**.
- **Default rules** (in **Settings → Backup**) replaces all rules with the ones the house started with. The reset is logged too.
- Rules travel with the **backup** zip, which can be downloaded and restored (see [chapter 6](06-web-app.md#settings)).

Next: [attributions](10-attributions.md).
