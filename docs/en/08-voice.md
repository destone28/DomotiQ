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
| **Talk** | Hold it down and speak; release it when you are done. A beep marks the start and the end. There is no need to hurry: the house listens as long as the button is held (up to two minutes). Pressing Talk while the house is speaking interrupts it. | on while the house listens |
| **Intercom** | A doorbell rings and the house asks "Chi è?" / "Who is it?". Say a name, without pressing anything: the house listens for 5 seconds after its question. See [the intercom](07-recognition-and-identities.md#with-the-intercom). | blinks during the conversation |
| **Language** | Switches between Italian and English. All the lights flash for about a second, **green for Italian** and **red for English**, and the house says "Italiano" or "English". | on while the house speaks English |

The house starts in Italian. The language can also be changed from **Controls → Language of the house** in the web app, or by voice ("Parla inglese", "Speak Italian"). This is the language the house speaks and listens in; each phone chooses the language of the web app on its own.

During the intercom conversation and the registration by voice, the house listens by itself for a few seconds after each of its questions ("Who is it?", "I heard Marco, right?", "Which room did you put it in?"). To answer its questions about who is who ("Is it Marco or Leo in the kitchen?"), hold **Talk** and say the name.

## Talkativeness

| Level | Behaviour |
|---|---|
| **Silent** | Never speaks. The doorbell and short sounds remain; answers and everything else the house would say appear only as subtitles in the web app. |
| **Normal** | Answers, the intercom, alarms and warnings, and the important events of the rules. |
| **Chatty** | As Normal, plus comments: who goes where ("Marco is in the kitchen.", at most every 20 seconds), proposals ("So many of you in the living room: shall we party?" with three or more people there, "Lovely day in the garden: shall I light the barbecue?" with two or more in the garden, at most every 10 minutes) the sentences that rules mark as chatty, such as "The temperature is back to normal.", and the **questions to the characters** (below). |

Set it from **Controls → Talkativeness**, or by voice: "Stai zitta" / "Be quiet", "Parla di più" / "Talk more", "Parla normale" / "Normal mode". Every sentence the house says also appears as a subtitle on the phones and in **Events → Said by the house**.

## Talking without pressing Talk

In two cases the house asks something and then listens by itself for a few seconds: the **Talk** LED lights up and the phones show *The house is listening…*. If the house says something else while it listens (a rule, a warning), the answer is thrown away: it could be its own voice. **Talk** and the **intercom** always come first: pressing them interrupts the greeting or the question, and the house listens to the button.

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

The answer is matched against a few expected words (yes, no, pizza, pasta, the colours...) and is never run as a free command: in a chat, "I like music" must not start the party. Offers are carried out only after a short, clear yes ("why not" counts as yes, "I don't know" does not), and the house does not offer what it cannot do now (the barbecue already on, a party just over, the cinema already on). With no answer: "Nothing? Maybe next time, Marco." the first time, then silence; after two unanswered questions the house waits for a new sign of visitors. Never in the bathroom or the utility room, never twice in a row to the same character (with only one in the house it waits for another), and not during a party, a conversation, a registration or a question of the house. Adjust them in **Settings → Voice**: *Questions to the characters* and *One question every (s)* (at least 45, 120 by default; the exact moment varies by a quarter either way).

## What you can say

The examples below are understood directly by the rule-based parser. It tolerates recognition errors in the names and does not need exact wording: the words that matter are the verbs, the rooms, the colours and the names of the characters. A registered name said alone ("Luna") is taken as "where is Luna?".

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
| Cancel | Annulla · Lascia stare | Cancel · Never mind |

Colours: rosso/red, verde/green, blu/blue, giallo/yellow, arancione/orange, viola/purple, rosa/pink, bianco/white, azzurro/cyan, caldo/warm. Rooms can be called in several ways: *soggiorno*, *salotto* or *sala*; *camera* or *camera da letto*; *locale tecnico* or *tecnico*; *living room*, *lounge*; and so on.

A few details:

- "Buonanotte" / "Good night" switches to the Night scene and says good night; "Buongiorno" / "Good morning" goes back to Normal and says good morning.
- A light switched on by voice stays on for two minutes; "turn off" keeps it dark for one minute; then the house takes the room back.
- The volume changes in steps of 15 (out of 100).
- A party or a barbecue asked for too soon gets "Give me a moment, then we party again!" or "The barbecue is already on, or cooling down."

What the answers sound like: "Marco è in cucina." / "Marco is in the kitchen.", "In cucina ci sono Marco e un cane.", "There are 2 people in the house.", "It's 24.3 degrees in the living room.", "The car is parked in the garage." When the house is not sure about a figurine it adds "Almeno credo." / "I think.".

## Free questions and the language model

A sentence the parser does not understand ("Quanta gente c'è in cucina?", a request with unusual words, a sentence mangled by the recognizer) goes to the **language model**. While it works, the house says "Vediamo…" / "Let me see…".

The model is **Qwen2.5-0.5B-Instruct** (quantized to 4 bits, in GGUF format), a small language model run by `llama-server` from llama.cpp in the `domotiq-llm` service, on the board, with no internet. It receives fixed instructions with the rooms, the commands of the house and a few examples, then the names of the registered characters and the sentence. Its output is constrained while it is produced, so it can only write one command of the house with its arguments, in a few words: *where_is Marco*, *who_in kitchen*, *lights_on bedroom purple*, *scene relax*, or *other* for anything that is not about the house. The commands cover the same requests as the table above (where is, who is in, how many, temperature, humidity, time, lights, scenes, party, barbecue, the car, the house summary, help, language, volume, who are you, add a character, a joke). A name can only be one of the registered characters. The instructions are always the same text, which `llama-server` keeps in its cache, so each question adds only a few words to read.

**The model chooses what to do; it never writes what the house says.** The answer is then composed by the same code that answers the fixed phrases, from the real state of the house, with sentences prepared in Italian and English. So the house cannot make things up: if the model misunderstands, the worst case is a correct answer to a different question.

A question that is not about the house gets: "Sono la casa: posso dirti chi c'è e dove, che temperatura fa, e posso accendere luci, fare festa o grigliare." / "I'm the house: I can tell you who's here and where, the temperature, and I can turn on lights, throw a party or light the barbecue." A sentence nobody understood gets "I didn't get that. Try asking: where is Marco? Or: let's party!".

Without the language model (installed with `--no-llm`, or with its service stopped) the fixed phrases above keep working.

## Speech recognition

The Vosk models are `vosk-model-small-it-0.22` and `vosk-model-small-en-us-0.15` (Apache-2.0). The house uses them in two ways:

- **A closed list of phrases** for names, yes/no and the options of a question: the model accepts only those words, which makes it fast (under half a second for a name on the board) and very hard to fool;
- **Free speech** for questions and commands, turned into an intent afterwards.

The microphone is on only while the house listens, at 16 kHz mono: while Talk is held, after "Who is it?" and for a few seconds after greeting a new phone or asking a chatty question. The audio stays in memory and is never saved; of what the house hears without Talk the log keeps only the outcome (yes, no, an option), never the text, and the recognised text is not sent to the phones.

## Speech synthesis

Piper (`piper1-gpl`, GPL-3.0) runs as a separate program in the `domotiq-tts` service, and the house sends it sentences over HTTP on the loopback interface. The voices are `it_IT-serena-medium` (CC BY 4.0) and `en_US-ljspeech-medium` (public domain). Numbers and units are spoken properly ("24.3 °C" becomes "24 point 3 degrees"). The frequent sentences ("Who is it?", "Let me see…", "Let's dance!"…) are synthesized at start-up and kept in memory, so they play at once even when the processor is busy.

All the other sounds (doorbell, chime, the beeps of Talk, alarm, notification) and the party music are synthesized by the house's own code: no recorded samples. The party music is four-on-the-floor dance music at 124 BPM, with kick, clap, hi-hats, bass, chords and a melody that change at every party, in time with the light show of the microcontroller. The music ducks under the voice when the house speaks.

## Setting the clock by voice

The UNO Q has no battery for its clock. If two minutes after start-up the time is still unknown, the house says once (unless it is Silent): "I don't know what time it is: press Talk and tell me."

Hold **Talk** and say the time:

- Italian: "Sono le quindici e trenta", "Sono le tre e mezza", "Sono le tre e venticinque", "Sono le dieci e un quarto", "Sono le tre e tre quarti", "Sono le otto meno venti", "Sono le sette meno un quarto", "È l'una e dieci". Any minute works, in words or digits; "del pomeriggio" or "di sera" add twelve hours.
- English: "It's half past three", "It's quarter to five", "It's twenty past six", "It's ten to seven pm", "It's five twenty", "Set the clock at three thirty". "pm", "afternoon" or "evening" add twelve hours.

The house confirms: "D'accordo, sono le 15 e 30." / "All right, it's 15:30." The first phone that opens the web app sets the clock too, and the staff can set it from **Settings → Use this phone's time**.

Next: [rules](09-rules.md).
