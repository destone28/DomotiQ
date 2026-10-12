# 7. Recognition and identities

The house recognizes people, pets, the car and objects with **classical computer vision**, without training a model. Seen from the pole, a figurine's base is only about a dozen pixels across at the analysis resolution, the number of characters has no limit, and whoever uses the house adds new ones at any moment. A trained detector would need hundreds of labelled images for every new character; the classical method registers a character in seconds and fits in one CPU core of the UNO Q.

**Machine learning** is used in one place only: when a character is registered with a photo, a **YOLOX-Nano** object detector trained on the COCO dataset looks at the photo and proposes what kind of thing it is.

## How the house sees

The vision runs in a separate process, so a slow frame or a camera problem never slows down the web app or the voice; if it stops, it starts again by itself.

1. **Capture.** The Logitech C270 delivers MJPEG frames; the house analyses them at 640 × 480, 7 to 10 per second on the board. Exposure, white balance and gain are locked, so the colours do not shift when figurines and coloured lights come and go. The values are found by measuring the pictures: the house lets the camera adjust automatically on the empty house, measures brightness and colours, then looks for the manual values that give the same picture, a quarter darker. What the colour temperature of the camera cannot correct (some warm, greenish lights) is corrected by a fixed gain on each channel. Until the light is set the house recognizes nothing, and says so in *Diagnostics*. If the hall light then changes a lot, the camera sets itself again (see *Nothing moves by itself*).
2. **The empty house.** At calibration the house stores the median of 20 frames of the empty house, furniture included. Everything that differs from it is a figurine, the car, an object or a visitor's hand.
3. **Difference in Lab colour space, with light correction per room.** The room lights of the house are coloured, and the hall light changes. Each pixel is corrected with the gains of its own room's light: one gain per colour channel, estimated on the free floor of the room as the most common ratio to the empty house (so a figurine or the car does not bias it), and the one closest to the previous frame when two are possible. Across a doorway the gain passes gradually from one room to the other. The house tells the vision every time it changes a light.
4. **Shadows do not count.** A shadow is darker but keeps the colour of the floor.
   **Tolerance per pixel.** Some spots flicker more than others: the lawns, the edges of the furniture, dim corners, the whole house when the hall is dark and the camera raises its gain. When the empty house is saved, the house measures the flicker of each pixel over the 20 frames and saves it next to the image (`noise.npy`); without that file it learns it from the first quiet frames after a start, then updates it slowly where no presence stands, and learns it again when the camera is set again. A blob counts only if somewhere it stands out by 5 times the flicker of its pixels, and then it counts whole: a figurine on a flickering lawn keeps its shape, a blob made of flicker alone goes. Under the lab light the flicker is below the fixed thresholds and nothing changes; with a picture two or three times noisier it removes 60 to 95% of the flicker blobs without losing any figurine. It costs about 2.5 ms per frame.
