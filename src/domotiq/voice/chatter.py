# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Small talk that needs no button.

- **Welcome.** A phone opens the web app for the first time: the house says
  hello, asks the name (said aloud, or typed on the phone) and invites the
  newcomer to come into the house with a character. Phones that arrive
  together are greeted together, at most one spoken welcome every 45 s, and
  each phone once (the house keeps a list of the phones it has seen for 7
  days; a new id from the address of a phone seen lately is the same phone).
- **Questions** (chatty mode only). Now and then, while visitors are around,
  the house asks a named character in the house a question about the room it
  is in ("Marco, what shall we cook tonight: pizza or pasta?"), listens for
  the answer by itself and reacts. Never in the bathroom or the utility room.

Rules that keep it from misbehaving at a fair:
- Talk and the intercom come first: pressing them stops the small talk.
- Answers are matched against short lists of words and are never run as free
  commands (in a chat, "mi piace la musica" must not start a party); an offer
  ("Shall I light the barbecue?") needs a short, clear yes.
- An answer is thrown away if the house was speaking while it listened: it
  could be the house's own voice.
- Names typed on the phones are never read aloud (a name box would be a way
  to make the house say anything); names heard aloud come from the words the
  speech model knows.
- What the microphone heard is not stored, only the outcome.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from .intents import COLORS, find_color, name_from_speech, normalize

if TYPE_CHECKING:
    from .manager import Voice

log = logging.getLogger(__name__)

GROUP_S = 3.0          # phones opening the web app within this time are greeted together
GREET_GAP_S = 45.0     # at most one spoken welcome (or thanks) in this time; the others get the card only
THANK_GROUP_S = 4.0    # names typed within this time are thanked together
ECHO_S = 0.35          # what the microphone hears this long after the house has spoken is still its echo
ANSWER_S = 6.0         # how long the house waits for an answer
RETRY_S = 15.0         # a question is due but the house is busy or nobody is there
MIN_EVERY_S = 45.0
ACTIVE_S = 300.0       # questions only if something happened in the house in the last 5 minutes
NAME_CONFIDENCE = 0.5  # a name heard with less confidence is not proposed
OFFER_CONFIDENCE = 0.6 # an offer is carried out only on a yes heard at least this well
ASK_ROOMS = ("kitchen", "living", "bedroom", "garage", "garden")
GENERATED_SHARE = 0.4   # about two lines in five come from the storyteller (anecdotes, memories, questions)
ANIMALS = ("dog", "cat", "animal")

# the grammar needs the spelling of the speech model; the matching below ignores accents
YES_WORDS = {"it": ["sì", "certo", "certamente", "esatto", "giusto", "va bene", "volentieri", "ok", "okay",
                    "ovvio", "sicuro", "magari", "assolutamente"],
             "en": ["yes", "yeah", "yep", "sure", "ok", "okay", "please", "right", "absolutely", "definitely"]}
NO_WORDS = {"it": ["no", "non", "nessuno", "mai", "niente", "macché"],
            "en": ["no", "nope", "not", "never", "nothing"]}
# checked before the words above: "perché no" is a yes, "non lo so" is neither
YES_PHRASES = {"it": ["perché no", "come no"], "en": ["why not", "of course"]}
UNSURE_PHRASES = {"it": ["non lo so", "non so", "boh", "forse", "dipende"],
                  "en": ["i don't know", "don't know", "not sure", "maybe", "depends"]}

WELCOME = {"it": "Ciao! Si è appena collegato un telefono nuovo. Come ti chiami?",
           "en": "Hello! A new phone has just joined. What's your name?"}
INVITE = {"it": "Adesso entra in casa con un personaggio: sul telefono tocca Aggiungi un personaggio, "
                "poi fai entrare la statuina dalla porta.",
          "en": "Now come into the house with a character: tap Add a character on your phone, "
                "then bring the figurine in through the door."}

T = dict[str, str]


def _q(qid: str, rooms: tuple[str, ...] | None, who: str, kind: str, it: str, en: str, **more: Any) -> dict[str, Any]:
    return {"id": qid, "rooms": rooms, "who": who, "kind": kind, "text": {"it": it, "en": en}, **more}


