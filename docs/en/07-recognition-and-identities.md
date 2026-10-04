# 7. Recognition and identities

The house recognizes people, pets, the car and objects with **classical computer vision**, without training a model. Seen from the pole, a figurine's base is only about a dozen pixels across at the analysis resolution, the number of characters has no limit, and visitors add new ones during the fair. A trained detector would need hundreds of labelled images for every new character; the classical method registers a character in seconds and fits in one CPU core of the UNO Q.

**Machine learning** is used in one place only: when a character is registered with a photo, a **YOLOX-Nano** object detector trained on the COCO dataset looks at the photo and proposes what kind of thing it is.

## How the house sees

The vision runs in a separate process, so a slow frame or a camera problem never slows down the web app or the voice; if it stops, it starts again by itself.

1. **Capture.** The Logitech C270 delivers MJPEG frames; the house analyses them at 640 × 480, 7 to 10 per second on the board. Exposure, white balance and gain are locked, so the colours do not shift when figurines and coloured lights come and go. The values are found by measuring the pictures: the house lets the camera adjust automatically on the empty house, measures brightness and colours, then looks for the manual values that give the same picture, a quarter darker. What the colour temperature of the camera cannot correct (some warm, greenish lights) is corrected by a fixed gain on each channel. Until the light is set the house recognizes nothing, and says so in *Diagnostics*.
2. **The empty house.** At calibration the house stores the median of 20 frames of the empty house, furniture included. Everything that differs from it is a figurine, the car, an object or a visitor's hand.
3. **Difference in Lab colour space, with light correction per room.** The room lights of the house are coloured, and the hall light changes. Each pixel is corrected with the gains of its own room's light: one gain per colour channel, estimated on the free floor of the room as the most common ratio to the empty house (so a figurine or the car does not bias it), and the one closest to the previous frame when two are possible. Across a doorway the gain passes gradually from one room to the other. The house tells the vision every time it changes a light.
4. **Shadows do not count.** A shadow is darker but keeps the colour of the floor.
5. **Masks.** The vision looks at the base of the house only: what is around it (the stand, the hands of visitors before they come in, phones) does not count. Inside the base, zones that are not floor are ignored: the wall lights, the tree canopy, the camera pole, the tops of the walls and the intercom totem, whose LEDs go on and off, each projected at the height where it really is.
6. **Objects.** After a morphological clean-up, each connected blob becomes an object with its area in mm², its median colour and a histogram of its colour, its elongation, and its nearest and farthest points from the point under the camera.
7. **Where it stands (parallax).** The camera sees a standing figurine from above, so the figurine appears stretched away from the point under the lens: its nearest point is the front of the feet, its farthest point the back of the head. Brought down by the figurine's height, the head gives the position of the feet too, so a figurine is placed correctly even when its feet are hidden behind a wall. The car, a box rather than a figurine, is placed at the middle of what is seen. On synthetic test scenes the position error stays below 12 mm.
8. **Hands.** A blob at least as big as an arm (2,500 mm² inside the base) entering from the edge of the base is a visitor's hand, except at the garage gate, where the car drives in. Every piece close to the hand belongs to it, whatever its size: the arm cut by wall tops and wall lights, the fingers, the shadow. A "hand" that stays perfectly still for 8 seconds is instead something lying on the edge (a module, a cable), and it becomes part of the empty house.
9. **Tracking.** Objects are matched to the tracks of the previous frame with the Hungarian method, on a distance that combines position, colour and size. Something that jumps more than 90 mm between frames is not the same thing. A followed character that is not seen for a moment (a light, two figurines touching) stays where it was for up to two minutes, instead of disappearing and coming back.
10. **Carried by hand.** When a figurine disappears under a hand, its track becomes *carried* and keeps its identity; when the hand has gone, the figurine that reappears where the hand worked is the same character. If the hand leaves without putting it down, the character leaves the house 2.5 seconds later.
11. **Who is it.** Each registered identity has a **colour signature**: a histogram of the a\* and b\* colour axes of the Lab space (where lightness is kept apart, so a shadow or a dimmer light changes little) plus the median colour. For white, grey and black figurines lightness weighs more, since it is the only thing that tells them apart. Identities are unique, so the assignment of identities to tracks is solved for all of them together; an identity is given after two frames of agreement. While a figurine is followed with confidence, its signature is slowly updated with what the camera sees.
12. **Which room.** The room is the one under the point where the figurine stands, with 15 mm of tolerance on the doorways, so a figurine on a threshold does not flicker between two rooms.

The result is a list of tracks, each with a position in millimetres, a room, a kind and, when known, an identity. The rest of the house (lights, rules, voice, web app) works on this list.

### Nothing moves by itself

In a diorama every change is made by a hand: a figurine comes in, goes out or moves only if somebody picks it up. The house uses this rule not to see presences that are not there.