5. **Masks.** The vision looks at the base of the house only: what is around it (the table, the hands of visitors before they come in, phones) does not count. Inside the base, zones that are not floor are ignored: the wall lights, the tree canopy, the camera pole, the tops of the walls, the intercom totem and the boards on the walls of the utility room (the UNO Q, which stands out a couple of centimetres from the wall, and the hub), whose LEDs go on and off, each projected at the height where it really is.
6. **Objects.** After a morphological clean-up, each connected blob becomes an object with its area in mm², its median colour and a histogram of its colour, its elongation, and its nearest and farthest points from the point under the camera.
7. **Where it stands (parallax).** The camera sees a standing figurine from above, so the figurine appears stretched away from the point under the lens: its nearest point is the front of the feet, its farthest point the back of the head. Brought down by the figurine's height, the head gives the position of the feet too, so a figurine is placed correctly even when its feet are hidden behind a wall. The car, a box rather than a figurine, is placed at the middle of what is seen. On synthetic test scenes the position error stays below 12 mm. A figurine on the bed, the sofa, a table or a bench is measured from the height of that furniture: the house knows it stands on it because its feet, brought up to that height, fall on the furniture. Not on the roof of the car, though: a figurine put on the car merges with the car. The house also knows which piece of furniture a character stands on, and says so (chapter 8).
8. **Hands.** A blob at least as big as an arm (2,500 mm² inside the base) entering from the edge of the base is a visitor's hand, except at the garage gate, where the car drives in. The car parked against the back wall of the garage, its roof over the edge, is no hand either: a "hand" almost all in the garage is shown to the network, and if it sees the car there, sure, it is no hand. Every piece close to the hand belongs to it, whatever its size: the arm cut by wall tops and wall lights, the fingers, the shadow. A "hand" that stays perfectly still for 8 seconds is instead something lying on the edge (a module, a cable), and it becomes part of the empty house. The figurines the "hand" covered stay out of the empty house: the glow of a wall light the house has just switched on, for instance, can become one big still "hand" with the figurines of the room inside it, and the house keeps them where it last saw them alone. A "hand" almost all in rooms the house has just lit, which appeared with the light, is the glow of that light and does not stop the house; the lit rooms are also left out of the measure with which the webcam follows the light of the hall.
9. **Tracking.** Objects are matched to the tracks of the previous frame with the Hungarian method, on a distance that combines position, colour and size. **Nothing moves by itself, not even on the map:** with no hand around lately a track does not jump more than 30 mm, however long it was hidden, and the place of a still character does not change (a shadow or a light on its blob does not move it); in the seconds after a hand has been around the place is updated once, where the hand left it. A followed character that is not seen for a moment (a light, two figurines touching) stays where it was for up to two minutes, a known character up to a quarter of an hour. An unknown blob right next to a character, coloured like it, is a piece of it (a figurine lying across the tree trunk is seen as two).
10. **Carried by hand.** When a figurine disappears under a hand, its track becomes *carried* and keeps its identity; when the hand has gone, the figurine that reappears where the hand worked is the same character. If the hand left only one new thing, that is the character it held, even lying down or on the bed with slightly different colours. If the hand only passed over it, the figurine finds its track again where it was. If it was put down against another figurine and the two are seen as one blob, it stays hidden behind the other until they part. If the hand leaves without putting it down, the character leaves the house 2.5 seconds later.
11. **Who is it.** Each registered identity has a **colour signature**: a histogram of the a\* and b\* colour axes of the Lab space (where lightness is kept apart, so a shadow or a dimmer light changes little) plus the median colour. For white, grey and black figurines lightness weighs more, since it is the only thing that tells them apart. Identities are unique, so the assignment of identities to tracks is solved for all of them together; an identity is given after two frames of agreement. Size counts too: the car is never taken for a figurine nor a figurine for the car, and a size very different from the one learned counts as less alike. Each character learns its **poses** on the board (up to six: lying down, on the bed, under another light), each with its colours, size and shape, and the comparison is made with the closest one; a new pose is added when the house is sure of the character, still and seen whole, and at once when somebody says who it is. A pose, though, shows the same figurine from another side, not another colour: it must have the colours of the character, more than those of anybody else. A pose learned on the wrong blob (the LEDs of a board, another character nearby) would make the house see that character everywhere: the house does not learn it, and forgets at start-up those learned before this check. In the same way the registered colours and size learn only from a blob that closely looks like the character. Comparing a blob with every pose of every character is one single computation, made once per frame. A character much more like one than like all the others is recognized with less close colours too, but only in the first 10 seconds of a new track. **Names move only with hands:** a name is never in two places; with no hand around, its holder keeps it while it still looks like it, and loses it only after eight frames in which it no longer does; and a name never goes to a blob far from the last place where that character was seen, unless a hand has been over that place or carried it. So a character no longer seen stays where it was, instead of turning up on some reflection on the other side of the house. **History:** the house remembers where each character was last seen and whether a hand has been over that place; before asking who something new is, if a character stood right there and no hand touched it, it is still that one and gets its name back. While a figurine is followed with confidence, its signature is slowly updated with what the camera sees.
12. **Which room.** The room is the one under the point where the figurine stands, with 15 mm of tolerance on the doorways, so a figurine on a threshold does not flicker between two rooms.

The result is a list of tracks, each with a position in millimetres, a room, a kind and, when known, an identity. The rest of the house (lights, rules, voice, web app) works on this list.

**At rest.** Analysing a frame takes about 180 ms on the board. When the house is still (no hand for 25 seconds, no light of the house changing or animated, nothing pending) the house first compares each frame, shrunk to 80 × 60 in grey, with the last one analysed: if no point changed by more than 6 grey levels, the frame is the same and is not analysed again. The comparison takes a fraction of a millisecond, a hand changes it at once, and at least one frame a second is analysed in full anyway. This leaves the processor free for the voice. In **Diagnostics**, on the webcam line, *at rest 60% of the frames* tells how many frames the house left alone (during a party it shows *paused for the party*).

**Priorities.** The vision is the continuous work of the board: when the processor is not enough for everything, it gives way to the voice, which runs in the same service (its process has a lower priority). Among the services the house comes first, then the voice synthesis, the language model last.

### Nothing moves by itself

In a diorama every change is made by a hand: a figurine comes in, goes out or moves only if somebody picks it up. The house uses this rule not to see presences that are not there.