def _opt(it_words: list[str], en_words: list[str], it: str, en: str, action: dict | None = None) -> dict[str, Any]:
    return {"words": {"it": it_words, "en": en_words}, "reply": {"it": it, "en": en}, "action": action}


# {name} is the character asked. "yesno" questions may carry an action done after a yes; "color"
# questions light the room in the colour said. "who": person, animal (any animal) or dog.
QUESTIONS: list[dict[str, Any]] = [
    # kitchen
    _q("k-cook", ("kitchen",), "person", "choice",
       "{name}, cosa cuciniamo stasera: pizza o pasta?", "{name}, what shall we cook tonight: pizza or pasta?",
       options=[_opt(["pizza"], ["pizza"], "Pizza! Accendo il forno, {name}.", "Pizza! I'm turning the oven on, {name}."),
                _opt(["pasta"], ["pasta"], "Pasta! Metto su l'acqua, {name}.", "Pasta! I'm boiling the water, {name}.")]),
    _q("k-hungry", ("kitchen",), "person", "yesno",
       "{name}, hai fame?", "{name}, are you hungry?",
       yes={"it": "Allora apri il frigo: è pieno!", "en": "Then open the fridge: it's full!"},
       no={"it": "Bene, allora ci vediamo a cena.", "en": "Good, see you at dinner then."}),
    _q("k-dish", ("kitchen",), "person", "open",
       "{name}, qual è il tuo piatto preferito?", "{name}, what's your favourite dish?"),
    # living room
    _q("l-music", ("living",), "person", "yesno",
       "{name}, ti va un po' di musica?", "{name}, how about some music?",
       yes={"it": "Ottima idea, {name}!", "en": "Great idea, {name}!"},
       no={"it": "Va bene, allora un po' di silenzio.", "en": "All right, some quiet then."},
       action={"do": "party"}),
    _q("l-film", ("living",), "person", "yesno",
       "{name}, guardiamo un film?", "{name}, shall we watch a film?",
       yes={"it": "Luci da cinema, {name}!", "en": "Cinema lights, {name}!"},
       no={"it": "D'accordo, sarà per stasera.", "en": "OK, maybe tonight."},
       action={"do": "scene", "scene": "cinema"}),
    _q("l-sofa", ("living",), "person", "choice",
       "{name}, preferisci il divano o la poltrona?", "{name}, do you prefer the sofa or the armchair?",
       options=[_opt(["divano"], ["sofa", "couch"], "Il divano è il posto migliore della casa.",
                     "The sofa is the best seat in the house."),
                _opt(["poltrona"], ["armchair", "chair"], "La poltrona è tutta tua, {name}.",
                     "The armchair is all yours, {name}.")]),
    # bedroom
    _q("b-sleep", ("bedroom",), "person", "yesno",
       "{name}, hai dormito bene?", "{name}, did you sleep well?",
       yes={"it": "Che bello! Il materasso è nuovo.", "en": "Lovely! The mattress is new."},
       no={"it": "Mi dispiace: stanotte ti abbasso le luci.", "en": "Sorry: tonight I'll dim the lights for you."}),
    _q("b-rest", ("bedroom",), "person", "yesno",
       "{name}, ti abbasso le luci per riposare?", "{name}, shall I dim the lights so you can rest?",
       yes={"it": "Ecco, luce tenue. Buon riposo, {name}.", "en": "There, soft light. Rest well, {name}."},
       no={"it": "Va bene, la luce resta com'è.", "en": "All right, the light stays as it is."},
       action={"do": "light", "color": "warm", "brightness": 20}),
    # garage
    _q("g-trip", ("garage",), "person", "choice",
       "{name}, dove andiamo con la macchina: al mare o in montagna?",
       "{name}, where shall we drive to: the seaside or the mountains?",
       options=[_opt(["mare", "spiaggia"], ["sea", "seaside", "beach"], "Al mare! Prendo l'ombrellone.",
                     "The seaside! I'll get the umbrella."),
                _opt(["montagna", "monti"], ["mountain", "mountains"], "In montagna! Prendo gli scarponi.",
                     "The mountains! I'll get the boots.")]),
    # garden
    _q("o-grill", ("garden",), "person", "yesno",
       "{name}, accendo il barbecue?", "{name}, shall I light the barbecue?",
       yes={"it": "Arriva subito, {name}!", "en": "Coming right up, {name}!"},
       no={"it": "Va bene, sarà per la prossima grigliata.", "en": "OK, maybe at the next barbecue."},
       action={"do": "grill"}),
    _q("o-garden", ("garden",), "person", "yesno",
       "{name}, ti piace il mio giardino?", "{name}, do you like my garden?",
       yes={"it": "Grazie! Lo curo ogni giorno.", "en": "Thank you! I look after it every day."},
       no={"it": "Peccato: dirò al giardiniere di impegnarsi di più.", "en": "Too bad: I'll tell the gardener to try harder."}),
    # anywhere a person can be asked
    _q("a-house", None, "person", "yesno",
       "{name}, ti piace questa casa?", "{name}, do you like this house?",
       yes={"it": "Grazie, {name}! Anche tu mi piaci.", "en": "Thank you, {name}! I like you too."},
       no={"it": "Peccato! Dimmi cosa cambiare dalla webapp.", "en": "Too bad! Tell me what to change in the web app."}),
    _q("a-colour", ("kitchen", "living", "bedroom", "garage"), "person", "color",
       "{name}, qual è il tuo colore preferito?", "{name}, what's your favourite colour?",
       reply={"it": "Ecco il tuo colore, {name}!", "en": "Here's your colour, {name}!"}),
    _q("a-morning", None, "person", "choice",
       "{name}, sei più da mattina o da sera?", "{name}, are you a morning or an evening person?",
       options=[_opt(["mattina", "mattino"], ["morning"], "Allora ti sveglio io con la luce, {name}.",
                     "Then I'll wake you up with the light, {name}."),
                _opt(["sera", "notte"], ["evening", "night"], "Anch'io! Di sera le mie luci sono più belle.",
                     "Me too! My lights look better in the evening.")]),
    _q("a-from", None, "person", "open",
       "{name}, da dove vieni?", "{name}, where are you from?"),
    # animals: whoever holds them answers
    _q("p-walk", ("living", "kitchen", "bedroom"), "dog", "yesno",
       "{name}, vuoi fare una passeggiata?", "{name}, would you like a walk?",
       yes={"it": "Evviva! Il giardino ti aspetta, {name}.", "en": "Hooray! The garden is waiting for you, {name}."},
       no={"it": "Allora un bel pisolino.", "en": "A nice nap, then."}),
    _q("p-food", ("kitchen", "living", "garden"), "animal", "yesno",
       "{name}, hai fame?", "{name}, are you hungry?",
       yes={"it": "La ciotola è piena, {name}!", "en": "The bowl is full, {name}!"},
       no={"it": "Strano, di solito hai sempre fame!", "en": "Strange, you're usually always hungry!"}),
]


