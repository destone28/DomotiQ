# 8. Voice

The house listens and speaks in **Italian and English**, entirely offline. Visitors use the three buttons of the totem: they hold **Talk** to ask a question or give a command, press **Intercom** to ring the doorbell and introduce themselves, and press **Language** to switch between Italian and English.

The voice chain has four parts:

- **Speech recognition**: Vosk, with the small Italian and English models, on the board.
- **Understanding**: a fast rule-based parser for the common phrases; the sentences it does not understand go to a small language model, Qwen2.5-0.5B-Instruct running in llama.cpp, which only chooses what to do.
- **Answers**: always composed by the code from the real state of the house.
- **Speech synthesis**: Piper, with an Italian and an English voice.

## The buttons

Seen by the visitor, from the left:

| Button | What it does | Its LED |
|---|---|---|
| **Talk** | Hold it down and speak; release it when you are done. A beep marks the start and the end. There is no need to hurry: the house listens as long as the button is held (up to two minutes). Pressing Talk while the house is speaking interrupts it. With the [word of activation](#the-word-of-activation), just say it. | blinks while the house listens (with the other two) |
| **Intercom** | A doorbell rings and the house asks "Chi è?" / "Who is it?". Say a name, without pressing anything: the house listens for 5 seconds after its question. See [the intercom](07-recognition-and-identities.md#with-the-intercom). | blinks during the conversation |
| **Language** | Switches between Italian and English. All the lights flash for about a second, **green for Italian** and **red for English**, and the house says "Italiano" or "English". | on while the house speaks English |

While the house listens, **all three button LEDs** **blink**; while it works out an answer to say, they **breathe** (the middle one lights up, then all three, then the middle one again, then none); while it speaks they stay **on, steady**. If the microphone opens while the house is still finishing its sentence, they stay steady until it has finished, then blink.

The house starts in Italian. The language can also be changed from **Controls → Language of the house** in the web app, or by voice ("Parla inglese", "Speak Italian"). This is the language the house speaks and listens in; each phone chooses the language of the web app on its own.

During the intercom conversation and the registration by voice, the house listens by itself for a few seconds after each of its questions ("Who is it?", "I heard Marco, right?", "Which room did you put it in?"). Its questions about who is who ("Is it Marco or Leo in the kitchen?", which can also be answered "both of them") and about the time are answered with no button too.

## The word of activation

In **Settings → Voice** you can switch on **Wake up with a keyword** and write the *Keyword*, for example *Casa*. From then on saying the word does what the Talk button does. The three LEDs of the buttons start blinking while the word is still being said: the recognizer reports it word by word, without waiting for the end of the sentence. You can say it all at once, "Casa, turn on the kitchen light": after the word the house keeps listening until the first pause, and what follows is already the request. A short pause after the word is fine too: if you say nothing within a second and a half, the house asks "Yes? What do you need?", listens to the sentence with no button and answers. A single word after the keyword counts as a request only if it means something to the house ("Casa, help!"), not any sound. The Talk button keeps working.

- **Numbers and letters.** The word is matched as the speech recognizer writes it: numbers become words, so *Casa 2*, *casa2* and *casa due* are the same word (in English *House 2* is *house two*). On saving, the web app shows how the house will hear the word and which of its words the speech recognizer does not know: an unknown word cannot be recognized, change it.
- **When it listens.** Only while the house is free: not while it speaks (and for a little more than a second after, since its own voice may say the word), not during a conversation, a question of the house or a question to the characters, and not in silent mode. The microphone stays on while it waits for the word, but the audio is never saved or sent anywhere (the house keeps only the last two seconds in memory, so as not to lose a request said together with the word); while it waits for the word the LEDs stay off, and they blink from the moment it hears it.
- **Mistakes.** A common word like "casa" may come up in a conversation between visitors and wake the house by mistake; a rare word, or two words, makes fewer mistakes. That is why the house makes a check: the free recognizer must find the word again in what was said. If it does not (for instance "cosa facciamo?" heard as "casa"), the LEDs go off and the house does not answer. The noise of a fair may lose a call now and then: the Talk button is always there.

## Talkativeness

| Level | Behaviour |
|---|---|
| **Silent** | Never speaks. The doorbell and short sounds remain; answers and everything else the house would say appear only as subtitles in the web app. |
| **Normal** | Answers, the intercom, alarms and warnings, the important events of the rules, the questions of the house and a line for whoever comes in, goes out or changes room (see *What the house tells* below). |
| **Chatty** | As Normal, plus comments: proposals ("So many of you in the living room: shall we party?" with three or more people there, "Lovely day in the garden: shall I light the barbecue?" with two or more in the garden, at most every 10 minutes, answered with no need to press Talk like the questions), the sentences that rules mark as chatty, such as "The temperature is back to normal.", and the **questions to the characters** (below). |

Set it from **Controls → Talkativeness**, or by voice: "Stai zitta" / "Be quiet", "Parla di più" / "Talk more", "Parla normale" / "Normal mode". Every sentence the house says also appears as a subtitle on the phones and in **Events → Said by the house**.

## Talking without pressing Talk

After **every** question of its own the house listens by itself for a few seconds, with no Talk button: the greeting of a new phone, the questions to the characters, "who is it?" for a newcomer, a doubt between two characters, confirmations. If the answer is not clear it asks once more, and meanwhile the same question appears on the phones: the first answer wins, aloud or from the app, and as soon as it arrives the house stops listening. The microphone opens while the house is still ending its question, and what it hears is thrown away until a third of a second after its last word: an answer said at once ("yes") is not lost while the recorder starts. While it listens, the three button LEDs blink and the phones show *The house is listening…*; while it works out the answer, the LEDs breathe. The question "who is it?" about a newcomer can be answered with any sentence: the house understands it and replies accordingly ([chapter 7](07-recognition-and-identities.md#a-newcomer)). If the house says something else while it listens (a rule, a warning), the answer is thrown away: it could be its own voice. **Talk** and the **intercom** always come first: pressing them interrupts the greeting or the question, and the house listens to the button.

**A new phone.** The first time a phone opens the web app, the house greets it: "Hello! A new phone has just joined. What's your name?". The name can be said aloud (the house asks to confirm: "Is your name Luca?") or typed on the card that appears on the phone; then the house invites the visitor to come in with a character, and the phone offers **Add a character**. The name becomes the phone's nickname, the one shown in the change log.
- Each phone is greeted once, also after a restart; a phone that comes back from the same address with another page (the home-screen icon, a private window, `casaN.lan`) is the same phone. The house forgets phones (and names) after 7 days.
- Phones that join together get one greeting, and at most one spoken greeting (or thanks) every 45 seconds: the other phones get the card only.
- Names **typed** on the phones are never read aloud (a name box would let anyone make the house say anything): the house thanks without the name, the phone shows it. Names said aloud are, since they come from the words the speech model knows.
- **Later** on the card holds for that phone: the house stops asking. If the card is lost (page reloaded, phone locked), it comes back once on reconnection.
- In **Silent** mode the house neither speaks nor listens: the card on the phone remains.
- Turn it off in **Settings → Voice → Greet new phones**.

**Questions to the characters** (**Chatty** mode only). About every two minutes, if visitors are around (something happened in the house in the last 5 minutes: a figurine moved, a button, a phone), a named character is in the house and the house is free, the house asks it a question that suits the room it is in, and listens for the answer:
- kitchen: "Marco, what shall we cook tonight: pizza or pasta?", "are you hungry?";
- living room: "how about some music?" (a yes starts the party), "shall we watch a film?" (a yes, cinema scene), "do you prefer the sofa or the armchair?";
- bedroom: "did you sleep well?", "shall I dim the lights so you can rest?" (a yes dims the light);
- garage: "where shall we drive to: the seaside or the mountains?";
- garden: "shall I light the barbecue?" (a yes starts the fan), "do you like my garden?";
- anywhere: "do you like this house?", "are you a morning or an evening person?", "where are you from?", "what's your favourite colour?" (the room light takes that colour);
- animals: "would you like a walk?", "are you hungry?".

The answer to a chat question is matched against a few expected words (yes, no, pizza, pasta, the colours...) and is never run as a command: "I like music" does not start the party. **Offers** (music, the film, the soft light, the barbecue and the ones to crowds in the table above) understand answers as they come instead: a yes, even inside a sentence ("yes, let's put on some music", "why not", "go ahead", "I'd love to"), carries out the offer; a no ("no thanks", "not now", "maybe later") leaves it; another command of the house said instead of an answer ("no, light the barbecue", "turn the living room light red") runs that command, and a light without a room is the one of the character's room ("turn off all the lights" stays the whole house). A yes does not count if the offer itself is refused ("yes, but no music", "please don't light the barbecue", "don't do it"), and saying you cannot stand it ("I hate the barbecue") is a no. A sentence that names the offer without asking for it ("we had a barbecue yesterday", "the music is too loud") does not carry it out: the model weighs it. Sentences the rules do not understand go to the language model (below), which only says whether the answer accepts, refuses or neither; a yes it is not sure of is not enough. If the answer is not clear the house asks once "Sorry, I didn't get that: yes or no?"; if nobody answers, for 30 seconds a "yes" can still be said with **Talk** (a question or another request said meanwhile, such as "is anybody in the kitchen?", gets its own answer and does not close the offer). The house does not offer what it cannot do now (the barbecue already on, a party just over, the cinema already on). With no answer: "Nothing? Maybe next time, Marco." the first time, then silence; after two unanswered questions the house waits for a new sign of visitors. Never in the bathroom or the utility room, never twice in a row to the same character (with only one in the house it waits for another), and not during a party, a conversation, a registration or a question of the house. Adjust them in **Settings → Voice**: *Questions to the characters* and *One question every (s)* (at least 45, 120 by default; the exact moment varies by a quarter either way).

**What the house tells.** In **Normal** and **Chatty** modes the house says in a few words what happens: "Here's Viola in the living room!", "Viola goes to the kitchen.", "Luca comes into the house.", "Mister Braun goes out onto the driveway.", "Bye Rosaria, see you soon!", "The car is parked in the garage." (the arrival and departure of the car are said by the rules: "Welcome home!", "Have a good trip!"). It waits until a move has stopped for a second, so a figurine carried across a room for a moment is not announced; what happens together is said in one go; it never talks over a question or while someone speaks to it. A newcomer it does not know is not announced: the house asks who it is. On the bed or the sofa it says so ("Here's Viola on the bed in the bedroom!", "Mister Braun is on the living room sofa."); on a table, a bench, the fridge or the other furniture it tells the character to get down at once ("Viola, get off the table right now!"), and "Where's Viola?" answers with the furniture. It does not say goodbye to someone still in the house (put down elsewhere, for instance). What it has said about a character it does not say again while the character stays there: "Rossana is on the bed in the bedroom" is heard once, not at every shadow on the edge of the bed nor every time the house finds its name again. It says it again after ten minutes, or when the character really moves and comes back. The most common lines, of the story and of the questions, come in several variants, and the house never says the same one twice in a row.

## What you can say

The examples below are understood directly by the rule-based parser. It tolerates recognition errors in the names and does not need exact wording: the words that matter are the verbs, the rooms, the colours and the names of the characters. A registered name said alone ("Luna") is taken as "where is Luna?".

**Names first.** When a sentence names a character, the requests about characters come before the general ones: "Raccontami cosa piace a Rossellina" is a question about Rossellina, not "who are you?" or "what can you do?". A name mangled by the recognizer is found again if it is close enough ("Rossellino" is Rossellina) or if it holds a word of its own ("vista Brown" is Mister Brown, if nobody else is called Brown). Words that many names share (*Mister*, *Signora*, the colours, the rooms) are not enough by themselves. After a question about a character, for a minute and a half a question with no name is about that character: "Tell me about Rossellina", then "what's her job?", "what does she like?".

| Request | Italian | English |
|---|---|---|
| Where is someone | Dov'è Marco? · Dove si trova Sofia? | Where is Marco? |
| Who is in a room | Chi c'è in cucina? · C'è qualcuno in garage? | Who's in the living room? · Is anyone in the garage? |
| How many | Quante persone ci sono in casa? · Quanti animali ci sono? | How many people are in the bathroom? · How many pets are there? |
| Temperature | Che temperatura c'è? · Temperatura in bagno | What is the temperature? |
| Humidity | Quanta umidità c'è in bagno? | How humid is the bathroom? |
| Time | Che ore sono? | What time is it? |
| Set the time | Sono le tre e mezza · Sono le quindici e trenta | It's half past three · It's ten to seven pm |
| Lights on | Accendi la luce in cucina · Luce rossa in camera | Turn on the kitchen light · Make the bedroom red |
| Favourite light | Accendi la luce preferita di Marco · Metti il colore preferito di Giulia in cucina | Turn on Marco's favourite colour |
| Lights off | Spegni la luce in bagno · Spegni tutto | Turn off the lights in the garage |
| Scenes | Scenario cinema · Scenario relax · Modalità via · Buonanotte · Buongiorno | Cinema mode · Relax scene · Away mode · Good night · Good morning |
| Party | Fai festa · Balliamo | Let's dance · Party |
| Barbecue | Accendi il barbecue · Spegni il barbecue | Light the barbecue · Turn off the barbecue |
| The car | Dov'è la macchina? | Where is the car? |
| The whole house | Com'è la casa? · Cosa succede? | How is the house? · What's happening? |
| Help | Cosa sai fare? | What can you do? |
| Who the house is | Chi sei? | Who are you? |
| A joke | Raccontami una barzelletta · Fammi ridere | Tell me a joke · Make me laugh |
| Language | Parla inglese · Parla italiano | Speak English · Speak Italian |
| Talkativeness | Stai zitta · Parla di più · Parla normale | Be quiet · Talk more · Normal mode |
| Volume | Alza il volume · Abbassa la musica | Louder · Turn it down |
| New character | Aggiungi un personaggio | Add a character |
| A story | Raccontami una storia · Una storia su Marco e Giulia · Una storia sulla cucina · Un'altra storia | Tell me a story · A story about Marco and Giulia · A story about the kitchen · Another story |
| The day | Cosa ha fatto Marco oggi? · Dov'è stato Luca? · Chi è stato in cucina oggi? · Quante feste abbiamo fatto oggi? | What did Marco do today? · Where has Luca been? · Who has been in the kitchen today? · How many parties today? |
| A character | Ricorda che Marco fa il medico · Cosa sai di Marco? · Raccontami qualcosa di Marco · Cosa piace a Giulia? · Chi è Giulia? | Remember that Marco is a doctor · What do you know about Marco? · Tell me about Marco · What does Giulia like? · Who is Giulia? |
| Two characters together | Mister Brown e Rossellina stanno insieme · Marco e Giulia sono vicini | Marco and Giulia are together |
| Memories and free questions | Ti ricordi la festa di compleanno di Giulia del 1998? · Luca ha pagato le bollette? · Quando scade l'assicurazione dell'auto? | Do you remember Giulia's birthday party in 1998? · Did Luca pay the bills? · When does the car insurance expire? |
| Cancel | Annulla · Lascia stare | Cancel · Never mind |

Colours: rosso/red, verde/green, blu/blue, giallo/yellow, arancione/orange, viola/purple, rosa/pink, bianco/white, azzurro/cyan, caldo/warm. Rooms can be called in several ways: *soggiorno*, *salotto* or *sala*; *camera* or *camera da letto*; *locale tecnico* or *tecnico*; *living room*, *lounge*; and so on.

A few details:

- "Buonanotte" / "Good night" switches to the Night scene and says good night; "Buongiorno" / "Good morning" goes back to Normal and says good morning.
- A light switched on by voice stays on for two minutes; "turn off" keeps it dark for one minute; then the house takes the room back.
- The volume changes in steps of 15 (out of 100).
- A party or a barbecue asked for too soon gets "Give me a moment, then we party again!" or "The barbecue is already on, or cooling down."
- "Marco and Giulia are together" tells the house that the shape it sees is made of the two characters touching: two figurines in contact are one blob, and the house marks both of them as there, one hidden behind the other until a hand parts them (like the answer "both" in [a newcomer](07-recognition-and-identities.md#a-newcomer)). The house looks for the shape that already has one of the two names, or the only one it does not recognize; if you say the room ("...in the living room") it looks there. If it does not find it, it answers "I can't see them: put them where the camera sees them, or tell me the room."

What the answers sound like: "Marco è in cucina." / "Marco is in the kitchen.", "In cucina ci sono Marco e un cane.", "There are 2 people in the house.", "It's 24.3 degrees in the living room.", "The car is parked in the garage." When the house is not sure about a figurine it adds "Almeno credo." / "I think.".

## The language model for commands

A sentence the parser does not understand ("Quanta gente c'è in cucina?", a request with unusual words, a sentence mangled by the recognizer) goes to **Qwen2.5-0.5B-Instruct** (quantized to 4 bits, GGUF), run by `llama-server` from llama.cpp in the `domotiq-llm` service. While it works, the house says "Vediamo…" / "Let me see…". It receives fixed instructions with the rooms, the commands of the house and a few examples, then the names of the registered characters and the sentence. Its output is constrained while it is produced, so it can only write one command of the house with its arguments: *where_is Marco*, *who_in kitchen*, *lights_on bedroom purple*, or *other* for anything else. The instructions are always the same text, which `llama-server` keeps in its cache.

The same model also understands the answers to "who is it?" that the rules do not recognize: it classifies them as a name, a kind, yes, no, "there's nobody", "I don't know" or anything else; a sentence with two registered names ("look, both Viola and Rosaria are there") means that both of them are there. A name it proposes counts only if it is in the sentence; the kind and the registered names are read by the house in the sentence itself, so the model cannot make up a character. These instructions sit in a second slot of `llama-server`, those that tell whether an answer accepts an offer of the house in a third, and those that tell what a fact about a character is about when no keyword does ([What the house knows about the characters](#what-the-house-knows-about-the-characters)) in a fourth: `-np 4`, context 8192, so no kind of request pushes the others out of the cache.

**Starting the model.** The four sets of instructions (with their examples) are 5,458 tokens long: on the Cortex-A53 cores of the board, with 3 threads at low priority so that vision and voice stay quick, the model reads about 9 a second, so 10 to 12 minutes (730 s on casa1). After the first reading each slot is saved in `/var/lib/domotiq-llm` (`--slot-save-path`, 67 MB in all), and at the next starts it is back in the cache in a few seconds (3.2 s for all four on casa1); it is read again only if the instructions or the model change. The reading starts together with the voice getting its sentences ready, not after it. Until the model is ready the rules work all the same, and only a free sentence that needs the model gets "I didn't get that". Then a free answer takes 3 to 6 seconds.

**This model chooses what to do and never writes what the house says**: the answer is composed from the real state of the house, with sentences prepared in Italian and English, so it cannot make things up. The same holds for the day of the characters ("What did Marco do today?"): the answer comes from what the camera really saw, not from a model.

## Stories, memories and free questions

Stories, memories ("Do you remember Giulia's birthday party in 1998?") and answers about life in the house ("Did Luca pay the bills?", "When does the car insurance run out?") are generated on the board by combining the pieces of a local database, `data/stories.json`, written by hand in Italian and English: moments ("One winter evening"), activities for each room, events, reactions, relationships between characters, discoveries, endings, personalities (jobs, characters, passions and quirks, also for dogs and cats), details of life in the house (bills, insurance, chores, shopping, cakes, holidays) and the outlines of six kinds of story (alone, at work, as a pair, the suspected prank, the surprise party, the room). It is procedural generation: the house picks at random among the pieces that fit together and slots them into the outline. A few hundred pieces give millions of different stories, ready in a millisecond, and every sentence is correct because every piece is written to agree with any name: in Italian no adjective or participle refers to a character, in English no *he* or *she*. Here the house makes things up, on purpose:

- **Pieces that fit.** A discovery or an ending may be tied to the events it explains (the parcel with no name was a present for the house); the other pieces share a tag with the event (dark, noise, water, party…). Day and night, summer and winter never meet in the same story; a noise "from the garage" is not heard by someone already in the garage; dogs bark and cats hiss.
- **Personalities.** The first time it is needed, a character gets a job, a character, a passion and a quirk from the database, different from the others'. They stay the same until the house restarts: if Marco is a doctor, he stays a doctor in the next stories; after a restart everything starts again. What somebody told the house comes first (in the web app, under *Who they are*, one thing per line, or aloud: "Remember that Marco is a doctor"). A piece of information that is a job takes the place of the job, and in the Italian stories it becomes the matching job of the database; the others go into the stories written in their language ("Marco, who loves jazz, …"). "What do you know about Marco?" first says where Marco is, then the given information and the personality; information written in the other language is read by that language's voice.
- **Always a new story.** For each character (or room) the house remembers the outlines and pieces already used and picks among the others until it has used them all.
- **The life of the house.** The first answer to a question is made up from the database, then it stays: the same question gets the same answer, also in the other language, until the restart. The house can answer about bills (all of them or one: electricity, gas, water, internet; who paid and when, or when they are due), car and home insurance, birthdays, parties of the past (with the name and the year, also of someone it does not know, or "the Christmas party in 2005": the room, the cake, what happened and who was there), shopping, chores (rubbish, dishes, washing, hoovering, plants), feeding the pets, the car, holidays and memories of a character. To a question that is not about the house it answers that it is a house and knows nothing about the rest of the world.
- **Spoken sentence by sentence.** While one sentence plays the next is synthesized, each with the voice of its own language, and the room it talks about lights up. **Talk** interrupts the story; a change of language stops it too.

In **Chatty** mode, about two times in five, instead of a question from the list the house says something about a character in the house: an anecdote, its quirk ("Did you know that Marco talks to the plants?"), a memory with its date ("Do you remember Marco's party in 2004?") or a question about life in the house ("Marco, did you pay the electricity bill?"), followed by the reply to a yes or a no. What the visitor says becomes the life of the house: after a yes, "Did Marco pay the electricity bill?" gets a yes.

Stories, memories and free questions use no language model, so they also work with a `--no-llm` installation. At first they were written by a second model on the board: the measurements and the reason for the change are in decision D-19 (`docs/decisioni.md`, in Italian).

## What the house knows about the characters

An answer to a question of chatty mode that tells something lasting about a character becomes one of its facts, like those of *Who they are* in the web app: written as it would be said after the name, in the language of the conversation. "What's your favourite dish?" → "pizza" becomes "loves eating pizza", and the house replies "I'll remember that: Rossellina loves eating pizza."; "where are you from?" → "comes from Turin". Pizza or pasta, sofa or armchair, seaside or mountains, morning or evening, the favourite colour, the house and the garden are noted without a word more. Questions about the moment ("are you hungry?", "did you sleep well?") and offers ("how about some music?") are not noted, and neither is an unclear answer ("dunno"), a long one or one heard badly, or one about the speaker instead of a dish or a place ("I'm a vegetarian", "I'm Italian", "my name is Giulia"). A denied choice counts for the other one ("pizza, not pasta"); "I don't like red" is no favourite colour. Each question keeps one line: a new answer takes the place of the old one, even if it was in the other language; when there are already eight lines, the oldest answer makes room, never a line somebody typed (unless it has just the shape of an answer, such as "loves eating pizza": "comes from a family of farmers" stays as it is). Lines made from an answer read in both languages: in Italian "loves eating pizza" becomes "adora mangiare pizza", in stories and in answers.

The house then answers questions about what it knows, however they are put: "Cosa mangia Rossellina?", "Qual è il pranzo preferito da Rossellina?", "What does Rossellina like to eat?", "What can I cook for Rossellina?" → "I know that Rossellina loves eating pizza.". Keywords of both languages tell what the question is about (food, drinks, colours, music, sport, work, fears, hobbies, travel, sofa and armchair, where somebody comes from, animals, family, age, the house, mornings and evenings) and what every fact is about; when no keyword does, the house looks for the facts that share a word with the question ("Does Marco play the guitar?" finds "plays the guitar in a band"), and to a question about what somebody likes it answers with what they love. For a fact typed in the web app that no keyword describes ("is mad about comics") the topic is told by the language model, which can only write one of those topics: it does so in the background, while the house is free, as soon as the fact is typed, so a question finds it without waiting. The answer is the fact itself after the name, so the house makes nothing up and the sentence agrees with any name; a fact typed as a whole sentence ("her favourite dish is carbonara") is said as it is: "About Rossellina, I know that her favourite dish is carbonara." When it knows nothing about that topic it says so: "I don't know: Rossellina hasn't told me yet." **The answer is always immediate**, like that of the light commands: no question about a character waits for the language model. Questions about life in the house (bills, shopping, chores…) stay with the stories; for holidays a fact comes before the made-up answer. A request that names a character is still a request ("Marco vuole sentire la musica", "musica per Marco", "Marco is hungry, light the barbecue"), and "Is Marco on the sofa?" asks where it is now, not where it likes to sit.

**What it does with them.** Three answers the house acts on:

- **The favourite colour** ("Marco, what's your favourite colour?"): in the Normal scene the light of a room takes the favourite colour of whoever is in (the last one to come in, among those who told it; switched off with **Light in the favourite colour of who comes in** in **Settings**), and "turn on Marco's favourite colour" lights the room Marco is in, or the one said ("...in the kitchen"), in that colour. If Marco has not told it yet and is in the house, the house asks at once and the answer lights the room.
- **Loves dancing** ("Marco, do you like dancing?"): in chatty mode, when Marco is in the living room with somebody else, the house offers a party ("Marco, you love dancing: shall we party?").
- **Loves barbecues** ("Marco, do you like barbecues?"): when Marco is in the garden, the house offers the barbecue ("Marco, you love barbecues: shall I light it?").

These offers are heard without Talk like the others, at most one every 10 minutes of each kind. **Ask a question**, in **Controls** and on the card of each character, makes the house ask one of these questions at once, outside chatty mode too, preferring those the character has not answered yet: to a character picked at random among those in the house, or to the one of the card, even if it is not in the house.

## Speech recognition

The Vosk models are `vosk-model-small-it-0.22` and `vosk-model-small-en-us-0.15` (Apache-2.0). The house uses them in two ways:

- **A closed list of phrases** for names, yes/no and the options of a question: the model accepts only those words, which makes it fast (under half a second for a name on the board) and very hard to fool;
- **Free speech** for questions and commands, turned into an intent afterwards.

To its own questions the house listens to the same audio both ways. The word of the list counts when the free speech confirms it or is close to it, or when the recognizer is very sure of it and the answer is short (up to three words); otherwise the free speech counts, which understands answers in other words than the expected ones too ("I'd say yes", "pasta, I think").

The microphone is on only while the house listens, at 16 kHz mono: while Talk is held, after "Who is it?" and for a few seconds after greeting a new phone or asking a chatty question; with the [word of activation](#the-word-of-activation) on, also while the house is free and waits for the word. The audio stays in memory and is never saved; of what the house hears without Talk the log keeps only the outcome (yes, no, an option), never the text, and the recognised text is not sent to the phones. The exception is an answer that becomes a fact of a character ([What the house knows about the characters](#what-the-house-knows-about-the-characters)): it stays among its facts, which the web app shows and anyone can correct or delete. A visitor's answer to a question about life in the house (chatty mode) stays in the storyteller's memory, for later stories, until the restart: it is not written to disk.

## Speech synthesis

Piper (`piper1-gpl`, GPL-3.0) runs as a separate program in the `domotiq-tts` service, and the house sends it sentences over HTTP on the loopback interface. The voices are `it_IT-serena-medium` (CC BY 4.0) and `en_US-ljspeech-medium` (public domain). Numbers and units are spoken properly ("24.3 °C" becomes "24 point 3 degrees"). The frequent sentences ("Who is it?", "Let me see…", "Let's dance!"…) are made ready at start-up and kept in memory, so they play at once even when the processor is busy. **Every sentence synthesized is also saved on disk**, in `var/voice/` (one WAV file per sentence, named after the voice and the text): after a restart the house reads it back in a moment instead of asking Piper again, so the frequent sentences are ready at once and Piper only works on those never said before. At most 3000 sentences are kept; beyond that, the ones not said for the longest time are deleted. If the voice changes, the sentences are synthesized again. A few phrases are given to Piper already written as phonemes, where the Italian voice would swallow a vowel: "Come si chiama?" came out as "Cme s chiama?", because the automatic transcription reads "si" as a reduced vowel.

All the other sounds (doorbell, chime, the beeps of Talk, alarm, notification) and the party music are synthesized by the house's own code: no recorded samples. The party music is four-on-the-floor dance music at 124 BPM, with kick, clap, hi-hats, bass, chords and a melody that change at every party, in time with the light show of the microcontroller. The music ducks under the voice when the house speaks.

## Setting the clock by voice

The UNO Q has no battery for its clock. If two minutes after start-up the time is still unknown, the house asks once (unless it is Silent): "I don't know the time: what time is it now?", and listens for the answer at once, with no Talk button. It does the same after "What time is it?" when it does not know. At any time you can also hold **Talk** and say the time:

- Italian: "Sono le quindici e trenta", "Sono le tre e mezza", "Sono le tre e venticinque", "Sono le dieci e un quarto", "Sono le tre e tre quarti", "Sono le otto meno venti", "Sono le sette meno un quarto", "È l'una e dieci". Any minute works, in words or digits; "del pomeriggio" or "di sera" add twelve hours.
- English: "It's half past three", "It's quarter to five", "It's twenty past six", "It's ten to seven pm", "It's five twenty", "Set the clock at three thirty". "pm", "afternoon" or "evening" add twelve hours.

The house confirms: "D'accordo, sono le 15 e 30." / "All right, it's 15:30." The first phone that opens the web app sets the clock too, and it can be set from **Settings → Use this phone's time**.

Next: [rules](09-rules.md).