- **While a hand is over the house**, and for 0.6 seconds after it has left (its shadow, the figurine still swinging), the house counts nothing new and makes nobody disappear.
- **Then new things are looked for only where the hand worked**, for 3 seconds. A new presence is announced after one second of stability: the reflection of the arm that has just left lasts less. Nothing is born that lies entirely on a wall (a reflection), nor anything small right on the edge of the base (a cable, a sleeve).
- **A change with no hand around** (a reflection, the hall light) never becomes a presence: after about 3 seconds it becomes part of the empty house. The exception is something that clearly stands out and stays, appearing within 20 seconds of a hand: a figurine put down while the house was waiting, which becomes a presence after 2 seconds.
- **When the house changes the light of a room**, for 2.5 seconds its glow on walls and floor is not taken for a presence.
- **When the light of the whole hall changes**, the house measures the light of every room again and waits; if the light goes beyond what the correction can follow, after 4 seconds it learns the empty house again from the current picture, leaving out the characters it is following.
- **At start-up** the house recognizes the registered characters that are in the house (by their colour) and the car; the rest becomes part of the empty house, since meanwhile lights may have gone on or modules may have been moved. A new character that was already in the house shows up as soon as somebody moves it.
- **The intercom** is left out of the analysis, but its outline counts as the edge of the base: an arm reaching towards the living room over the totem is still a hand.

## Kinds of things

Every identity has a kind: **person**, **dog**, **cat**, **animal** (any other pet), **car** or **object**. Rules can filter on them; *animal* in a rule covers dogs and cats too. The furniture of the house is fixed and is part of the empty house; a new object put in the house (a chair, a ball, a suitcase) is an identity of kind *object*.

When a registration starts, the house proposes a kind:

- **From the photo**, if one was taken: YOLOX-Nano runs on the board with ONNX Runtime and looks for the 80 COCO classes; the largest confident detection decides. *person* gives a person, *dog* a dog, *cat* a cat; *car*, *truck* and *bus* give a car; *bird*, *horse*, *sheep*, *cow*, *elephant*, *bear*, *zebra*, *giraffe* and *teddy bear* give an animal; every other class gives an object, with a proposed name (for example *chair*, *sports ball*, *suitcase*).
- **Without a photo**, from size and shape seen from above: a large blob is a car, a tall and narrow one a person, a small elongated and low one an animal, anything else an object.

The proposal is always confirmed by whoever registers it.

## Registering a character

Anyone can register characters, pets, cars and objects, in three ways.

### From the web app