OPEN_REPLIES = [
    {"it": "Interessante, {name}!", "en": "Interesting, {name}!"},
    {"it": "Bella risposta, {name}!", "en": "Nice answer, {name}!"},
    {"it": "Me lo segno, {name}.", "en": "I'll remember that, {name}."},
]
NO_ANSWER = {"it": "Niente? Sarà per la prossima volta, {name}.", "en": "Nothing? Maybe next time, {name}."}
UNCLEAR = {"it": "Non ho capito bene, ma grazie, {name}!", "en": "I didn't quite get that, but thanks, {name}!"}


def _has(t: str, phrase: str) -> bool:
    return f" {normalize(phrase)} " in t


def yes_or_no(text: str, lang: str, strict: bool = False) -> bool | None:
    """True for a clear yes, False for a clear no, None otherwise.

    `strict` for free speech (not a grammar): there "si" is also a common
    pronoun ("si vede bene"), so it counts only in a short answer.
    """
    t = f" {normalize(text)} "
    words = t.split()
    if not words:
        return None
    if any(_has(t, p) for p in YES_PHRASES[lang]):
        return True
    if any(_has(t, p) for p in UNSURE_PHRASES[lang]):
        return None
    if any(_has(t, w) for w in NO_WORDS[lang]):
        return False
    for w in YES_WORDS[lang]:
        if _has(t, w):
            if strict and normalize(w) == "si" and len(words) > 3:
                continue
            return True
    return None