- **While a hand is over the house**, and for 0.6 seconds after it has left (its shadow, the figurine still swinging), the house counts nothing new and makes nobody disappear. A figurine the hand does not hold stays where it is: its track does not jump onto another blob.
- **On the map a figurine moves only when a hand comes close to it** (within 5 cm), even by a few millimetres. With no hand close, its place and the furniture it stands on stay as they are: a shadow, the light of the hall, its blob now and then merging with something next to it do not move it. On casa1 Viola's blob jumped 15 mm back and forth while nobody touched her, and the map followed it. While the hand works, the figurine follows what is seen. When the hand has left (after 0.6 seconds), its place becomes the median of the first 10 frames, about a second: the median leaves out the crooked frames with the shadow of the arm. The same goes for a figurine that has just appeared. Measured on four recordings (`scripts/settle_bench.py`): with 10 frames the place fixed stays within 2 mm of the real one, with 8 it gets to 6 mm, with 3 to 12 cm.
- **Then new things are looked for only where the hand worked**, for 3 seconds, and only what the hand brought is born: something that already differed from the empty house before the hand came is not new. It must also be compact (at most 3.5 times longer than wide) and stand out clearly from the floor, by colour or by being much darker or lighter: the strips the light draws at the foot of the walls or along the edge of the sofa, and faint patches, are no presences. Nothing is born that lies entirely on a wall, nor anything small right on the edge of the base.
- **Double check.** Before showing something new on the map and asking its name, the house checks twice that it is sure. Its certainty goes from 0 to 100% and combines four measures: how often it is seen, how still it stands, how much it stands out from the floor, how compact it is. It must be over 80%, and again one second later without having dropped below in between. For two minutes, in the room where somebody has just said there was nobody (aloud, with **Nothing there** or with **Not really there: remove**) or where the house has just discarded a reflection, 92% is needed, checked 2.5 seconds apart.
- **Something unknown that jumps**, even by a few millimetres, or vanishes and comes back several times a second with no hand around, is no figurine: it is a reflection or an LED. It leaves the map, nothing is born there for 30 seconds, and for two minutes the stricter double check holds in that room. This does not apply in rooms with animated lights (a party).
- **A change with no hand around** (a reflection, the hall light, a lamp at the side) never becomes a presence. Faint changes become part of the empty house after about 3 seconds. What looks like a figurine never does, so taking it away leaves no ghost. The exception is something that clearly stands out, appears with a hand around and stays for 2 seconds: a figurine put down while the house was waiting.
- **The place left** by a figurine that had become part of the empty house (for instance after the house learned the empty house again), once it matches the saved empty house again, is no presence: the empty house takes it back.
- **When the house changes the light of a room**, for 2.5 seconds its glow on walls and floor is not taken for a presence.
- **When the hall light changes** the characters stay as they were just before, and the house learns the empty house again in the new light: see *The light of the hall*.
- **At start-up** the house waits for the lights to stand still (the microcontroller sends them again), then recognizes the registered characters that are in the house and the car: only those that closely look like a character and are shaped like a figurine, so the glow of a lamp or the LEDs of a module do not become somebody. A new character that was already in the house, or one lying down that looks less alike, shows up as soon as somebody moves it.
- **A presence followed for less than 2.5 seconds** is noise, even if it took a name: it does not stay on the plan as hidden.
- **Alarms only for sure presences.** The alarm rules (chapter 9) count a character the house knows, or something unknown that has stood there, still and clearly visible, for at least 6 seconds. A blob just born sets nothing off.
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