1. **More → Characters and objects → + Add**, or tap an unknown figurine on the **House** screen and then **Register**.
2. Type the **Name**. Optionally tap **Take or choose a photo**: one front photo is enough; it is shown in the list and used to guess the kind. The phone shrinks it to 1024 pixels before sending it. Tap **Next**.
3. *Put it down on a free spot of the house: I'm looking for it…* The house looks for something it sees but does not know. With exactly one candidate it takes it; with more than one it says *I see more than one new thing: tap the right one on the plan*; with none it waits. After two and a half minutes without a result it gives up: *I didn't find anything new. Try again.*
4. *Found it! What is it?* The house shows its guess (*It looks like: dog*, with a proposed name for objects), any [warnings](#warnings), and the six kinds. Choose and tap **Save**.
5. *Marco is registered. From now on I'll recognize it.*

### With the intercom

1. A visitor presses **Intercom** on the totem. A doorbell rings and the house asks "Chi è?" / "Who is it?".
2. **A registered name**: "Hi Marco, come on in!". The first person figurine that comes from the driveway through the front door into the living room in the next 60 seconds gets that name. If the name belongs to someone already inside, the house says so ("But Marco is already in the kitchen!"). If the camera clearly recognizes the figurine that comes in as somebody else, the house says it ("Hmm, you look like Sofia to me, not Marco!") and keeps the identity it sees.
3. **A new name**: "I heard Marco, right?" After a *yes*: "Nice to meet you, Marco! Come in through the door." The first figurine the house does not know that comes through the front door into the living room in the next 60 seconds becomes Marco, with no further step: the category it guessed can be changed later in the character's card.
4. **A name not understood**: a second try ("Sorry, I didn't catch that. Who are you?"), then "I don't know you, but come in: you're a guest."

When a registration started by voice is complete, the house says "Welcome, Marco! Now I know you."

### With the Talk button

Hold **Talk** and say "Aggiungi un personaggio" / "Add a character". The house asks "What's the name?", then "Which room did you put it in?", and looks for the figurine it does not know in that room:

- exactly one: it becomes Marco at once;
- none yet: "OK: put it in the kitchen, I'm waiting." The first unknown figurine put in that room within two and a half minutes becomes Marco;
- more than one: "I see more than one newcomer in the kitchen: pick Marco in the web app." A banner *Voice registration to complete* appears on every phone; **Choose** opens the plan to tap the right figurine.

## Names

- **Names are unique** in the whole house, without distinction between upper and lower case, and they are also checked against the English pronunciations. A name already in use is refused: *The name Marco is already used: add a surname or a nickname.* Asked by voice to add a name it already has, the house answers "I already know Marco."
- There is **no limit** to the number of characters or objects.
- **Speaking names.** To recognize a name by voice, the house listens for the registered names only, with the vocabulary of its speech recognition model. A name made of words the model does not know cannot be heard by voice: at registration the house checks it and warns on the confirmation step (*The Italian speech recognizer does not know "Zorbax": I may not understand it by voice.*). The English recognizer may not hear an Italian name: in the character's card, fill in **English pronunciation (optional)** with a spelling it can hear; the house accepts either form.
- Anyone can rename or delete a character from its card. A deleted character stays in the bin for 24 hours and the staff can restore it; if its name was taken in the meantime, it comes back with " 2" after the name.

## Warnings

At registration the house checks what could make the new figurine hard to recognize, and says so on the confirmation step:

- *Its colour is very close to the floor / the lawns / the walls: I may not see it well.* The difference from the empty house is small, so parts of the figurine may be lost.
- *It keeps disappearing: try moving it to a clearer spot.* The figurine was detected in fewer than half of the frames since it appeared.
- *It looks just like Marco: I will tell them apart only by following them.* Its colour signature is almost the same as a registered one.

None of these prevents the registration.

## Same-colour figurines and doubts

Two figurines of the same colour are told apart only by following them. Continuity of movement keeps them distinct: if only one of the two is picked up and put down elsewhere, it must be that one, since the other stayed in view.

When the thread is lost (both picked up together, the two touched, one reappeared far away, or the house just started) the track becomes **uncertain**. The house then:

- asks on every phone, with a banner such as "Is it Marco or Leo in the kitchen?" and one button per name;
- asks aloud too, if its talkativeness allows it, and right after listens for the answer by itself, with no need for **Talk**: just say the name. The first answer wins, aloud or from a phone;
- without an answer within 60 seconds, keeps its best guess, marked as uncertain: a **?** on the plan, and "Marco is in the kitchen. I think." in voice answers.

It asks again about the same figurine at most every 30 seconds. An answer, a registration or an intercom entry **confirms** an identity: a confirmed figurine keeps it as long as the house can follow it.

## A newcomer

When something appears that the house does not recognize, it asks at once, aloud and on every phone at the same time: "There's a new person in the living room: who is it? Viola, Rosaria or Mister Braun?". For an animal, a car or an object the question changes ("There's a new car in the garage: what shall I call it?"). It proposes the registered characters of the right kind that are not already in the house, closest colours first, then those whose colours it has not learned yet.

- **Aloud**, with no Talk button: say one of the names proposed, or a new name ("the name is Luca"); the house repeats a new name and asks for confirmation ("The name is Luca, right?").
- **From a phone**: tap a name on the banner, or type a new name and tap **Add**.
- The first answer wins, from either; when it arrives, the house stops listening.
- If what it asks about disappears before the answer (it was a reflection, or somebody took it away), the question is withdrawn from the phones and the house stops listening.

With a new name the house creates the character, with the kind it guessed (it can be corrected under **Characters and objects**) and the colours it sees. With a registered name it updates that character's colours at once with what it sees, so next time it recognizes it by itself, even if it was registered under another light. A registration in progress from the web app comes first: while it waits for its figurine, the house does not ask this question.

## Privacy

- **Everything around the house is blurred** on every image that leaves the board (the stand, the visitors, their phones), as soon as the house knows where the base is.
- **The bathroom is blurred** by default on every image that leaves the board: the live view, snapshots, dataset captures and recorded sequences. The staff can turn it off in **Settings → Bathroom blurred in the live view**. The blurred area is the footprint of the bathroom at floor level and at the top of its walls, plus a margin, so nothing inside shows whatever its height. The area is computed from the calibration. Before the calibration the house assumes the camera is mounted as designed and blurs a wider area around where the bathroom should be: calibrate before the house is open to visitors, so the blur fits the bathroom exactly.
- The microphone records only while the house is listening; the audio stays in memory and is never saved.
- Nothing leaves the board: no internet, no cloud. Positions are kept for 24 hours and events for 7 days.

## Datasets and recordings

The house does not need training, but the staff can collect images for other projects, for example to train a detector. In **More → Calibration → Dataset**:

- **Capture** saves the current frame; **Burst (10)** saves ten in a row. Each image (640 × 480 JPEG, bathroom blurred) gets automatic labels: a box around every object the vision found, with the kind and the name of its track; hands are left out.
- **Download the dataset** exports a zip with `images/`, `coco/annotations.json` (COCO format, categories person, dog, cat, animal, car, object, with the character's name as an attribute) and `yolo/` (`classes.txt` and one label file per image in YOLO format).
- **Record a sequence (60 s)** saves, in `var/recordings/rec-DATE-TIME/`, every analysed frame as a blurred JPEG, a `detections.jsonl` file with the objects and tracks of each frame, the calibration and the empty-house reference. Sequences like these are used to test the tracking on a PC: `.venv/bin/python scripts/replay.py var/recordings/rec-DATE-TIME` runs the current vision code on the recorded frames and prints what it sees next to what the house saw at the time (`--video out.mp4` also writes the frames with the tracks drawn).

Next: [voice](08-voice.md).