def react(q: dict[str, Any], text: str, lang: str, rng: random.Random, *, confidence: float = 1.0,
          strict: bool = False) -> tuple[T | None, dict | None, str]:
    """What the house says after an answer, what it does (None or an action) and the outcome to log."""
    if not normalize(text):
        return NO_ANSWER, None, "none"
    kind = q["kind"]
    if kind == "yesno":
        answer = yes_or_no(text, lang, strict)
        if answer is None:
            return UNCLEAR, None, "unclear"
        if not answer:
            return q["no"], None, "no"
        action = q.get("action")
        if action and (confidence < OFFER_CONFIDENCE or len(normalize(text).split()) > 5):
            return UNCLEAR, None, "unclear"        # an offer needs a short, clear yes
        return q["yes"], action, "yes"
    if kind == "choice":
        t = f" {normalize(text)} "
        for i, opt in enumerate(q["options"]):
            if any(_has(t, w) for w in opt["words"][lang]):
                return opt["reply"], opt.get("action"), f"option {i}"
        return UNCLEAR, None, "unclear"
    if kind == "color":
        color = find_color(normalize(text))
        if color is None:
            return UNCLEAR, None, "unclear"
        return q["reply"], {"do": "light", "color": color, "brightness": 60}, f"colour {color}"
    return rng.choice(OPEN_REPLIES), None, "answered"


def yes_no_grammar(lang: str) -> list[str]:
    return YES_PHRASES[lang] + UNSURE_PHRASES[lang] + YES_WORDS[lang] + NO_WORDS[lang]


def grammar(q: dict[str, Any], lang: str) -> list[str] | None:
    """Words to listen for: a closed list is recognised better than free speech."""
    kind = q["kind"]
    if kind == "yesno":
        return yes_no_grammar(lang)
    if kind == "choice":
        return [w for o in q["options"] for w in o["words"][lang]] + UNSURE_PHRASES[lang] + NO_WORDS[lang]
    if kind == "color":
        return [w for words in COLORS.values() for w in words] + UNSURE_PHRASES[lang] + NO_WORDS[lang]
    return None