1. **Characters → + Add**, or tap an unknown figurine on the **House** screen and then **Register**.
2. Type the **Name**. Optionally tap **Take or choose a photo**: one front photo is enough; it is shown in the list and used to guess the kind. The phone shrinks it to 1024 pixels before sending it. Tap **Next**.
3. *Put it down on a free spot of the house: I'm looking for it…* The house looks for something it sees but does not know. With exactly one candidate it takes it; with more than one it says *I see more than one new thing: tap the right one on the plan*; with none it waits. After two and a half minutes without a result it gives up: *I didn't find anything new. Try again.*
4. *Found it! What is it?* The house shows its guess (*It looks like: dog*, with a proposed name for objects), any [warnings](#warnings), and the six kinds. Choose and tap **Save**.
5. *Marco is registered. From now on I'll recognize it.*

### With the intercom

1. A visitor presses **Intercom** on the totem. A doorbell rings and the house asks "Chi è?" / "Who is it?".
2. **A registered name**: "Hi Marco, come on in!". The first figurine that appears after the bell, in the next 3 minutes, on the driveway or in a room of the house (not the garage), gets that name, whatever the camera took it for (a figurine often looks like an object or an animal to it), and the house does not ask who it is. If the name belongs to someone already inside, the house says so ("But Marco is already in the kitchen!"). If the camera clearly recognizes the figurine that comes in as somebody else, the house says it ("But you look like Sofia to me, not Marco!") and keeps the identity it sees.
3. **A new name**: "I heard Marco, right?" After a *yes*: "Nice to meet you, Marco! Come in through the door." The first figurine that appears after the bell, in the next 3 minutes, on the driveway or in a room of the house, becomes Marco, a person, with the colours the house sees, with no further step and no question; even if the house had given it a name it was not sure of. A figurine the house recognizes for sure as somebody else does not count, and neither does one that was in the house before the bell.
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
- Anyone can rename or delete a character from its card. A deleted character leaves at once the presence that carried it, the open questions that proposed it and the labels of **Image training** (it no longer teaches the network a character that is not there). It stays in the bin for 24 hours and can be restored from **More → Settings → Bin**; if its name was taken in the meantime, it comes back with " 2" after the name.

## Warnings

At registration the house checks what could make the new figurine hard to recognize, and says so on the confirmation step:

- *Its colour is very close to the floor / the lawns / the walls: I may not see it well.* The difference from the empty house is small, so parts of the figurine may be lost.
- *It keeps disappearing: try moving it to a clearer spot.* The figurine was detected in fewer than half of the frames since it appeared.
- *It looks just like Marco: I will tell them apart only by following them.* Its colour signature is almost the same as a registered one.

None of these prevents the registration.

## Same-colour figurines and doubts

Two figurines of the same colour are told apart only by following them. Continuity of movement keeps them distinct: if only one of the two is picked up and put down elsewhere, it must be that one, since the other stayed in view.

When the thread is lost (both picked up together, the two touched, one reappeared far away, or the house just started) the track becomes **uncertain**. The house then:

- asks on every phone, with a question such as "Is it Marco or Leo in the kitchen?", one button per name and **Both**, if the figurines touch;
- asks aloud too, if its talkativeness allows it, and right after listens for the answer by itself, with no need for **Talk**: just say the name, or "both of them". The first answer wins, aloud or from a phone;
- without an answer within 60 seconds, keeps its best guess, marked as uncertain: a **?** on the plan, and "Marco is in the kitchen. I think." in voice answers.

**A name is never in two places.** Before asking, the house leaves out of the candidates whoever is already recognized somewhere else in the house (unless a hand has been where it was), whoever was last seen far from there with no hand having been there since, whoever is of a size too different from what it sees (more than four times bigger or smaller than all of its poses; a figurine is never the car, the car is never a figurine), and the car out of the garage unless it is certain of it. If only one is left, the house decides by itself without asking: with Rossellina in the kitchen, the new figurine in the living room that looks like both Rossellina and Rosaria is Rosaria. If nobody is left (Rossellina is in the kitchen and Rosaria in the bedroom), that figurine is neither of them: the house treats it as a newcomer and asks who it is. If the doubt clears while the question is open (Rossellina shows up in the kitchen), the question is withdrawn from the phones and the house stops listening.

The same rule holds for what the house shows and says. If two presences come with the same name (for instance one still in a hand and one just put down), the name stays with the one in sight. A name given from the web app, by voice or at the intercom stays where it was given and leaves where it was at once, even in the half second when the vision, which runs in a separate process, does not know it yet; then the names are the vision's again, and the house never puts back a name the vision has taken away from a presence.

**The car stays in the garage.** The car is never proposed for a figurine, or for something out of the garage, unless the house is certain of it: as big as a car, still and clearly seen for 10 seconds.

It asks again about the same figurine at most every 30 seconds. An answer, a registration or an intercom entry **confirms** an identity: a confirmed figurine keeps it as long as the house can follow it.

## A newcomer

When it is sure there is something it does not recognize, the house asks at once, aloud and on every phone at the same time. It also says what it thinks it is, so that it can be corrected: "I see a new person in the living room, right? What's their name?". A person is asked the name, with no registered person proposed. For an animal, a car or an object it proposes the registered ones of the same kind that are not already in the house ("I see a new dog in the garden, right? Is it Fido or Birba, or what's its name?"); for an animal it never proposes a person. **The car lives in the garage**: inside a room of the house it never asks about a new car (it calls it "an object"); for something as big as a car out of the garage (more often a light, a shadow or figurines huddled together) the house asks nothing unless it is certain: seen still and clearly for at least 10 seconds.

**Aloud**, with no Talk button, any sentence will do as an answer. The house understands it and replies accordingly:

| Answer | The house |
|---|---|
| a new name ("Marco", "the name is Marco", "it's my brother Andrea") | asks to confirm the name together with the kind ("A person called Marco, right?"), then "Nice to meet you, Marco!" |
| a registered name ("it's Viola"), even heard with a letter wrong ("rosario" for Rosaria) | assigns it and learns its colours, if they look like the character's. If that character is in sight somewhere else in the house, the newcomer was not there: "Viola is already in the living room: so I saw wrong here" |
| "both of them", "both", "Viola and Rosaria" | two figurines touching are one blob: it marks both of them present, one hidden behind the other until a hand parts them ("Oh, there are two of them: Viola and Rosaria!"). If one of them is in sight elsewhere, only the other is here; if no names were said and the question proposed none, it asks which ones |
| the right kind ("no, it's a dog", "it's a cat called Micia") | corrects the kind and asks the name, if missing |
| yes or no | after a yes it asks the name, after a no it asks what it is |
| "there's nobody", "that's my hand", "it's a shadow" | forgets what it saw: the blob becomes part of the empty house and nothing is born there for 30 seconds. For two minutes the stricter double check applies in that room |
| "I don't know", "never mind" | leaves the question to the phones |
| "wait" | waits and listens again |
| a command or a question ("what time is it?") | answers it, then asks the name again |
| a joke or anything else | asks the name again; the second time it lets it go |
| talk that is not about the newcomer ("...to make the model faster") | as a joke: the kind the language model says counts only if the sentence names it |
| silence | asks once more, then leaves the question to the phones. When two newcomers in a row get no answer at all, for three minutes the house asks about them on the phones only |

Short, common answers are understood by rules, at once. Any other sentence is classified by the local language model (chapter 8). On the board that takes 3 to 6 seconds, and meanwhile the house says "Let me think..." and the buttons breathe.

- **From a phone**, tap a name on the question, **Both** when more than one name is proposed, or pick **Someone already known…** among all the characters and objects the house knows and tap **This one** (the name moves there from wherever it was), or type a new name, choose the kind and tap **Add**. **Nothing there** makes the house forget what it saw.
- The first answer wins, from either; when it arrives, the house stops listening.
- If what it asks about disappears before the answer, the question is withdrawn from the phones and the house stops listening.

With a new name the house creates the character, with the kind said (or guessed) and the colours it sees. With a registered name it updates that character's colours at once with what it sees, if they look like the character's, so next time it recognizes it by itself; an answer given about the wrong blob gives the name but does not change how the character looks. A registration in progress from the web app comes first: while it waits for its figurine, the house does not ask this question.

## During a party

While the house throws a party the coloured lights change at every beat, and the camera sees colours that are not those of the characters. So the house **pauses the recognition** from the start of the party to the end of the light show: the presences stay where they were and keep their names, nothing new is born, nothing disappears, the house asks nothing and announces no moves. The picture in **Live** keeps updating.

When the party is over the house measures the light of every room again, waits for the lights to stand still and takes what it sees afresh, as at a start. Somebody may have moved a character during the party, so for each of them it is as if a hand had been where it stood: a character that was moved is found again and its name follows it even far from where it was; if the house does not recognize it, it asks who it is.

## Correcting the house from the web app

- **Who it is.** On the card of a presence (**House** page), **Who is it?** or **Someone else: change** opens the list of every character and object the house knows, with a new name at the bottom. Choosing a character already known moves the name to that presence and away from the one that had it by mistake; the house learns that look as one of its poses even if it is unusual (another light, a character lying down), up to a colour distance of 0.6 instead of 0.45, and remembers it after a restart. An answer by voice, which may be about the wrong blob, stays more careful.
- **Unrecognized item.** A figurine the house did not see being put down, or took for the empty house, is not followed. **Unrecognized item**, on the **House** page (tapping the spot on the plan) or in **Live** (tapping it in the picture), tells the house where it is: around that spot, for about 3 cm, the house takes back the empty house as it was saved, so what stands there differs from it again, makes it a presence followed at once and asks who it is. Any "nothing there" said there a moment before is cancelled too. If it sees nothing different from the empty house there (the item was already there when it was saved), move it a little and try again.

- **Learn the look again.** On the card of a character (**Characters**) it makes the house forget its colours, poses and size. Name, facts and rules stay. The first time somebody says who it is (tapping the figurine on the plan, answering a question of the house, or aloud) the house learns the look it sees then. Useful when the figurine is another one: a character painted again, or a house made like another one with the backup but with its own figurines, where the house would look for the colours of the figurines of the other house, under another light, and would not recognize its own or would mix them up.

## The light of the hall

The camera has its exposure and colours locked on the light in which the empty house was saved.

**The gain follows the light.** While the house looks, every half second it compares the light of the rooms with the empty house in use, as it was photographed: in each room the free floor counts, away from the characters and the hands, and among the rooms the middle one counts, so a room whose light just went on moves nothing. If they differ by more than 5%, it moves the gain of the webcam one step, at most 8% of light at a time. When the light of the hall changes at once, the house holds the characters, the gain takes longer steps (up to 25%) and only then does the house learn the empty house again. So the evening coming or a lamp switched on are followed with no gap in the pictures: the full setting of the webcam, about 10 seconds without pictures, starts by itself only when the gain is already at its limit, and never in the dark if it was already made in the dark. *Diagnostics → Light of the webcam* shows the gain, the steps of the last hour and any pause (hands over the house, start, dark, party, rooms covered, lights of the house changing). It is switched off with `camera.follow_light: false` in the settings.

**How it notices.** The house notices by itself when the light of the hall changes:
- the brightness of the picture changes by more than 12% within 2 seconds (a light switched on or off);
- the brightness stays more than 15% away from the one the empty house was last learned in for 3 seconds (the evening coming slowly);
- much of the house changes with no hand;
- "hands" cover almost half of the house and the brightness has changed too (two real arms cover a quarter of the house at most and hardly change the brightness: they are the walls, lit another way);
- the light goes beyond what the correction of the rooms can follow;
- the camera is set again.

It does not count while a light of the house has just changed (its glow is measured room by room), nor while the house looks for the characters at a start.

**What it does.**
- **The characters stay.** From then on the characters stay exactly as they were just before: the same names, the same places, nothing is born, nothing disappears, and the house does not look. What seemed "taken by a hand" in the last seconds stays where it was: those hands were the light.
- **The brightness.** If the picture is below 70% or above 143% of the empty house, the camera is set again at once.
- **The map.** Once the brightness stands still (within 2% for a second), the house learns the empty house again from the median of the last 5 frames, except around the characters.
- **Back to work.** A second later it finds the characters again in their places and goes back to looking: a few seconds in all.

Measured on casa1: the room light switched off brings the picture to 45-57%, while the scenes of the house (cinema, night) never go below 95%.

A covered or dazzled camera is never learned as the empty house, and neither is a hall that is too dark (mean grey of the picture below 25 out of 255; with the light on it is 55-65). Nor can the empty house be saved in the dark: the web app asks to turn on the light. The characters stay and the web app warns *The webcam sees almost nothing* (see chapter 11). When the light comes back, the house looks again at what is in sight, as after a party: in the dark somebody may have moved a figurine, and the house finds it in its new place, with its name. Nor is a knocked camera: before learning, the house checks that walls and furniture are where they were. If they are not, it learns nothing and asks for a new calibration at once. *Diagnostics* shows when the light is changing and how many times the house adapted.

**A very dark hall.** Even when the picture is too dark to be learned, the webcam keeps raising its gain, and only towards the light, as long as it can: before, the house waited for the light to come back, with the gain left where it was (on 10 October at 28 of 255) and the house blind. At the highest gain the webcam also uses the exposures beyond 625, where it multiplies the picture (about 1.7, 2.3 and 2.9 times, still at 15 frames a second); when the light comes back it leaves them first. Then the noise of the webcam is high, and the house learns it again even if it sees "hands": at that gain they are almost always the noise itself. In a hall that dark, dark figurines on the dark floor (the black dog, a red figurine in the shade) may no longer stand out: the house does not see things that are not there, but it may not see all those that are. With normal light everything is as before.

**The empty house in more lights.** In **Calibration**, with the house empty:
1. **Photograph in every light of the house.** The house shows its lights one after the other (all off, all on, one room at a time, the scenes) and in each saves a picture of the empty house, in about a minute.
2. **Add the light of now.** Switch on one at a time the lights of the hall the house does not command (lamps, LEDs, the light of the window) and press the button for each.

When the light changes, and at every start, the house compares with the most similar picture, after measuring the light of every room, and learns nothing from what it sees: a figurine it is not following cannot end up in the empty house. If no picture is similar enough, it learns as before. The pictures are cleared when the corners are set again. After moving a piece of furniture, press *Clear* and take them again.

**A start in another light.** If the house is switched on, or starts again, in another light than the one the empty house was saved in, the colours of the figurines are not those registered. At a start the house also takes what the network recognizes as a character, and if it learns the empty house again while it knows no presence yet, what stands out does not join the empty house and the house looks again at what is there. On casa1, on 7 October, before this fix every start in another light had learned all the figurines as part of the empty house: they were no longer seen and, once moved, they left ghost presences where they had been. It is still good practice to save the empty house again when the light of the hall changes for good. If a light changes while the house is looking (the light that follows the characters, for instance, lit for one just found), from then on it takes only what the network is sure of: the glow of a lamp on the walls has the colours of characters.

While the camera is being set (about 10 seconds, with no frames) the presences stay where they are on the map, also in the instant between the end of the setting and the first frame. Before, they all disappeared and came back, and the house said goodbye and welcomed everybody again ("arrivederci Viola, a presto Mister Brown"). When a setting does not bring the picture back close to the empty house (a hall darker than the camera can follow), the next one waits twice as long, up to a quarter of an hour: on casa1 the camera was set every 70 seconds, always with the same values.

In a very different light the walls and the edges of the furniture look another way and may look like big blobs coming in from the edges, that is hands. That is what happened on casa1 on the evening of 6 October: for 30 seconds the "hands" "took" three characters and moved them to other rooms, then some fifteen cars and animals were born where they had been. Now the change of the light is recognized first, and the empty house learned again has no such "hands". The earlier rules stay: "hands" that stay without a break for 30 seconds are no hands, and if the light is close to the one of the empty house they join it (except where a character stands).

## The network that knows the figurines

Besides the difference from the empty house and the colour signature, the house always has a second opinion: a small neural network trained on the figurines of this house, seen by its webcam under different lights and shadows. It looks at the crop of a blob and says which character it is, or "niente" (nothing: a light shining on a wall, a shadow, a module). On the board every crop costs about 10 ms, so the house uses it only when needed:
- **A new blob** the network sees as "niente", sure enough, does not become a presence. Not while a new character is being registered: the network does not know it yet.
  - **"Niente" as the first answer.** Even when the network is not sure, a new presence is announced only when its latest answer is not "niente": the presence waits, and the network looks at it again every half second. In the entries of **Image training** of 7-10 October, looked at one by one, none of the 46 real figurines announced had "niente" as the first answer, while 144 of the 227 false presences had it (furniture, grilles and lawns under another light). A character registered after the network was trained is not judged by it.
  - **The kind.** A nameless presence takes the kind of the character the network sees, when it is at least 80% sure: the small round figurines, taken for animals by their shape, were asked about as "a new animal".
  - **The threshold.** Every network is sure in its own measure, so the threshold is measured when it is trained: just above the most "niente" real figurine of the blocks left out, written in the network's `figures.json` (0.75 for the one of 7 October evening). Without it, 90%.
- **A character that no longer looks like its colours** (another light) keeps its name while the network, at least 80% sure, still sees it.
- **A wrong name from the colours.** The network also looks at the presences with a name, every 2 seconds. If it is 95% sure twice in a row that a presence is another character, the name goes to it, even from another presence that held it, unless somebody gave that name or the network sees that character in the other presence too. A character does not learn a new look when the network, at least 80% sure, sees another character there. On the blocks left out of its training, at that certainty the network of 12 October was wrong on 5 figurines out of 4,089.
- **A newcomer** takes the name of a character nobody else holds, instead of being asked "who is it?", when the network is 95% sure of it twice in a row.
- **Two characters of alike colours** (Rossana and Rossellina, Mister Blu and Viola) are told apart by the network, when it is 95% sure twice in a row, instead of by their colours. Before asking "who is it?" about a doubt between two alike characters, the house waits 2 seconds for the network.

The network also looks at the figurines taken "late" (put down while the house waited). It is always on, with no switch in the settings; *Diagnostics* shows how often it helped. Without the network file (`models/vision/figures.onnx` and `figures.json`) the house works as before.

**The consent of the network**, always required: a new presence is announced only when the network has seen a figurine, twice in a row. It is the way to have no false presences. The price: a figurine the network does not know is announced only while it is being registered (**Characters → + Add**), and in low light a figurine may take a little longer.

A new presence is announced only after the network has looked at it (one frame later at most), and the name of a character just taken by a hand does not go to a blob the network has just seen as "niente".

**The continuous collection** (Settings → Continuous collection of pictures for the network, off by default) keeps what the webcam sees, with the outside blurred, in `var/collect`: folders of 10 minutes in the format of the recordings, one picture every 5 seconds and two a second while something happens. Beyond the chosen space (500 MB by default) the oldest folders are deleted. They are the data to train the network again with the real lights and positions of the place where the house stands; every folder also keeps the empty house of that moment (`reference.jpg`), useful to check that the house has not learned a figurine as part of the empty house.

**Image training** (More → Image training) teaches the neural network to recognize presences and absences in the house better: it keeps every new presence, every name given and every blob refused by the network, with its picture. Saying for each one whether it was right, or what it really was, gives examples verified by a person for the next training (`build_crops.py ... --journal <copy of var/journal>`).

**Training it.** The network is trained on the PC with the programs in `scripts/figures/`, from the recordings of the house (**Calibration → Record**). Every recording saves, for every recognized character, the box of its blob: that is the crop with its name.
1. With all the characters in the house and recognized, record a few minutes moving them to different rooms and positions, under different lights (the hall light, a lamp at the side, the scenes of the house) and with the shadows of people nearby.
2. Copy `var/recordings/rec-*` (or `var/collect/rec-*`, the continuous collection), `var/config/identities.json`, `var/domotiq.db` and `var/calibration` to the PC, then:
   ```
   python scripts/figures/web_fixes.py domotiq.db identities.json fixes.json --since "2026-10-07 00:00"
   python scripts/figures/build_crops.py <recordings> identities.json crops [--journal journal] [--fixes fixes.json]
   python scripts/figures/empty_crops.py calibration empty   # the empty house under every light: all "niente"
   python scripts/figures/preview.py crops preview.png      # check the labels by eye
   python scripts/figures/train.py net crops empty --only 2 --niente-weight 2   # test on a block left out
   python scripts/figures/train.py net2 crops empty --drop net/suspect.json --niente-weight 2
   ```
   - **The corrections made on the plan.** `web_fixes.py` finds in the database of the house what was corrected on the plan of the web app: a presence dismissed was "niente" all the time it stood at that place; a presence given a name was that character, also while the house called it something else or nothing. With `--fixes` these corrections count more than the labels of the house.
   - **The empty house.** `empty_crops.py` makes "niente" crops from the photos of the empty house (the saved one and those with the lights), at the sizes of real blobs. They teach the network the furniture of the house even before there are mistakes to correct: on a house with an orange sofa the network of 7 October saw figurines in 25% of the crops of the empty house, the one trained with these photos too in 8%.
   - **The weight of "niente".** Every class is seen about as often; on top of that a mistake on a figurine weighs more, because "niente" has many more examples. With `--niente-weight 2` a mistake on "niente" weighs twice: on the last block of time left out, the real figurines with "niente" as the first answer went from 0.8% to 0.4%, and the "niente" crops taken for figurines from 4% to 1.7%. With 4 the false presences drop further, but Mister Green lying on the lawn becomes "niente" in one crop out of eight.
   - **The second training** leaves out the crops the network is very sure carry another label (the house was wrong there). Not for a name given by hand: on 7 October the network called Rossellina, lying on the bed, "Mister Blu", because the house had called her that before the correction.
3. Copy `figures.onnx` and `figures.json` to `models/vision/` on the board and restart the house.

PyTorch is needed on the PC (not on the board). The classes are the names of the characters: after a new character, or for the other house with different figurines, the network must be trained again.

## Privacy

- **Everything around the house is blurred** on every image that leaves the board (the table, the visitors, their phones), as soon as the house knows where the base is.
- **The bathroom is blurred** by default on every image that leaves the board: the live view, snapshots, dataset captures and recorded sequences. It can be turned off in **Settings → Bathroom blurred in the live view**. The blurred area is the footprint of the bathroom at floor level and at the top of its walls, plus a margin, so nothing inside shows whatever its height. The area is computed from the calibration. Before the calibration the house assumes the camera is mounted as designed and blurs a wider area around where the bathroom should be: calibrate before the house is open to visitors, so the blur fits the bathroom exactly.
- The microphone records only while the house is listening; the audio stays in memory and is never saved.
- Nothing leaves the board: no internet, no cloud. Positions are kept for 24 hours and events for 7 days.

## Datasets and recordings

The house does not need training, but images can be collected for other projects, for example to train a detector. In **More → Calibration → Dataset**:

- **Capture** saves the current frame; **Burst (10)** saves ten in a row. Each image (640 × 480 JPEG, bathroom blurred) gets automatic labels: a box around every object the vision found, with the kind and the name of its track; hands are left out.
- **Download the dataset** exports a zip with `images/`, `coco/annotations.json` (COCO format, categories person, dog, cat, animal, car, object, with the character's name as an attribute) and `yolo/` (`classes.txt` and one label file per image in YOLO format).
- **Record a sequence (60 s)** saves, in `var/recordings/rec-DATE-TIME/`, every analysed frame as a blurred JPEG, a `detections.jsonl` file with the objects and tracks of each frame, the calibration and the empty-house reference. Sequences like these are used to test the tracking on a PC: `.venv/bin/python scripts/replay.py var/recordings/rec-DATE-TIME` runs the current vision code on the recorded frames and prints what it sees next to what the house saw at the time (`--video out.mp4` also writes the frames with the tracks drawn).

Next: [voice](08-voice.md).
