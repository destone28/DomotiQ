# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the visitor means when the house asks who a newcomer is.

"In cucina vedo una persona nuova, giusto? Come si chiama?" may be answered
with a name ("Marco", "si chiama Marco"), with what it really is ("no, è un
cane", "è un gatto e si chiama Micia"), with a yes or a no, by saying that
there is nothing there ("non c'è nessuno in cucina", "è la mia mano": the
house saw wrong), by not knowing, or with something else entirely (a joke,
another question).

Short, common answers are understood at once by a few rules. Any other
sentence goes to the language model, which only classifies it: a grammar
forces its output to one of the forms below, and a name it gives counts only
if it is in the sentence. Its instructions and examples stay in a slot of
llama-server of their own, read once after each start, so an answer takes a
couple of seconds on the board.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import answers
from .intents import Intent, find_names, normalize
from .intents import parse as parse_command

if TYPE_CHECKING:
    from .manager import Voice

KINDS = ("person", "dog", "cat", "animal", "car", "object")
ANIMAL_KINDS = ("dog", "cat", "animal")


@dataclass
class Reply:
    kind: str                       # name, kind, yes, no, none_of, nobody, unknown, wait, other, silence
    category: str | None = None     # what it is, when the answer says so
    name: str | None = None
    source: str = "rules"
    intent: Intent | None = None    # a command of the house said instead of an answer


# ------------------------------------------------------------------ rules
KIND_WORDS = {
    "person": ["persona", "uomo", "donna", "bambino", "bambina", "ragazzo", "ragazza", "signore", "signora",
               "omino", "fratello", "sorella", "amico", "amica", "figlio", "figlia", "nonno", "nonna", "zio",
               "zia", "cugino", "cugina", "papa", "mamma", "padre", "madre", "marito", "moglie", "person",
               "man", "woman", "boy", "girl", "child", "kid", "lady", "human", "brother", "sister", "friend",
               "son", "daughter", "grandpa", "grandma", "grandfather", "grandmother", "uncle", "aunt", "cousin",
               "dad", "mum", "mom", "father", "mother", "husband", "wife"],
    "dog": ["cane", "cagnolino", "cagnolina", "cucciolo", "dog", "puppy", "doggy"],
    "cat": ["gatto", "gatta", "gattino", "gattina", "cat", "kitten"],
    "animal": ["animale", "uccello", "uccellino", "coniglio", "criceto", "tartaruga", "pesce", "pesciolino",
               "cavallo", "pappagallo", "topo", "topolino", "maiale", "maialino", "mucca", "pecora", "papera",
               "anatra", "gallina", "pulcino", "scoiattolo", "volpe", "orso", "leone", "tigre", "elefante",
               "giraffa", "scimmia", "serpente", "lucertola", "rana", "farfalla", "riccio", "furetto", "porcellino",
               "animal", "bird", "rabbit", "bunny", "hamster", "turtle", "tortoise", "fish", "horse", "pony",
               "parrot", "pet", "mouse", "pig", "cow", "sheep", "duck", "chicken", "squirrel", "fox", "bear", "lion",
               "tiger", "elephant", "giraffe", "monkey", "snake", "lizard", "frog", "hedgehog", "ferret"],
    "car": ["auto", "macchina", "automobile", "macchinina", "car"],
    "object": ["oggetto", "pianta", "vaso", "lampada", "giocattolo", "pupazzo", "peluche", "palla", "scatola",
               "sedia", "tavolo", "object", "thing", "plant", "toy", "lamp", "vase", "ball", "box", "chair", "table",
               "puppet", "doll", "bambola"],
}
KIND_OF = {w: kind for kind, nouns in KIND_WORDS.items() for w in nouns}
DIMINUTIVES = ("etto", "etta", "ino", "ina", "ello", "ella", "otto", "otta", "uccio", "uccia")


def _kind_of(word: str) -> str | None:
    """The kind a noun names, diminutives too ("coniglietto", "gattina")."""
    if word in KIND_OF:
        return KIND_OF[word]
    for suffix in DIMINUTIVES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            stem = word[:-len(suffix)]
            for end in ("o", "a", "e", "io"):
                if KIND_OF.get(stem + end) in ("person", "dog", "cat", "animal"):
                    return KIND_OF[stem + end]     # not objects: "pallino" is a name, not a small ball
    return None
UNKNOWN = {"it": ["non lo so", "non so", "boh", "chi lo sa", "non saprei", "non ne ho idea", "decidi tu",
                  "scegli tu", "non te lo dico", "non mi va", "piu tardi", "lascia perdere", "lascia stare",
                  "lasciamo stare", "lasciamo perdere", "non importa", "fa niente"],
           "en": ["i don t know", "don t know", "dunno", "no idea", "not sure", "you decide", "you choose",
                  "won t tell", "don t want to tell", "later", "never mind", "forget it", "doesn t matter"]}
# hold on: the visitor is thinking, or asking someone
WAIT = {"it": ["aspetta", "un attimo", "un momento", "un secondo", "fammi pensare", "vediamo"],
        "en": ["wait", "hold on", "one moment", "a moment", "just a second", "let me think"]}
# what follows a noun without being a name: "un gatto nero", "a big dog"
QUALITIES = {"nero", "nera", "bianco", "bianca", "rosso", "rossa", "grigio", "grigia", "marrone", "giallo",
             "gialla", "verde", "blu", "azzurro", "azzurra", "rosa", "viola", "arancione", "grande", "piccolo",
             "piccola", "nuovo", "nuova", "vecchio", "vecchia", "bello", "bella", "carino", "carina", "black",
             "white", "red", "grey", "gray", "brown", "yellow", "green", "blue", "pink", "big", "small", "little",
             "new", "old", "nice", "cute", "mio", "mia", "tuo", "tua", "suo", "sua", "nostro", "nostra"}
QUESTION_WORDS = {"perche", "come", "cosa", "chi", "dove", "quando", "quanto", "quanti", "why", "how", "what",
                  "who", "where", "when"}
# the commands of the house that are no answer at all: "che ore sono?" is answered, then the house asks again
OTHER_INTENTS = {"time_now", "set_time", "story", "joke", "party", "grill", "lights_on", "lights_off", "scene",
                 "language", "volume", "verbosity", "help", "who_are_you", "house_summary", "temperature",
                 "humidity", "car_where", "where_is", "who_in", "count", "recall", "remember", "fact"}
NONE_OF = {"it": ["nessuno di questi", "nessuno dei due", "nessuno di loro", "un altro", "un altra"],
           "en": ["none of these", "none of them", "neither", "another one", "someone else", "something else"]}
# there is nothing there: a reflection, a shadow, a hand
NOBODY = {"it": ["non c e nessuno", "non c e niente", "non c e nulla", "non ce nessuno", "non ce niente",
                 "non c e nessun", "non c e nessuna", "non vedo niente", "non vedo nessuno",
                 "anima viva", "nessuno", "niente", "nulla", "vuoto", "vuota", "ti sbagli", "visto male",
                 "ti sei sbagliata", "ti sei sbagliato", "hai sbagliato", "ombra", "riflesso", "riflessi",
                 "un errore", "falso allarme", "dito", "dita", "mano", "mani", "braccio", "polso", "gomito"],
          "en": ["nobody", "no one", "noone", "nothing", "empty", "you re wrong", "you are wrong", "shadow",
                 "reflection", "a mistake", "false alarm", "finger", "fingers", "hand", "hands", "arm", "wrist",
                 "elbow"]}
YES = {"it": ["si", "certo", "esatto", "giusto", "corretto", "ok", "okay", "va bene", "proprio cosi", "esattamente",
              "certamente", "sicuro", "si si", "certo che si"],
       "en": ["yes", "yeah", "yep", "right", "correct", "exactly", "sure", "ok", "okay", "that s right", "yes yes"]}
NO = {"it": ["no", "sbagliato", "non proprio", "macche", "per niente", "no no", "non e cosi"],
      "en": ["no", "nope", "wrong", "not really", "not at all", "no no"]}
NEGATIONS = {"non", "not", "isn", "no", "nope", "macche", "neanche", "nemmeno", "nessun", "nessuna"}
# said to the house, not about the newcomer: "sei bellissima", "you're funny"
TO_THE_HOUSE = ["sei", "you re", "you are", "ti voglio", "ti amo", "i love you"]
# "si chiama Marco", "un gatto di nome Tom", "chiamalo Pippo", "her name is Anna", "a dog called Rex"
INTRO = ["si chiama", "che si chiama", "di nome", "chiamato", "chiamata", "lo chiamo", "la chiamo", "chiamalo",
         "chiamala", "lo chiamiamo", "la chiamiamo", "chiamiamolo", "chiamiamola", "il suo nome e", "il nome e",
         "mi chiamo", "its name is", "his name is", "her name is", "the name is", "name is", "called", "named",
         "call it", "call him", "call her"]
# after "è" or "it's" only a name said alone: "è Marco", "it's Tom"
SHORT_INTRO = ["e", "sono", "it s", "it is", "he s", "she s", "he is", "she is", "this is", "that s", "i m", "i am"]
STOP = {"e", "ed", "and", "ma", "but", "che", "who", "perche", "because", "con", "with", "in", "nel", "nella",
        "a", "al", "alla", "da", "dal", "dalla", "di", "del", "della", "of", "from", "per", "for", "se", "if"}
FILLERS = {"tipo", "ehm", "eh", "uhm", "praticamente", "allora", "beh", "dunque", "like", "um", "uh", "well",
           "so", "pure", "proprio", "credo", "penso", "think", "guess", "il", "la", "lo", "l", "the", "mio", "mia",
           "my", "suo", "sua", "his", "her"}
# words that are no name ("grazie" said alone is not a newcomer called Grazie)
NOT_NAMES = {"grazie", "ciao", "prego", "ecco", "forse", "aspetta", "dai", "cosa", "come", "perche", "chi",
             "dove", "quando", "quale", "quello", "quella", "questo", "questa", "lui", "lei", "io", "tu", "boh",
             "mah", "hmm", "thanks", "thank", "hello", "hi", "what", "who", "why", "where", "when", "which",
             "that", "this", "he", "she", "it", "me", "you", "wait", "casa", "house", "un", "una", "uno", "an",
             "sei", "fai", "dimmi", "accendi", "spegni", "brava", "bravo", "bella", "bello", "stupida", "scemo",
             "scema", "festa", "ora", "ore", "tempo", "are", "is", "do", "does", "can", "please", "sorry", "scusa",
             "anche", "molto", "tanto", "poco", "qui", "li", "la", "here", "there", "si", "yes", "no", "ok", "okay"}
MAX_RULE_WORDS = 7          # longer answers go to the language model


def _has(t: str, phrase: str) -> bool:
    return f" {normalize(phrase)} " in f" {t} "


def _negated(words: list[str], i: int) -> bool:
    """Is the word at i denied ("non è un cane", "macché persona", "not a cat", "non è Viola")?"""
    j = i - 1
    while j >= 0 and words[j] in ("un", "una", "uno", "a", "an", "il", "la", "lo", "l", "e", "is", "s", "the",
                                  "proprio", "mica", "really"):
        j -= 1
    if j >= 1 and words[j - 1] == "ma" and words[j] == "quale":
        return True                                     # "ma quale persona": not a person at all
    return j >= 0 and words[j] in NEGATIONS and (words[j] != "no" or j == i - 1)


def _kinds(words: list[str]) -> list[str]:
    """What the answer says it is, leaving out what it denies and what only qualifies something else
    ("il riflesso della lampada", "il cane di Viola" is a dog)."""
    found = []
    for i, w in enumerate(words):
        kind = _kind_of(w)
        if not kind or kind in found or _negated(words, i):
            continue
        if i and words[i - 1] in ("di", "del", "della", "dello", "dei", "delle", "degli", "of") and found == []:
            if any(_kind_of(x) or x in NOBODY_WORDS for x in words[:i]):
                continue
        found.append(kind)
    return found


NOBODY_WORDS = {w for lang in NOBODY.values() for p in lang for w in p.split() if len(p.split()) == 1}


def _known(words: list[str], names: list[str]) -> list[str]:
    """The registered names in the answer, also when the recognizer got a letter wrong ("rosario" for
    Rosaria), except those it denies ("non è Viola, è Rosaria")."""
    found: list[tuple[int, str]] = []
    taken: set[int] = set()
    for n in sorted(names, key=lambda x: -len(x)):
        key = normalize(n).split()
        if not key:
            continue
        best, at = 0.0, -1
        for i in range(len(words) - len(key) + 1):
            if taken & set(range(i, i + len(key))):
                continue
            gram = " ".join(words[i:i + len(key)])
            r = 1.0 if gram == " ".join(key) else difflib.SequenceMatcher(None, gram, " ".join(key)).ratio()
            if r > best:
                best, at = r, i
        if at >= 0 and (best == 1.0 or best >= 0.8 and len(" ".join(key)) >= 5):
            taken |= set(range(at, at + len(key)))
            if not _negated(words, at):
                found.append((at, n))
    return [n for _, n in sorted(found)]


def _take_name(words: list[str]) -> str | None:
    picked = []
    for w in words:
        if w in FILLERS and not picked:
            continue
        if w in STOP or w in NEGATIONS or _kind_of(w) or w.isdigit():
            break
        if w in NOT_NAMES:
            return None
        picked.append(w)
        if len(picked) == 2:
            break
    return _title(picked) if picked else None


def _title(words: list[str]) -> str:
    return " ".join(w.capitalize() for w in words)


def _new_name(words: list[str]) -> str | None:
    """A name introduced by "si chiama", "di nome", "called"..., or right after "mio fratello", "il mio cane"."""
    t = " ".join(words)
    for intro in sorted(INTRO, key=len, reverse=True):
        key = f" {intro} "
        if key in f" {t} ":
            rest = f" {t} ".split(key, 1)[1].split()
            name = _take_name(rest)
            if name:
                return name
    for i, w in enumerate(words[:-1]):
        if _kind_of(w) not in (None, "object") and not _negated(words, i):
            name = _take_name(words[i + 1:])
            if name and words[i + 1] not in FILLERS and words[i + 1] not in QUALITIES:
                return name
    return None


def by_rules(text: str, lang: str, names: list[str]) -> Reply | None:
    """A short, clear answer; None when the sentence needs the language model."""
    t = normalize(text)
    if not t:
        return Reply("silence")
    words = t.split()
    if any(_has(t, p) for p in UNKNOWN[lang]):
        return Reply("unknown")
    if any(t == normalize(p) or t.startswith(normalize(p) + " ") for p in WAIT[lang]):
        return Reply("wait")
    known, kinds = _known(words, names), _kinds(words)
    if any(_has(t, p) for p in NONE_OF[lang]) and not known and not kinds:
        return Reply("none_of")
    if any(_has(t, p) for p in NOBODY[lang]) and not known and (not kinds or kinds == ["object"]):
        return Reply("nobody")
    if not known and not kinds and any(w in ("nessun", "nessuna", "nessuno") and i + 1 < len(words)
                                       and _kind_of(words[i + 1]) for i, w in enumerate(words)):
        return Reply("nobody")                          # "nessuna persona", "nessun animale"
    if words[0] in QUESTION_WORDS and not known and not kinds:
        return Reply("other")                           # "perché me lo chiedi?": a question, no answer
    if any(t.startswith(p + " ") for p in TO_THE_HOUSE):
        return Reply("other")
    command = parse_command(text, names)
    if command is not None and command.name in OTHER_INTENTS and not (
            command.name == "where_is" and known and not {"dov", "dove", "where"} & set(words)):
        return Reply("other", intent=command)        # "dov'è Viola?", "accendi la luce": not an answer
    if len(words) > MAX_RULE_WORDS:
        return None
    named = _new_name(words)
    if len(known) == 1 and len(kinds) <= 1 and not named:
        return Reply("name", kinds[0] if kinds else None, known[0])
    if known or len(kinds) > 1:
        return None
    if kinds:
        return Reply("kind", kinds[0], named)
    if t in [normalize(p) for p in NO[lang]]:
        return Reply("no")
    if t in [normalize(p) for p in YES[lang]]:
        return Reply("yes")
    if named:
        return Reply("name", None, named)
    rest = words
    for intro in sorted(SHORT_INTRO + [normalize(w) for w in YES[lang]], key=len, reverse=True):
        if t.startswith(intro + " "):
            rest = t[len(intro) + 1:].split()
            break
    if any(w in NEGATIONS for w in rest):
        return None
    if len(rest) <= 2 and not any(w in NOT_NAMES or w in STOP or w.isdigit() for w in rest):
        return Reply("name", None, _title(rest))          # a name said alone, "è Marco", "sì, Marco"
    return None


# ------------------------------------------------------------------ language model
SYSTEM = """A model smart home has seen something new in a room and asked the visitor what it is (a person, an animal, a car or an object) and its name. Classify the visitor's answer.
Forms: name NAME (it gives the name), kind KIND (it says what it is), kind KIND NAME (both), yes (it agrees, no name), no (it disagrees, nothing else), nobody (there is nothing there: the house saw wrong, a reflection, a shadow, a hand), unknown (the visitor does not know or will not say), other (anything else: a joke, a question, chit-chat).
KIND is one of: person, dog, cat, animal, car, object. NAME is copied from the answer.
Answers may be in Italian or English and may contain recognition errors."""

_EXAMPLES = [
    ("si chiama Marco", "name Marco"), ("Giulia", "name Giulia"), ("her name is Anna", "name Anna"),
    ("chiamalo pure Pippo", "name Pippo"), ("it's Tom", "name Tom"), ("è mia nonna Pina", "kind person Pina"),
    ("non c'è nessuno in giardino", "nobody"), ("ma guarda che lì non c'è niente", "nobody"),
    ("è la mia mano", "nobody"), ("è solo un'ombra", "nobody"), ("ti sbagli, la cucina è vuota", "nobody"),
    ("there's nobody in the garden", "nobody"), ("that's just my hand", "nobody"),
    ("you're wrong, it's empty", "nobody"),
    ("è un cane", "kind dog"), ("no, è un gatto e si chiama Micia", "kind cat Micia"),
    ("it's a dog called Rex", "kind dog Rex"), ("non è un animale, è una persona", "kind person"),
    ("si chiama Luca ed è un bambino", "kind person Luca"), ("è una tartaruga", "kind animal"),
    ("è il cane di Viola", "kind dog"), ("è la mia macchina", "kind car"), ("una lampada", "kind object Lampada"),
    ("it's a plant", "kind object Plant"), ("no it's a cat", "kind cat"),
    ("sì", "yes"), ("certo, è una persona", "yes"), ("yes", "yes"),
    ("no", "no"), ("no, non è una persona", "no"), ("no it isn't", "no"),
    ("non lo so", "unknown"), ("boh, decidi tu", "unknown"), ("I have no idea", "unknown"),
    ("che ore sono", "other"), ("sei proprio stupida", "other"), ("what's the weather like", "other"),
    ("accendi la luce in cucina", "other"), ("ahahah", "other"), ("tell me a joke", "other"),
    ("sei bellissima", "other"), ("grazie mille", "other"), ("è il mio pupazzo preferito", "kind object"),
    ("no, è un uccellino", "kind animal"), ("è mio fratello Andrea", "kind person Andrea"),
    ("no non è Viola, è Rosaria", "name Rosaria"),
]


def _mixed(examples: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out = list(examples)
    random.Random(5).shuffle(out)
    return out


EXAMPLES = _mixed(_EXAMPLES)
MIN_CONFIDENCE = 0.4       # below this the form was a guess: better to ask again


def _user(sentence: str) -> str:
    return f"Answer: {sentence}"


def messages(sentence: str) -> list[dict[str, str]]:
    out = [{"role": "system", "content": SYSTEM}]
    for said, form in EXAMPLES:
        out.append({"role": "user", "content": _user(said)})
        out.append({"role": "assistant", "content": form})
    out.append({"role": "user", "content": _user(sentence)})
    return out


GRAMMAR = "\n".join([
    'root ::= "name " name | "kind " kind (" " name)? | "yes" | "no" | "nobody" | "unknown" | "other"',
    f'kind ::= {" | ".join(json.dumps(k) for k in KINDS)}',
    'name ::= word (" " word)?',
    "word ::= [A-Za-zÀ-ÿ] [A-Za-zÀ-ÿ']{0,15}",
])


def _in_sentence(name: str, sentence: str) -> bool:
    """Every word of the name is in the sentence (give or take a letter): the model may not invent it."""
    said = normalize(sentence).split()
    for w in normalize(name).split():
        if w not in said and not difflib.get_close_matches(w, said, n=1, cutoff=0.8):
            return False
    return True


def parse(form: str, sentence: str, names: list[str], confidence: float = 1.0) -> Reply | None:
    """The model's form, checked against the sentence: what it is and the registered names are read in the
    sentence itself, the model only tells what kind of answer it is (and a new name, if the rules missed it)."""
    out = form.strip().split()
    if not out or out[0] not in ("name", "kind", "yes", "no", "nobody", "unknown", "other"):
        return None
    head = out[0]
    if confidence < MIN_CONFIDENCE:
        return Reply("other", source="llm")             # a guess: ask again rather than act on it
    words = normalize(sentence).split()
    if any(" ".join(words).startswith(p + " ") for p in TO_THE_HOUSE):
        return Reply("other", source="llm")             # "sei bellissima": said to the house
    known, kinds = _known(words, names), _kinds(words)
    given = _title(normalize(" ".join(out[2 if head == "kind" else 1:])).split()) or None
    if given and (not _in_sentence(given, sentence) or any(w in NOT_NAMES or _kind_of(w) or w in QUALITIES
                                                          for w in normalize(given).split())):
        given = None
    if given:
        fixed = _known(normalize(given).split(), names)
        given = fixed[0] if fixed else given
    name = known[0] if len(known) == 1 else given or _new_name(words)
    kind = kinds[0] if len(kinds) == 1 else out[1] if head == "kind" and len(out) > 1 and out[1] in KINDS else None
    if head in ("nobody", "unknown", "other") and not (len(known) == 1 or len(kinds) == 1):
        return Reply(head, source="llm")
    if head in ("nobody", "unknown", "other"):
        # the sentence itself names what it is or who: that counts more than the model's guess
        return Reply("name", kind, known[0], "llm") if len(known) == 1 else Reply("kind", kind, name, "llm")
    if head == "name" and not name:
        said = _title(out[1:2])
        if said and _kind_of(normalize(said)):
            return Reply("kind", kind or _kind_of(normalize(said)), None, "llm")   # "name Gatto": a cat
        return Reply("other", source="llm")
    if kind and head != "name":
        return Reply("kind", kind, name, "llm")
    if name:
        return Reply("name", kind, name, "llm")
    return Reply(head if head in ("yes", "no") else "other", source="llm")


# ------------------------------------------------------------------ the dialogue
# what the house thinks a newcomer is, said so that it can be corrected, and how it asks the name
NEWCOMER = {
    "person": ("una persona nuova", "a new person"),
    "dog": ("un cane nuovo", "a new dog"),
    "cat": ("un gatto nuovo", "a new cat"),
    "animal": ("un animale nuovo", "a new animal"),
    "car": ("un'auto nuova", "a new car"),
    "object": ("un oggetto nuovo", "a new object"),
}
NOUN = {"person": ("una persona", "a person"), "dog": ("un cane", "a dog"), "cat": ("un gatto", "a cat"),
        "animal": ("un animale", "an animal"), "car": ("un'auto", "a car"), "object": ("un oggetto", "an object")}
ASK_NAME = {
    "person": ("Come si chiama?", "What's their name?"),
    "dog": ("Come si chiama?", "What's its name?"),
    "cat": ("Come si chiama?", "What's its name?"),
    "animal": ("Come si chiama?", "What's its name?"),
    "car": ("Come la chiamo?", "What shall I call it?"),
    "object": ("Come lo chiamo?", "What shall I call it?"),
}
WHAT_IS_IT = ("Ah, scusa! Allora cos'è: una persona, un animale, un'auto o un oggetto?",
              "Oh, sorry! So what is it: a person, an animal, a car or an object?")
NOTHING = ("Ah, allora ho visto male: scusate!", "Oh, I must have seen wrong: sorry!")
LATER = ("Va bene, nessun problema: se vuoi me lo dici dalla webapp.",
         "All right, no problem: you can tell me later in the web app.")
GIVE_UP = ("Va bene, lasciamo stare: me lo puoi dire dalla webapp.",
           "All right, let's leave it: you can tell me in the web app.")
WAITING = ("Certo, aspetto.", "Sure, I'll wait.")
THINKING = {"it": "Mmm...", "en": "Hmm..."}
MAX_TURNS = 7               # answers listened to, at most, before leaving it to the phones
LISTEN_S = 6.0
THINKING_S = 0.8            # the language model takes longer than this: a sound, so the visitor knows


class Dialogue:
    """Asking aloud who a newcomer is, until the house knows, the visitor gives up or a phone answers.

    The first question says what the house thinks it is ("vedo una persona nuova, giusto? Come si
    chiama?"); every answer is understood (rules, then the language model) and gets a reply: a name is
    checked together with what it is ("Una persona di nome Marco, giusto?"), a correction asks the name
    again, "there is nothing there" makes the vision forget it, a question or a command of the house is
    answered and the house asks again.
    """

    def __init__(self, voice: "Voice") -> None:
        self.voice = voice
        self.ctx = voice.ctx

    async def interpret(self, text: str) -> Reply:
        voice = self.voice
        names = voice._names()
        reply = by_rules(text, voice.lang, names)
        if reply is not None or voice.llm is None:
            return reply or Reply("other")
        task = asyncio.ensure_future(voice.llm.classify(text, names))
        done, _ = await asyncio.wait({task}, timeout=THINKING_S)
        if not done:
            await voice.say(THINKING[voice.lang])
        return await task or Reply("other")

    async def run(self, ev: dict, stop: asyncio.Event) -> None:
        voice, house = self.voice, self.ctx.house
        cid = ev.get("id")
        context = ev.get("context") or {}
        category = context.get("category") if context.get("category") in KINDS else "object"
        where_it = answers.room(self.ctx, context.get("room"), "it") if context.get("room") else "in casa"
        where_en = answers.room(self.ctx, context.get("room"), "en") if context.get("room") else "in the house"
        sure = False                    # the visitor said or confirmed what it is
        pending: str | None = None      # a new name waiting for a yes
        prompt: tuple[str, str] | None = None
        others = silences = 0
        for _ in range(MAX_TURNS):
            if prompt:
                await voice.reply(*prompt)
                prompt = None
            text, _, _, spoke = await voice.chatter._listen(None, stop=stop, max_s=LISTEN_S)
            if cid not in house.confirmations or spoke:
                return                  # answered on a phone, or someone pressed Talk
            r = await self.interpret(text)
            if cid not in house.confirmations:
                return
            ask_it, ask_en = ASK_NAME[category]
            if pending:
                if r.kind == "yes" or r.kind == "kind" and not r.name:
                    category = r.category or category
                    await self._new(cid, pending, category, context)
                    return
                if r.kind in ("no", "none_of"):
                    pending, prompt = None, ("Come si chiama, allora?", "What's the name, then?")
                    continue
                if r.kind == "silence" and silences == 0:
                    silences += 1
                    prompt = (f"Dimmi sì o no: si chiama {pending}?", f"Say yes or no: is the name {pending}?")
                    continue
                if not r.name:
                    pending = None
            if r.kind == "silence":
                silences += 1
                if silences > 1:
                    return              # nobody answers: the phones still can
                prompt = (ask_it, ask_en)
            elif r.kind == "wait":
                prompt = WAITING
            elif r.kind == "nobody":
                voice.narrator.hush(context.get("track"))
                if house.answer(cid, {"nothing": True}, by="voice"):
                    await voice.reply(*NOTHING)
                return
            elif r.kind == "unknown":
                await voice.reply(*LATER)
                return
            elif r.kind == "other":
                others += 1
                if r.intent is not None:
                    await voice.execute(r.intent)          # "che ore sono?": answered, then asked again
                if others >= 2:
                    await voice.reply(*GIVE_UP)
                    return
                prompt = (f"E il nuovo arrivato {where_it}: {ask_it[0].lower()}{ask_it[1:]}",
                          f"And the newcomer {where_en}: {ask_en[0].lower()}{ask_en[1:]}") if r.intent else \
                    (f"Scusa, mi serve il nome. {ask_it}", f"Sorry, I need the name. {ask_en}")
            elif r.kind == "yes":
                sure, prompt = True, (f"Bene! {ask_it}", f"Good! {ask_en}")
            elif r.kind == "no":
                sure, prompt = False, WHAT_IS_IT
            elif r.kind == "none_of":
                prompt = (f"Va bene. {ask_it}", f"All right. {ask_en}")
            elif r.kind in ("kind", "name"):
                if r.category in KINDS:
                    category, sure = r.category, True
                ask_it, ask_en = ASK_NAME[category]
                if not r.name:
                    noun = NOUN[category]
                    prompt = (f"Ah, {noun[0]}! {ask_it}", f"Oh, {noun[1]}! {ask_en}")
                    continue
                ident = self.ctx.identities.by_name(r.name)
                if ident is not None:
                    voice.narrator.hush(context.get("track"))
                    if house.answer(cid, ident.id, by="voice"):
                        await voice.reply(f"Ah, è {ident.name}! Grazie.", f"Oh, it's {ident.name}! Thanks.")
                    return
                pending = r.name
                if sure:
                    prompt = (f"Si chiama {pending}, giusto?", f"The name is {pending}, right?")
                else:
                    noun = NOUN[category]
                    prompt = (f"{noun[0][0].upper()}{noun[0][1:]} di nome {pending}, giusto?",
                              f"{noun[1][0].upper()}{noun[1][1:]} called {pending}, right?")
        await voice.reply(*GIVE_UP)

    async def _new(self, cid: str, name: str, category: str, context: dict) -> None:
        """Registered with what the house sees, its colours learned at once."""
        self.voice.narrator.hush(context.get("track"))
        if self.ctx.house.answer(cid, {"name": name, "category": category}, by="voice"):
            if category in ("car", "object"):
                await self.voice.reply(f"D'accordo: {name}!", f"All right: {name}!")
            else:
                await self.voice.reply(f"Piacere, {name}!", f"Nice to meet you, {name}!")