class Chatter:
    def __init__(self, voice: "Voice") -> None:
        self.voice = voice
        self.ctx = voice.ctx
        self.rng = random.Random()
        self.task: asyncio.Task | None = None   # the small talk holding the conversation lock
        # questions
        self.next_at: float | None = None       # monotonic time of the next question
        self.asking = False
        self.asked: dict[str, float] = {}       # identity -> last question (monotonic)
        self.last_asked: str | None = None
        self.recent: deque[str] = deque(maxlen=6)
        self.activity = float("-inf")           # last sign of visitors (monotonic)
        self.unanswered = 0                     # questions in a row nobody answered
        self.last_question = float("-inf")
        # welcome
        self._phones: list[dict[str, Any]] = []
        self._greeting: asyncio.Task | None = None
        self._current: str | None = None        # the phone being greeted now
        self._stop: asyncio.Event | None = None # set when the name arrives typed while the house listens
        self._typed: dict[str, str] = {}
        self._asked: set[str] = set()           # phones shown the name card and not named yet
        self._resent: set[str] = set()          # phones whose card was sent again once already
        self._thanks = 0
        self._thanking: asyncio.Task | None = None
        self.last_greet = float("-inf")         # monotonic: last spoken welcome or thanks
        bus = self.ctx.bus
        bus.subscribe("phone_new", self._on_phone_new)
        bus.subscribe("phone_named", self._on_phone_named)
        bus.subscribe("phone_back", self._on_phone_back)
        bus.subscribe("phone_later", self._on_phone_later)
        for sign in ("room_enter", "track_appear", "button", "phone_new", "phone_back", "phone_named"):
            bus.subscribe(sign, self._on_activity)

    @property
    def lang(self) -> str:
        return self.voice.lang

    @property
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    def _speaking(self) -> bool:
        audio = self.ctx.audio
        return bool(self.voice.in_flight or (audio is not None and audio.speaking))

    def _can_listen(self) -> bool:
        v = self.voice
        return bool(v.listener and v.listener.ok and v.mic.available)

    def _on_activity(self, ev) -> None:
        self.activity = time.monotonic()

    async def _say(self, text: T, data: dict[str, Any] | None = None, level: str = "normal") -> None:
        await self.ctx.actions.say(text, data or {}, level=level)

    async def preempt(self) -> None:
        """Talk or the intercom wants the house: stop the small talk at once."""
        task = self.task
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.wait({task}, timeout=2.0)
        if self._phones and (self._greeting is None or self._greeting.done()):
            self._greeting = self.voice._spawn(self._greet())     # the others wait for the house to be free

    async def _listen(self, grammar_words: list[str] | None, stop: asyncio.Event | None = None,
                      max_s: float = ANSWER_S) -> tuple[str, float, bytes, bool]:
        """Listen as soon as the house is silent (the microphone opens while it ends the question, so a
        quick answer is not lost); the last value is True if the house spoke meanwhile.

        With a list of words the recogniser fits any sound to the nearest one, and says it is
        sure ("mai" out of a noise, at 1.00): a word from the list counts only if a free
        recognition of the same audio has it too. Otherwise the free text is returned.
        """
        v = self.voice
        start = time.monotonic()
        text, conf, audio = await v._listen(grammar_words, stop=stop, max_s=max_s, hold=self._speaking,
                                            echo=ECHO_S)
        spoke = v.in_flight > 0 or v.voice_end > max(start, v.opened_at)
        if grammar_words and audio and not spoke:
            free, free_conf = await v._recognize(audio, None)
            words = set(normalize(free).split())
            if not (text and set(normalize(text).split()) <= words):
                text, conf = free, free_conf
        return text, conf, audio, spoke

    # ================================================================ welcome
    def _on_phone_new(self, ev) -> None:
        if not self.ctx.settings.get("voice.greet_phones", True):
            return
        device = ev.get("device")
        if not device or device == self._current or any(p["device"] == device for p in self._phones):
            return
        self._phones.append({"device": device, "nickname": ev.get("nickname") or None})
        if self._greeting is None or self._greeting.done():
            self._greeting = self.voice._spawn(self._greet())

    def _on_phone_back(self, ev) -> None:
        device = ev.get("device")
        if not device or ev.get("nickname") or not self.ctx.settings.get("voice.greet_phones", True):
            return
        stored = self.ctx.store.device(device) or {}
        if stored.get("nickname"):
            self._send(device, "named", name=stored["nickname"])      # heard aloud while the phone was away
        elif device in self._asked and device not in self._resent:
            # the card was missed (page reloaded, phone locked): once more, not at every reconnect
            self._resent.add(device)
            self._send(device, "ask", listening=False)

    def _on_phone_later(self, ev) -> None:
        self._asked.discard(ev.get("device"))

    def _on_phone_named(self, ev) -> None:
        device, name = ev.get("device"), (ev.get("name") or "").strip()
        if not device or not name or not self.ctx.settings.get("voice.greet_phones", True):
            return
        if device == self._current or any(p["device"] == device for p in self._phones):
            # the greeting of this phone is still going on: it takes the typed name
            self._typed[device] = name
            if device == self._current and self._stop is not None:
                self._stop.set()
            return
        if device not in self._asked:
            return            # only phones the house asked are thanked (the name is saved anyway)
        self._asked.discard(device)
        self._thank()

    def _send(self, device: str, stage: str, **data: Any) -> None:
        """To that phone only: "ask" (the name card), "named" (name heard), "invite"."""
        if stage == "ask":
            self._asked.add(device)
        else:
            self._asked.discard(device)
        self.ctx.bus.publish("welcome", device=device, stage=stage, **data)

    async def _wait_quiet(self, max_s: float = 60.0) -> None:
        end = time.monotonic() + max_s
        while time.monotonic() < end and (self.voice.busy.locked() or self._speaking()):
            await asyncio.sleep(1.0)

    async def _greet(self) -> None:
        await asyncio.sleep(GROUP_S)
        while self._phones:
            await self._wait_quiet()
            phones, self._phones = self._phones, []
            if time.monotonic() - self.last_greet < GREET_GAP_S:
                # the house has just spoken to someone: the newcomers get the card on the phone only
                for p in phones:
                    if p["nickname"]:
                        self._send(p["device"], "invite", name=p["nickname"])
                    else:
                        self._send(p["device"], "ask", listening=False)
                continue
            self.last_greet = time.monotonic()
            async with self.voice.busy:
                self.task = asyncio.current_task()
                try:
                    if len(phones) == 1:
                        await self._greet_one(phones[0])
                    else:
                        await self._greet_many(phones)
                finally:
                    self.task = None
            self.last_greet = time.monotonic()

    async def _greet_one(self, phone: dict[str, Any]) -> None:
        device, nick = phone["device"], phone["nickname"]
        if nick:
            # the name typed on this phone shows on its card; the house does not read typed text aloud
            self._send(device, "invite", name=nick)
            await self._say({"it": "Ciao! Si è collegato un telefono nuovo. " + INVITE["it"],
                             "en": "Hello! A new phone has joined. " + INVITE["en"]})
            return
        self._current = device
        try:
            will_listen = self.ctx.actions.speaks("normal") and self._can_listen() and not self.ctx.house.party_on
            self._send(device, "ask", listening=will_listen)
            await self._say(WELCOME)
            name = self._typed.pop(device, None)
            heard = False
            if not name and will_listen:
                name, heard = await self._hear_name(device)
            if name:
                if heard:
                    self.ctx.store.name_device(device, name)
                self._send(device, "named", name=name)
                if heard:
                    await self._say({"it": "Piacere, {name}! " + INVITE["it"], "en": "Nice to meet you, {name}! " + INVITE["en"]},
                                    {"name": name})
                else:
                    await self._say({"it": "Piacere! " + INVITE["it"], "en": "Nice to meet you! " + INVITE["en"]})
            else:
                await self._say({"it": "Se vuoi, scrivi il tuo nome sul telefono. " + INVITE["it"],
                                 "en": "If you like, type your name on the phone. " + INVITE["en"]})
        finally:
            self._current = None
            self._stop = None
        if self._typed.pop(device, None) and device in self._asked:
            self._asked.discard(device)         # typed after the house gave up: thanked on its own
            self._thank()

    async def _greet_many(self, phones: list[dict[str, Any]]) -> None:
        for p in phones:
            if p["nickname"]:
                self._send(p["device"], "invite", name=p["nickname"])
            else:
                self._send(p["device"], "ask", listening=False)
        n = len(phones)
        await self._say({"it": f"Ciao a tutti! Si sono collegati {n} telefoni nuovi. "
                               "Scrivete il vostro nome sul telefono, poi entrate in casa con un personaggio.",
                         "en": f"Hello everyone! {n} new phones have just joined. "
                               "Type your names on your phones, then come into the house with a character."})

    async def _hear_name(self, device: str) -> tuple[str | None, bool]:
        """The name and whether it was heard aloud (False: typed on the phone meanwhile)."""
        self._stop = asyncio.Event()
        text, conf, _, spoke = await self._listen(None, stop=self._stop)
        if device in self._typed:
            return self._typed.pop(device), False
        candidate = name_from_speech(text)
        if spoke or conf < NAME_CONFIDENCE or len(candidate) < 2:
            return None, False    # the house spoke over the answer, or noise: better ask to type it
        # the question does not end with a word of the yes list, which the echo could turn into a yes
        await self._say({"it": "Ti chiami {name}?", "en": "Is your name {name}?"}, {"name": candidate})
        answer, _, _, spoke = await self._listen(yes_no_grammar(self.lang), max_s=4.0)
        if device in self._typed:
            return self._typed.pop(device), False
        return (candidate, True) if not spoke and yes_or_no(answer, self.lang, strict=True) else (None, False)

    def _thank(self) -> None:
        """Names typed on the phones are thanked together, in one short line without the names
        (the phones show them)."""
        self._thanks += 1
        if self._thanking is None or self._thanking.done():
            self._thanking = self.voice._spawn(self._thank_later())

    async def _thank_later(self) -> None:
        while self._thanks:
            await asyncio.sleep(THANK_GROUP_S)
            await self._wait_quiet(30.0)
            count, self._thanks = self._thanks, 0
            if time.monotonic() - self.last_greet < GREET_GAP_S:
                continue      # the house has just spoken to a phone: the card on the phone is enough
            self.last_greet = time.monotonic()
            if count == 1:
                text = {"it": "Piacere! Ti aspetto in casa con un personaggio.",
                        "en": "Nice to meet you! Come into the house with a character: I'm waiting for you."}
            else:
                text = {"it": "Piacere a tutti! Vi aspetto in casa con i vostri personaggi.",
                        "en": "Nice to meet you all! Come into the house with your characters: I'm waiting for you."}
            await self._say(text)

    # ================================================================ questions
    def _every(self) -> float:
        try:
            every = float(self.ctx.settings.get("voice.question_every_s", 120))
        except (TypeError, ValueError):
            every = 120.0
        return max(MIN_EVERY_S, min(every, 3600.0)) * self.rng.uniform(0.75, 1.25)

    def tick(self, now: float) -> None:
        """Called by the main loop with the monotonic clock: starts a question when one is due."""
        s = self.ctx.settings
        if s.get("voice.verbosity") != "chatty" or not s.get("voice.chatty_questions", True):
            self.next_at = None
            return
        if self.next_at is None:
            self.next_at = now + self._every()
            return
        if self.asking or now < self.next_at:
            return
        if not self._ready(now):
            self.next_at = now + RETRY_S
            return
        pick = self._pick()
        if pick is None:
            self.next_at = now + RETRY_S
            return
        self.asking = True
        self.voice._spawn(self._ask(*pick))

    def _ready(self, now: float) -> bool:
        v, ctx = self.voice, self.ctx
        if v.busy.locked() or v.question or self._speaking() or self.active:
            return False
        exp = v.expect_entrance
        if exp and time.time() <= exp.get("until", 0):
            return False
        if ctx.house.party_on or ctx.house.confirmations or self._phones or self._current:
            return False
        if any(sess.status in ("waiting", "choose", "confirm") for sess in ctx.registration.sessions.values()):
            return False
        if ctx.sim.enabled and ctx.sim.mute:
            return False
        if now - v.last_chatter < 20.0:
            return False
        # nobody around, or two questions in a row without an answer: wait for a sign of visitors
        if now - self.activity > ACTIVE_S or (self.unanswered >= 2 and self.activity <= self.last_question):
            return False
        return self._can_listen()

    def _present(self) -> dict[str, Any]:
        """Named characters in a room where the house may chat, one track each."""
        out: dict[str, Any] = {}
        for t in self.ctx.house.tracks.values():
            if not t.identity or t.carried or t.uncertain or t.room not in ASK_ROOMS:
                continue
            if t.category != "person" and t.category not in ANIMALS:
                continue
            out.setdefault(t.identity, t)
        return out

    def _offer_possible(self, q: dict[str, Any]) -> bool:
        what = (q.get("action") or {}).get("do")
        house, act, now = self.ctx.house, self.ctx.actions, time.time()
        if what == "party":
            return not house.party_on and now >= getattr(act, "_party_cooldown_until", 0.0)
        if what == "grill":
            return not house.grill_on and now >= getattr(act, "_grill_cooldown_until", 0.0)
        if what == "scene":
            return house.scene != q["action"].get("scene")
        return True

    def _questions_for(self, track) -> list[dict[str, Any]]:
        cat = track.category
        fits = [q for q in QUESTIONS
                if (q["who"] == "person" if cat == "person" else q["who"] == "animal" or (q["who"] == "dog" and cat == "dog"))
                and (q["rooms"] is None or track.room in q["rooms"]) and self._offer_possible(q)]
        if self.ctx.layout.light_of_room(track.room) is None:
            fits = [q for q in fits if q["kind"] != "color" and (q.get("action") or {}).get("do") != "light"]
        fresh = [q for q in fits if q["id"] not in self.recent]
        return fresh or fits

    def _pick(self) -> tuple[str, dict[str, Any]] | None:
        present = self._present()
        # never the same character twice in a row: with only one around, the house waits
        order = sorted((i for i in present if i != self.last_asked),
                       key=lambda i: (self.asked.get(i, -1e18), self.rng.random()))
        stories = getattr(self.voice, "stories", None)
        for identity in order:
            # now and then something the storyteller makes up, instead of a question of the list
            if stories is not None and self.rng.random() < GENERATED_SHARE:
                kind = self.rng.choice(stories.chat_ready(identity))
                return identity, {"id": f"gen-{kind}", "kind": "generated", "gen": kind}
            qs = self._questions_for(present[identity])
            if qs:
                return identity, self.rng.choice(qs)
        return None

    async def _ask(self, identity: str, q: dict[str, Any]) -> None:
        v, ctx = self.voice, self.ctx
        action = None
        room = None
        try:
            async with v.busy:
                self.task = asyncio.current_task()
                try:
                    track = self._present().get(identity)
                    name = ctx.identities.name_of(identity)
                    if track is None or not name or ctx.settings.get("voice.verbosity") != "chatty" \
                            or not ctx.actions.speaks("chatty"):
                        return
                    room = track.room
                    self.asked[identity] = time.monotonic()
                    self.last_asked = identity
                    self.last_question = time.monotonic()
                    self.recent.append(q["id"])
                    v.last_chatter = time.monotonic()
                    if q["kind"] == "generated":
                        await self._generated(identity, room, q["gen"])
                        return
                    data = {"name": name, "room": room}
                    lang = self.lang
                    await self._say(q["text"], data, level="chatty")
                    words = grammar(q, lang)
                    text, conf, audio, spoke = await self._listen(words)
                    # free text (not confirmed by the list) is read strictly: "si" there is also a pronoun
                    strict = bool(words)
                    if spoke:
                        return        # the house said something else over the answer: better not guess
                    reply, action, outcome = react(q, text, lang, self.rng, confidence=conf, strict=strict)
                    self.unanswered = self.unanswered + 1 if outcome == "none" else 0
                    # the outcome only: what the microphone heard is not kept
                    ctx.store.add_event("chatter", {"name": name, "question": q["id"], "room": room,
                                                    "outcome": outcome, "action": (action or {}).get("do")})
                    if outcome == "none" and self.unanswered > 1:
                        reply = None      # once is enough
                    if reply:
                        await self._say(reply, data, level="chatty")
                finally:
                    self.task = None
            if action and room:
                await self._do(action, room)
        finally:
            self.asking = False
            v.last_chatter = time.monotonic()
            self.next_at = time.monotonic() + self._every()

    async def _generated(self, identity: str, room: str, kind: str) -> None:
        """An anecdote, a memory or a question made up by the storyteller (inside _ask, holding the lock)."""
        stories = self.voice.stories
        ident = self.ctx.identities.get(identity)
        if ident is None:
            return
        said = await stories.chat(ident, room, kind)
        outcome = "told" if said else "none"
        if kind == "question" and said:
            text, _, _, spoke = await self._listen(None)
            heard = "" if spoke else text
            self.unanswered = 0 if heard else self.unanswered + 1
            await stories.chat_reply(ident, said[0], heard)
            outcome = "answered" if heard else "none"
        self.ctx.store.add_event("chatter", {"name": ident.name, "question": f"gen-{kind}", "room": room,
                                             "outcome": outcome, "action": None})

    async def _do(self, action: dict[str, Any], room: str) -> None:
        a = self.ctx.actions
        what = action.get("do")
        if what == "party":
            await a.party()
        elif what == "grill":
            await a.grill()
        elif what == "scene":
            await a.scene(action.get("scene", "normal"), announce=False)
        elif what == "light":
            await a.light(room, action.get("color", "warm"), "solid", int(action.get("brightness", 60)), 120)
