# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Stories, memories and answers about the life of the house, generated from a local database.

data/stories.json holds pieces written by hand in Italian and English:
moments, activities for each room, events, reactions, relationships,
discoveries, endings, personalities (jobs, characters, passions, quirks),
details of the life of the house (bills, insurance, chores, shopping, cakes,
holidays) and the outlines of a few kinds of story. The house puts them
together at random, among the pieces that fit (procedural generation): a
few hundred pieces give millions of different stories, ready in a
millisecond on the UNO Q, and every sentence is correct because every piece
agrees with any name (in Italian no adjective or participle refers to a
character, in English no he or she).

- **Pieces that fit.** A discovery or an ending may be tied to the events it
  explains ("for"), the others share tags with the event; day and night,
  summer and winter never meet in the same story; a room is not heard "from
  the garage" by someone who is in the garage; dogs bark and cats hiss.
- **Personalities.** The first time a character is needed it gets a job, a
  character, a passion and a quirk from the database, different from those
  of the others; they stay the same until the house restarts. What somebody
  told the house about a character (its facts: web app, "ricorda che Marco
  fa il medico", the answers to the questions of chatty mode) comes first: a
  fact that is a job takes the place of the job, the others are used in the
  stories written in their language (an answer in both: facts.py).
- **Always a new story.** For each character (or room) the house remembers
  the outlines and pieces already used and picks others until it has used
  them all.
- **The life of the house.** "Luca ha pagato le bollette?", "quando scade
  l'assicurazione dell'auto?", "ti ricordi la festa di compleanno di Giulia
  del 1998?": the first answer is made up from the database and kept, so the
  same question gets the same answer, also in the other language and after
  the answer a visitor gave to a question of chatty mode, until the restart.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from ..layout import DATA_DIR
from ..model import ANIMALS, CATEGORY_NAMES, PERSON
from . import answers, facts
from . import variants as V
from .intents import find_names, find_room, normalize

if TYPE_CHECKING:
    from .manager import Voice

log = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "stories.json"
FALLBACK_NAMES = ("Nina", "Otto", "Lea", "Teo")      # when the house has no characters yet
CONFLICTS = (("day", "night"), ("summer", "winter"))
STORY_ROOMS = ("kitchen", "living", "bedroom", "bathroom", "garage", "garden")
PARTY_ROOMS = ("kitchen", "living", "garden")
MONTHS = {"it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
                 "ottobre", "novembre", "dicembre"],
          "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December"]}
WHEN = {"it": ["lunedì", "ieri mattina", "la settimana scorsa", "tre giorni fa", "ieri sera", "stamattina presto"],
        "en": ["on Monday", "yesterday morning", "last week", "three days ago", "last night", "early this morning"]}
GENERIC_JOB_USE = {"it": "diede una mano a tutti", "en": "gave everyone a hand"}
# every sentence is read by the voice of its own language (a fact typed in the other one, a name...)
LANG_WORDS = {
    "it": {"il", "lo", "la", "gli", "le", "un", "una", "che", "di", "del", "della", "e", "è", "non", "per", "con",
           "sono", "era", "erano", "mentre", "poi", "anche", "nella", "nel", "alla", "al", "quando", "perché",
           "tutti", "suo", "sua", "loro", "ma", "si", "da", "ha", "aveva", "casa"},
    # not "a" and "in": Italian words too ("cominciò a cadere", "in cucina")
    "en": {"the", "an", "and", "is", "was", "were", "of", "to", "on", "with", "he", "she", "they",
           "it", "his", "her", "their", "but", "when", "then", "there", "that", "this", "had", "has", "house"},
}
# the words that tell the language of a short fact ("ama il jazz", "loves jazz")
FACT_WORDS = {
    "it": LANG_WORDS["it"] | {"ama", "adora", "odia", "fa", "lavora", "gioca", "suona", "vive", "abita", "paura",
                              "sempre", "mai", "tifa", "colleziona", "insegna", "va", "sa", "legge", "mangia"},
    "en": LANG_WORDS["en"] | {"loves", "likes", "hates", "works", "plays", "lives", "afraid", "always", "never",
                              "supports", "collects", "teaches", "goes", "can", "reads", "eats", "does"},
}
JOB_VERB = re.compile(r"^(lavora|insegna|works|teaches)\b|\bdi (mestiere|professione)\b|\b(by trade|for a living)\b", re.I)
JOB_NOUN = re.compile(r"^(fa (il|la|lo|l'|l’)|è (un|una|un'|un’)|is an?)\s*(\w+ )?(\w+)", re.I)
JOB_ENDING = re.compile(r"(ista|iere|iera|tore|trice|(?<!am)ico|(?<!am)ica|aio|aia|ante|ente|essa|ologo|ologa|iatra|"
                        r"er|or|ist|ian|ant|ent|ef|ot|se)$|^(avvocat|architett|ingegner|commess|impiegat|operai|"
                        r"poliziott|ballerin|segretari|casaling|cuoc|sart|maestr|pilot|chef|clown|vet|cook)", re.I)
# the life of the house: what a free question is about
TOPICS = [
    ("party", r"\bfest[ae]\b|\bpart(y|ies)\b"),
    ("birthday", r"\bcompleann\w*|\bbirthdays?\b"),
    ("insurance", r"\bassicuraz\w*|\binsurance\b"),
    ("bill", r"\bbollett\w*|\bbills?\b|\bpagat\w*|\bpaid\b|\bpay\b"),
    ("shopping", r"\bspesa\b|\bshopping\b|\bgroceries\b"),
    ("pet", r"\bda mangiare\b|\bcroccantini\b|\bpappa\b|\bfed\b|\bfeed\b|\bpet food\b"),
    ("chore", r"\bspazzatura\b|\bimmondizia\b|\brifiuti\b|\bpiatti\b|\bbucato\b|\baspirapolvere\b|\bannaff\w*|"
              r"\brubbish\b|\btrash\b|\bbins?\b|\bdishes\b|\blaundry\b|\bwashing\b|\bhoover\w*|\bvacuum\w*|\bplants\b"),
    ("car", r"\btagliando\b|\bbenzina\b|\bgomme\b|\bpetrol\b|\btyres?\b|\btires?\b|\bservice\b"),
    ("holiday", r"\bvacanz\w*|\bferie\b|\bholidays?\b|\bvacation\b"),
]
BILLS = {"electricity": r"\bluce\b|\belectric\w*", "gas": r"\bgas\b", "water": r"\bacqua\b|\bwater\b",
         "internet": r"\binternet\b|\bwi ?fi\b"}
INSURANCES = {"house": r"\bcasa\b|\bhome\b|\bhouse\b", "car": r"\bauto\b|\bmacchina\b|\bcar\b"}
CHORES = {"rubbish": r"spazzatura|immondizia|rifiuti|rubbish|trash|\bbins?\b", "dishes": r"piatti|dishes",
          "laundry": r"bucato|laundry|washing", "hoover": r"aspirapolvere|hoover|vacuum", "plants": r"annaff|plants"}
FESTIVITIES = {"natale": ("di Natale", "Christmas"), "christmas": ("di Natale", "Christmas"),
               "capodanno": ("di Capodanno", "New Year's"), "halloween": ("di Halloween", "Halloween"),
               "carnevale": ("di Carnevale", "Carnival"), "carnival": ("di Carnevale", "Carnival")}
NOT_NAMES = {"compleanno", "birthday", "casa", "house", "the", "a", "my", "your", "our", "fine", "anno", "year",
             "quartiere", "street", "del", "della", "dei", "in", "of", "last", "that", "this", "quella", "quel"}


def sentence_lang(sentence: str, default: str) -> str:
    words = re.findall(r"[a-zàèéìòù']+", sentence.lower())
    score = {lang: sum(1 for w in words if w in vocab) for lang, vocab in LANG_WORDS.items()}
    other = "en" if default == "it" else "it"
    return other if score[other] >= score[default] + 2 else default


def fact_lang(fact: str) -> str | None:
    """The language of a short fact about a character, or None when it cannot be told."""
    said = facts.line_lang(fact)          # an answer to a question of the house: its template knows
    if said:
        return said
    words = re.findall(r"[a-zàèéìòù']+", fact.lower())
    it, en = (sum(1 for w in words if w in FACT_WORDS[lang]) for lang in ("it", "en"))
    return "it" if it > en else "en" if en > it else None


# a fact typed as a sentence of its own ("Il suo colore preferito è il rosso", "Her best friend is Viola"): it does
# not follow the name, it is said as it is
SENTENCE = re.compile(r"^(il suo|la sua|i suoi|le sue|suo|sua|suoi|sue|his|her|their|its)\b", re.I)


def as_clause(fact: str, name: str = "") -> str:
    """A fact that can follow the name: "a doctor" becomes "is a doctor", "un medico" "è un medico"; the name or a
    pronoun at its start goes ("Lei ama il jazz", "Marco ama il jazz" after "Marco")."""
    fact = fact.strip().rstrip(".")
    if name and fact.lower().startswith(name.lower() + " "):
        fact = fact[len(name):].strip()
    fact = re.sub(r"^(lui|lei|egli|ella|he|she)\s+", "", fact, flags=re.I)
    if SENTENCE.match(fact):
        return fact
    if re.match(r"(a|an|the)\s", fact, re.I):
        return "is " + fact
    if re.match(r"(un|una|il|la|lo)\s|un'|l'", fact, re.I):
        return "è " + fact
    return fact


def split_facts(lines: list[str], name: str) -> tuple[list[str], list[str]]:
    """The facts that follow the name ("ama il jazz"), and those that are sentences of their own ("Il suo colore
    preferito è il rosso"), each ready to be said."""
    clauses, sentences = [], []
    for f in lines:
        c = as_clause(f, name)
        if SENTENCE.match(c):
            sentences.append(c[:1].lower() + c[1:])
        else:
            clauses.append(c)
    return clauses, sentences


# words with the ending of a job that are not one ("fa il tifo per la Juve", "è un amante della musica",
# "is a heavy sleeper")
NOT_JOB = {"per", "for", "of", "di", "del", "della", "dei", "delle", "da", "con", "with", "amante", "appassionato",
           "appassionata", "tifoso", "tifosa", "fan", "lover", "vegetarian", "vegan", "vegetariano", "vegetariana",
           "sleeper", "riser", "eater", "drinker", "dreamer", "walker", "talker", "reader"}


def is_job(fact: str) -> bool:
    fact = as_clause(fact)
    if JOB_VERB.search(fact):
        return True
    m = JOB_NOUN.match(fact)
    return bool(m) and any(JOB_ENDING.search(w.strip()) for w in m.group(4, 5)
                           if w and w.strip().lower() not in NOT_JOB)


def _verb_first(fact: str, lang: str) -> bool:
    """The fact reads well after "Marco, che" / "Marco, who"."""
    word = fact.split()[0].lower() if fact.split() else ""
    if lang == "it":
        return word in {"è", "ha", "sa", "fa", "va", "sta", "non", "si", "ci", "ne"} or word.endswith(("a", "e", "è", "i"))
    return word in {"can", "never", "always", "often", "loves", "is", "has"} or word.endswith("s")


def _cap(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text[:1].upper() + text[1:] if text else text


def _about_sentence(name: str, sentence: str, lang: str, how: str) -> str:
    """A fact typed as a whole sentence ("il suo piatto preferito è la carbonara"), said as it is, in its language:
    `how` "told" (what somebody told the house) or "know" (what the house knows)."""
    if lang == "it":
        return f"Di {name} {'mi hai detto' if how == 'told' else 'so'} che {sentence}."
    return f"About {name}, {'you told me' if how == 'told' else 'I know'} that {sentence}."


def _key(piece: dict[str, Any]) -> str:
    return piece.get("id") or piece["it"]


def _clash(tags: Iterable[str], context: Iterable[str]) -> bool:
    tags, context = set(tags), set(context)
    return any((a in tags and b in context) or (b in tags and a in context) for a, b in CONFLICTS)


def date_text(lang: str, day: int, month: int) -> str:
    if lang == "it":
        article = "l'" if day in (8, 11) else "il "
        return f"{article}{'primo' if day == 1 else day} {MONTHS['it'][month]}"
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{MONTHS['en'][month]} {day}{suffix}"


def life_topic(question: str) -> str | None:
    """What a free question about the life of the house is about (TOPICS), or None."""
    t = normalize(question)
    return next((name for name, pattern in TOPICS if re.search(pattern, t)), None)


def load_db(path: Path = DB_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Guest:
    """A character made up by the house when it has none registered yet (or a name it does not know)."""

    category = PERSON
    alias_en = None

    def __init__(self, name: str) -> None:
        self.name = name
        self.id = f"guest:{name.lower()}"
        self.facts: list[str] = []


class StoryTeller:
    def __init__(self, voice: "Voice", db: dict[str, Any] | None = None, rng: random.Random | None = None) -> None:
        self.voice = voice
        self.ctx = voice.ctx
        self.db = db or load_db()
        self.rng = rng or random.Random()
        self.ok = True
        self.task: asyncio.Task | None = None       # a story being spoken (Talk stops it)
        self.reset()

    def reset(self) -> None:
        """Back to the personalities given in the web app or by voice (what a restart does)."""
        self.personas: dict[str, dict[str, Any]] = {}       # identity -> {"trait", "passion", "quirk", "job"}
        self.used: dict[str, set[str]] = {}                  # character, room or house -> pieces already used
        self.life: dict[tuple, Any] = {}                     # what the house made up about its life
        self._pending_reply: dict[str, dict[str, Any]] = {}

    @property
    def lang(self) -> str:
        return self.voice.lang

    @property
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    async def check(self) -> bool:
        return self.ok

    async def preempt(self) -> None:
        """Talk wants the house: the story stops."""
        task = self.task
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        await asyncio.wait({task}, timeout=2.0)

    # ================================================================ choosing pieces
    def _choose(self, pool: list[dict[str, Any]], used: set[str] | None = None, *, event: str | None = None,
                tags: Iterable[str] = (), context: Iterable[str] = (), who: Any = None, generic: float = 0.3,
                loose: bool = True) -> dict[str, Any]:
        """A piece of the pool that fits: tied to the event, or sharing a tag, and now and then a generic one;
        never clashing with the moment, never for another kind of animal; one not used yet if there is one."""
        tags = set(tags)
        ok = [p for p in pool if not _clash(p.get("tags", ()), context)
              and (who is None or "only" not in p or who.category in p["only"])]
        specific = [p for p in ok if event and event in p.get("for", ())]
        tagged = [p for p in ok if loose and not p.get("for") and set(p.get("tags", ())) & tags]
        plain = [p for p in ok if not p.get("for") and not p.get("tags")]
        candidates = specific + tagged
        if not candidates or self.rng.random() < generic:
            candidates += plain
        candidates = candidates or ok or pool
        fresh = [p for p in candidates if used is None or _key(p) not in used] or candidates
        item = self.rng.choice(fresh)
        if used is not None:
            used.add(_key(item))
        return item

    # ================================================================ characters
    def persona(self, ident) -> dict[str, Any]:
        """The personality of a character from the database, different from the others', kept until the restart."""
        p = self.personas.get(ident.id)
        if p is not None:
            return p
        pet = ident.category in ANIMALS
        pools = self.db["animals"] if pet else self.db["people"]
        slots = [("trait", "traits"), ("passion", "passions"), ("quirk", "quirks")] + ([] if pet else [("job", "jobs")])
        p = {}
        for slot, pool in slots:
            taken = {other[slot]["id"] for other in self.personas.values() if slot in other}
            items = [x for x in pools[pool] if "only" not in x or ident.category in x["only"]]
            p[slot] = self.rng.choice([x for x in items if x["id"] not in taken] or items)
        self.personas[ident.id] = p
        log.info("personality of %s: %s", ident.name, {k: v["id"] for k, v in p.items()})
        return p

    def job(self, ident, lang: str) -> dict[str, Any] | None:
        """The job of a character in a language: the one somebody gave first, else the one from the database."""
        if ident.category != PERSON:
            return None
        fact = next((as_clause(f) for f in ident.facts if is_job(f)), None)
        preset = self.persona(ident)["job"]
        if fact is None:
            return {"text": preset[lang], "use": preset["use"][lang], "tags": preset.get("tags", [])}
        known = next((j for j in self.db["people"]["jobs"] if re.search(j["match"], fact, re.I)), None)
        said_in = fact_lang(fact)
        if known:
            return {"text": fact if said_in == lang else known[lang], "use": known["use"][lang],
                    "tags": known.get("tags", [])}
        if said_in == lang:
            return {"text": fact, "use": GENERIC_JOB_USE[lang], "tags": []}
        return None                 # a job the house can only say in the other language

    def facts_in(self, ident, lang: str) -> list[str]:
        """The facts of a character, not the job, written in this language and fit to follow its name."""
        out = []
        for f in getattr(ident, "facts", ()):
            f = as_clause(facts.translated(f, lang) or f)       # an answer reads in both languages
            if not is_job(f) and fact_lang(f) == lang and _verb_first(f, lang):
                out.append(f)
        return out

    def _name(self, ident, lang: str, first: bool) -> str:
        if first and ident.category in ("dog", "cat"):
            noun = CATEGORY_NAMES[ident.category][lang]
            return f"il {noun} {ident.name}" if lang == "it" else f"{ident.name} the {noun}"
        return ident.name

    def _present(self) -> list[Any]:
        ids = self.ctx.identities
        out = []
        for t in self.ctx.house.tracks.values():
            ident = ids.get(t.identity) if t.identity else None
            if ident and ident not in out and ident.category in (PERSON,) + ANIMALS \
                    and t.room not in ("outside", None) and not t.carried:
                out.append(ident)
        return out

    def _room_of(self, ident) -> str | None:
        for t in self.ctx.house.tracks.values():
            if t.identity == ident.id and t.room in self.db["activities"]:
                return t.room
        return None

    def _characters(self) -> list[Any]:
        return [i for i in self.ctx.identities.all() if i.category in (PERSON,) + ANIMALS]

    def _others(self, cast: list[Any], person: bool = False) -> list[Any]:
        """Characters for a story besides the cast: first those in the house, then the others, then made-up ones."""
        present = [i for i in self._present() if i not in cast]
        rest = [i for i in self._characters() if i not in cast and i not in present]
        self.rng.shuffle(present)
        self.rng.shuffle(rest)
        taken = {c.name for c in cast}
        out = present + rest + [Guest(n) for n in FALLBACK_NAMES if n not in taken]
        return [i for i in out if not person or i.category == PERSON]

    # ================================================================ stories
    def _plot_fits(self, plot: dict[str, Any], cast: list[Any], lang: str) -> bool:
        if len(cast) < plot["cast"]:
            return False
        if "job" in plot.get("needs", ()) and self.job(cast[0], lang) is None:
            return False
        if "party" in plot.get("tags", ()) and cast[1].category != PERSON:
            return False             # a pet does not blow up balloons
        return True

    def _cast_for(self, plot: dict[str, Any], named: list[Any]) -> list[Any]:
        """Who was asked for, then others to share the story with (a person prepares a party)."""
        party = "party" in plot.get("tags", ())
        cast = list(named[:plot["cast"]])
        if party and len(cast) == 2 and cast[1].category != PERSON:
            cast.reverse()
        while len(cast) < plot["cast"]:
            cast.append(self._others(cast, person=party and len(cast) == 1)[0])
        return cast

    def compose(self, names: list[str] | None = None, room: str | None = None, party: bool = False,
                lang: str | None = None) -> tuple[list[str], list[Any]]:
        """A new story: its sentences and its cast."""
        lang = lang or self.lang
        ids = self.ctx.identities
        named: list[Any] = []
        for n in names or []:
            ident = ids.by_name(n)
            if ident and ident.category in (PERSON,) + ANIMALS and ident not in named:
                named.append(ident)
        named = named[:2]
        subject = named[0].id if named else (f"room:{room}" if room else "house")
        used = self.used.setdefault(subject, set())
        plots = self.db["plots"]
        if party:
            pool = [p for p in plots if "party" in p.get("tags", ())]
        else:
            pool = [p for p in plots if "party" not in p.get("tags", ()) and (len(named) < 2 or p["cast"] == 2)]
            if room and "plot:room" not in used:
                pool = [p for p in pool if p["id"] == "room"] or pool
        order = pool[:]
        self.rng.shuffle(order)
        order.sort(key=lambda p: f"plot:{p['id']}" in used)       # the outlines not told yet first
        for plot in order:
            cast = self._cast_for(plot, named)
            if self._plot_fits(plot, cast, lang):
                break
        else:
            plot = next(p for p in plots if p["id"] == "alone")
            cast = self._cast_for(plot, named)
        used.add(f"plot:{plot['id']}")
        slots = self._slots(plot, cast, room, lang, used)
        sentences = []
        for template in plot[lang]:
            text = template
            for _ in range(3):            # a piece may hold placeholders itself ({a} in a relationship)
                text = re.sub(r"\{([A-Za-z_.]+)\}", lambda m: slots.get(m.group(1), m.group(0)), text)
            if lang == "it":
                text = re.sub(r"(?<= )a (?=[aà])", "ad ", text)          # "ad annaffiare"
            sentences.append(_cap(text))
        log.info("story %s about %s", plot["id"], [c.name for c in cast])
        return sentences, cast

    def _slots(self, plot: dict[str, Any], cast: list[Any], room: str | None, lang: str,
               used: set[str]) -> dict[str, str]:
        db = self.db
        a = cast[0]
        b = cast[1] if len(cast) > 1 else None
        pet_a = a.category in ANIMALS
        if room not in db["activities"]:
            room = self.rng.choice(PARTY_ROOMS) if "party" in plot.get("tags", ()) else \
                (self._room_of(a) or self.rng.choice(STORY_ROOMS))
        moment = self._choose(db["moments"], used, generic=1)
        events = [e for e in db["events"] if not _clash(e.get("tags", ()), moment.get("tags", ()))
                  and room not in e.get("not_in", ()) and e["id"] not in moment.get("not", ())]
        event = self._choose(events, used, generic=1)
        tags = set(event.get("tags", ()))
        context = tags | set(moment.get("tags", ())) | set(plot.get("tags", ()))
        acts = (db["animal_activities"] if pet_a else db["activities"]).get(room) or db["activities"][room]
        pets = pet_a or (b is not None and b.category in ANIMALS)
        slots = {
            "moment": moment[lang], "room_in": answers.room(self.ctx, room, lang),
            "activity": self._choose(acts, used, generic=1)[lang], "event": event[lang],
            "reaction": self._choose(db["animal_reactions"] if pet_a else db["reactions"], used, event=event["id"],
                                     tags=tags, who=a)[lang],
            "help": self._choose(db["helps"], used, event=event["id"], tags=tags)[lang],
            "discovery": self._choose(db["discoveries"], used, event=event["id"], loose=False, generic=0.15)[lang],
            "ending": self._choose(db["endings"], used, event=event["id"], tags=context,
                                   context=moment.get("tags", ()), generic=0.35)[lang],
            "party_prep": self._choose(db["party_preps"], used, generic=1)[lang],
            "relation": self._choose([r for r in db["relations"] if r.get("pet") or not pets], used, generic=1)[lang],
        }
        for who, ident in (("a", a), ("b", b)):
            if ident is None:
                continue
            p = self.persona(ident)
            slots[who.upper()] = self._name(ident, lang, True)
            slots[who] = ident.name
            facts = self.facts_in(ident, lang)
            slots[f"{who}.trait"] = self.rng.choice(facts) if facts and self.rng.random() < 0.4 else p["trait"][lang]
            slots[f"{who}.passion"] = p["passion"][lang]
            slots[f"{who}.passion_use"] = p["passion"]["use"][lang]
            slots[f"{who}.quirk"] = p["quirk"][lang]
            job = self.job(ident, lang)
            if job:
                slots[f"{who}.job"] = job["text"]
                slots[f"{who}.job_use"] = job["use"]
        return slots

    async def tell(self, names: list[str] | None = None, room: str | None = None, party: bool = False) -> bool:
        """Tell a new story (it is ready at once)."""
        self.task = asyncio.current_task()
        sentences, cast = self.compose(names, room, party)
        said = await self._speak(sentences, self._light_rooms)
        if said:
            self.ctx.store.add_event("story", {"cast": [c.name for c in cast], "room": room, "sentences": len(said)})
        await self.ctx.actions.lights_auto("all")
        return bool(said)

    # ================================================================ speaking
    async def _speak(self, sentences: list[str | tuple[str, str]],
                     on_sentence: Callable[[str], None] | None = None) -> list[str]:
        """Speak the sentences in order, synthesizing the next one while one plays. They are in the language
        of the house, unless one comes with its own (a fact written in the other language)."""
        lang = self.lang
        spoken = self.ctx.actions.speaks("normal")
        voice = self.voice
        ready: asyncio.Queue[tuple[str, str, Any] | None] = asyncio.Queue(maxsize=1)

        async def prepare() -> None:
            for item in sentences:
                sentence, said_lang = item if isinstance(item, tuple) else (item, lang)
                samples = await voice.speaker.synth(sentence, said_lang) if spoken else None
                await ready.put((sentence, said_lang, samples))
            await ready.put(None)

        preparer = asyncio.ensure_future(prepare())
        said: list[str] = []
        try:
            while True:
                item = await ready.get()
                if item is None:
                    break
                sentence, said_lang, samples = item
                if on_sentence:
                    on_sentence(sentence)
                said.append(sentence)
                self.ctx.bus.publish("say", text=sentence, lang=said_lang, spoken=spoken)
                if samples is not None:
                    await voice.play(samples)
        finally:
            preparer.cancel()
        return said

    def _light_rooms(self, sentence: str) -> None:
        room = find_room(normalize(sentence))
        if room and self.ctx.layout.light_of_room(room) is not None:
            asyncio.ensure_future(self.ctx.actions.light(room, "warm", "breathe", 70, 12))

    # ================================================================ what the house knows of a character
    def about(self, name: str, lang: str | None = None) -> list[tuple[str, str]]:
        """What the house knows about a character, as (sentence, language): what it was told, then its personality."""
        lang = lang or self.lang
        ident = self.ctx.identities.by_name(name)
        if not ident or ident.category not in (PERSON,) + ANIMALS:
            return [(f"Non conosco nessun personaggio che si chiama {name}." if lang == "it"
                     else f"I don't know any character called {name}.", lang)]
        p = self.persona(ident)
        out: list[tuple[str, str]] = []
        here = self.ctx.house.where_is(ident.id)
        if here is not None and here.room:
            where = answers.room(self.ctx, here.room, lang)
            out.append((_cap(f"{ident.name} è {where}.") if lang == "it" else _cap(f"{ident.name} is {where}."), lang))
        told, sentences = split_facts([facts.translated(f, lang) or f for f in ident.facts], ident.name)
        mine = [f for f in told if fact_lang(f) in (lang, None)]
        other = [f for f in told if f not in mine]
        said_mine = [s for s in sentences if fact_lang(s) in (lang, None)]
        said_other = [s for s in sentences if s not in said_mine]
        if mine:
            out.append((f"Mi hai detto che {ident.name} {answers.join(mine, lang)}." if lang == "it"
                        else f"You told me that {ident.name} {answers.join(mine, lang)}.", lang))
        for s in said_mine:
            out.append((_about_sentence(ident.name, s, lang, "told"), lang))
        if other or said_other:
            other_lang = "en" if lang == "it" else "it"
            also = {"it": " anche", "en": " also"}[lang] if mine or said_mine else ""
            out.append((f"Me l'hai detto{also} in inglese:" if lang == "it" else f"You{also} told me in Italian:", lang))
            if other:
                out.append((_cap(f"{ident.name} {answers.join(other, other_lang)}."), other_lang))
            for s in said_other:
                out.append((_about_sentence(ident.name, s, other_lang, "told"), other_lang))
        items = []
        if ident.category == PERSON and not any(is_job(f) for f in ident.facts):
            items.append(p["job"][lang])
        items += [p["trait"][lang], p["passion"][lang], p["quirk"][lang]]
        lead = ("E poi so che " if lang == "it" else "And I also know that ") if ident.facts else ""
        out.append((_cap(f"{lead}{ident.name} {answers.join(items, lang)}."), lang))
        return out

    async def tell_about(self, name: str) -> None:
        await self._speak(self.about(name))

    def told(self, ident, indices: list[int], lang: str | None = None) -> list[tuple[str, str]]:
        """The facts of a character that answer a question, as (sentence, language): the fact itself after the
        name, in the language of the house when it can be said in it, otherwise in its own."""
        lang = lang or self.lang
        other_lang = "en" if lang == "it" else "it"
        mine, other = [], []
        clauses, sentences = split_facts([facts.translated(ident.facts[i], lang) or ident.facts[i] for i in indices],
                                         ident.name)
        for line in clauses:
            (mine if fact_lang(line) in (lang, None) else other).append(line)
        said_mine = [s for s in sentences if fact_lang(s) in (lang, None)]
        said_other = [s for s in sentences if s not in said_mine]
        out: list[tuple[str, str]] = []
        if mine:
            pair = V.said("facts-known", facts.KNOWN, name=ident.name, fact=answers.join(mine, lang))
            out.append((pair[0] if lang == "it" else pair[1], lang))
        for s in said_mine:
            out.append((_about_sentence(ident.name, s, lang, "know"), lang))
        if other or said_other:
            also = {"it": " anche", "en": " also"}[lang] if mine or said_mine else ""
            out.append((f"Me l'hai detto{also} in inglese:" if lang == "it" else f"You{also} told me in Italian:", lang))
            if other:
                out.append((_cap(f"{ident.name} {answers.join(other, other_lang)}."), other_lang))
            for s in said_other:
                out.append((_about_sentence(ident.name, s, other_lang, "know"), other_lang))
        return out

    async def tell_facts(self, ident, indices: list[int]) -> None:
        await self._speak(self.told(ident, indices))

    # ================================================================ the life of the house
    def _keep(self, key: tuple, make: Callable[[], Any]) -> Any:
        if key not in self.life:
            self.life[key] = make()
        return self.life[key]

    def _soon(self, lo: int, hi: int) -> tuple[int, int]:
        """A day and month a few days or months from now (any date if the clock is not set)."""
        today = datetime.date.today()
        if today.year < 2025:
            return self.rng.randint(1, 28), self.rng.randrange(12)
        d = today + datetime.timedelta(days=self.rng.randint(lo, hi))
        return d.day, d.month - 1

    def _birthday(self) -> tuple[int, int]:
        return self._soon(5, 80)             # chatty mode says it is coming up soon

    def _any_date(self) -> tuple[int, int]:
        return self.rng.randint(1, 28), self.rng.randrange(12)

    def _people(self) -> list[Any]:
        return [i for i in self.ctx.identities.all() if i.category == PERSON]

    def _usual(self) -> Any:
        """The one who usually takes care of things, when the question names nobody."""
        people = self._people()
        if not people:
            return Guest(FALLBACK_NAMES[0])
        chosen = self._keep(("usual",), lambda: self.rng.choice(people).id)
        return self.ctx.identities.get(chosen) or people[0]

    def _who(self, ident_id: str) -> Any:
        return self.ctx.identities.get(ident_id) or (Guest(ident_id.split(":", 1)[1].title())
                                                     if ident_id.startswith("guest:") else self._usual())

    def _bill(self, kind: str, owner: Any) -> dict[str, Any]:
        return self._keep(("bill", kind), lambda: {
            "paid": self.rng.random() < 0.55, "owner": owner.id, "when": self.rng.randrange(len(WHEN["it"])),
            "due": self._soon(4, 40), "excuse": self.rng.randrange(len(self.db["life"]["excuses"]))})

    def _party_name(self, t: str) -> tuple[Any, tuple[str, str] | None]:
        """Whose party the question is about: a character, a festivity ("di Natale") or a name the house
        does not know ("la festa di Giulia")."""
        for word, label in FESTIVITIES.items():
            if re.search(rf"\b{word}\b", t):
                return None, label
        m = re.search(r"\b(?:festa|compleanno)(?: di compleanno)? (?:di|per) (\w+)", t) or \
            re.search(r"\b(\w+) s (?:birthday )?party\b", t) or re.search(r"\bparty for (\w+)", t)
        if m and m.group(1) not in NOT_NAMES and not m.group(1).isdigit():
            return Guest(m.group(1).title()), None
        return None, None

    def life_answer(self, question: str, names: list[str] | None = None, recall: bool = False,
                    lang: str | None = None) -> list[str]:
        """The answer to a free question about the life of the house (made up once, then kept)."""
        lang = lang or self.lang
        it = lang == "it"
        t = normalize(question)
        ids = self.ctx.identities
        found = names if names else find_names(t, ids.names())
        mentioned = [i for i in (ids.by_name(n) for n in found) if i]
        people = [i for i in mentioned if i.category == PERSON]
        topic = life_topic(t)
        life = self.db["life"]
        W = WHEN[lang]
        asked = people[0] if people else None

        if topic in ("party", "birthday") and (recall or re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", t)
                                               or re.search(r"\bricord|\bremember", t)):
            return self._party_memory(t, asked, lang)
        if topic in ("party", "birthday"):
            who = asked or self._party_name(t)[0]
            if who is None:
                return ["Il compleanno di chi? Dimmi il nome." if it else "Whose birthday? Tell me the name."]
            day, month = self._keep(("birthday", who.id), self._birthday)
            return [f"Il compleanno di {who.name} è {date_text(lang, day, month)}." if it
                    else f"{who.name}'s birthday is on {date_text(lang, day, month)}."]

        if topic == "bill":
            return self._bill_answer(t, asked, lang)

        if topic == "insurance":
            kind = next((k for k, p in INSURANCES.items() if re.search(p, t)), "car")
            label = next(i for i in life["insurances"] if i["id"] == kind)
            d = self._keep(("insurance", kind), lambda: {"due": self._soon(20, 330), "owner": (asked or self._usual()).id})
            when, owner = date_text(lang, *d["due"]), self._who(d["owner"]).name
            return [f"L'assicurazione {label['it']} scade {when}: se ne occupa {owner}." if it
                    else f"The {label['en']} insurance runs out on {when}: {owner} takes care of it."]

        if topic == "shopping":
            d = self._keep(("shopping",), lambda: {"who": (asked or self._usual()).id, "done": self.rng.random() < 0.6,
                                                   "when": self.rng.randrange(len(W)),
                                                   "items": self.rng.randrange(len(life["groceries"]))})
            who, items = self._who(d["who"]), life["groceries"][d["items"]][lang]
            if not d["done"]:
                return [f"Non ancora: sulla lista ci sono {items}." if it else f"Not yet: the list says {items}."]
            if asked and asked.id != who.id:
                return [f"No, la spesa l'ha fatta {who.name} {W[d['when']]}." if it
                        else f"No, {who.name} did the shopping {W[d['when']]}."]
            return [f"Sì, {who.name} ha fatto la spesa {W[d['when']]}: {items}." if it
                    else f"Yes, {who.name} did the shopping {W[d['when']]}: {items}."]

        if topic == "chore":
            chore = next((c for c in life["chores"] if re.search(CHORES[c["id"]], t)), life["chores"][0])
            d = self._keep(("chore", chore["id"]), lambda: {
                "who": (asked or self._usual()).id, "done": self.rng.random() < 0.5, "when": self.rng.randrange(len(W)),
                "excuse": self.rng.randrange(len(life["excuses"]))})
            who = self._who(d["who"])
            if d["done"]:
                if asked and asked.id != who.id:
                    return [f"No, stavolta ci ha pensato {who.name}, {W[d['when']]}." if it
                            else f"No, this time {who.name} did it, {W[d['when']]}."]
                return [f"{'Sì' if it else 'Yes'}, {who.name} {chore['done'][lang]} {W[d['when']]}."]
            excuse = life["excuses"][d["excuse"]][lang]
            return [f"Non ancora: tocca a {who.name}, che {excuse}." if it
                    else f"Not yet: it's {who.name}'s turn, and {who.name} {excuse}."]

        if topic == "pet":
            pets = [i for i in mentioned if i.category in ANIMALS] or \
                   [i for i in ids.all() if i.category in ANIMALS]
            if not pets:
                return ["In questa casa per ora non ci sono animali da sfamare." if it
                        else "There are no pets to feed in this house yet."]
            pet = pets[0]
            d = self._keep(("pet", pet.id), lambda: {"fed": self.rng.random() < 0.7, "who": (asked or self._usual()).id,
                                                     "when": self.rng.randrange(len(W))})
            who = self._who(d["who"])
            if d["fed"]:
                return [f"Sì, {who.name} ha dato la pappa a {pet.name} {W[d['when']]}." if it
                        else f"Yes, {who.name} fed {pet.name} {W[d['when']]}."]
            return [f"Non ancora, e {pet.name} aspetta davanti alla ciotola!" if it
                    else f"Not yet, and {pet.name} is waiting by the bowl!"]

        if topic == "car":
            d = self._keep(("car",), lambda: {"fact": self.rng.randrange(len(life["car_facts"])),
                                              "month": self.rng.randrange(12)})
            fact = life["car_facts"][d["fact"]][lang].replace("{month}", MONTHS[lang][d["month"]])
            return [f"L'auto {fact}." if it else f"The car {fact}."]

        if topic == "holiday":
            key = asked.id if asked else "house"
            place = life["holidays"][self._keep(("holiday", key), lambda: self.rng.randrange(len(life["holidays"])))][lang]
            if asked:
                return [f"{asked.name} vorrebbe andare {place}." if it else f"{asked.name} would like to go {place}."]
            return [f"Quest'anno in casa si parla di andare {place}." if it
                    else f"This year everyone in the house is talking about going {place}."]

        if recall:
            return self._memory(mentioned[0] if mentioned else self._usual(), lang)

        if mentioned:
            ident = mentioned[0]
            p = self.persona(ident)
            facts = self.facts_in(ident, lang)
            first = self.rng.choice(facts) if facts else p["trait"][lang]
            return [f"Posso dirti che {ident.name} {first} e {p['passion'][lang]}." if it
                    else f"I can tell you that {ident.name} {first} and {p['passion'][lang]}."]
        return [self.rng.choice(self.db["unknown"])[lang]]

    def _bill_answer(self, t: str, asked: Any, lang: str) -> list[str]:
        it = lang == "it"
        life = self.db["life"]
        W = WHEN[lang]
        owner = asked or self._usual()
        kind = next((k for k, p in BILLS.items() if re.search(p, t)), None)
        if kind:
            label = next(b for b in life["bills"] if b["id"] == kind)
            b = self._bill(kind, owner)
            who = self._who(b["owner"])
            what_it, what_en = f"la bolletta {label['it']}", f"the {label['en']} bill"
            if b["paid"]:
                if asked and asked.id != who.id:
                    return [f"No, {what_it} l'ha pagata {who.name}, {W[b['when']]}." if it
                            else f"No, {who.name} paid {what_en}, {W[b['when']]}."]
                return [f"Sì, {who.name} ha pagato {what_it} {W[b['when']]}." if it
                        else f"Yes, {who.name} paid {what_en} {W[b['when']]}."]
            excuse = life["excuses"][b["excuse"]][lang]
            due = date_text(lang, *b["due"])
            return [f"Non ancora: {what_it} scade {due}, e {who.name} {excuse}." if it
                    else f"Not yet: {what_en} is due on {due}, and {who.name} {excuse}."]
        bills = [(b, self._bill(b["id"], owner)) for b in life["bills"]]
        unpaid = [(b, s) for b, s in bills if not s["paid"]]
        if not unpaid:
            payers = {s["owner"] for _, s in bills}
            who = self._who(payers.pop()) if len(payers) == 1 else None
            last = W[bills[0][1]["when"]]
            if who and (not asked or asked.id == who.id):
                return [f"Sì, {who.name} ha pagato tutte le bollette, l'ultima {last}." if it
                        else f"Yes, {who.name} paid all the bills, the last one {last}."]
            return ["Sì, le bollette sono tutte pagate." if it else "Yes, all the bills are paid."]
        first = min(unpaid, key=lambda bs: (bs[1]["due"][1], bs[1]["due"][0]))
        due = date_text(lang, *first[1]["due"])
        if len(unpaid) == len(bills):
            who = self._who(first[1]["owner"])
            excuse = life["excuses"][first[1]["excuse"]][lang]
            return [f"Non ancora: la prima scade {due}, e {who.name} {excuse}." if it
                    else f"Not yet: the first one is due on {due}, and {who.name} {excuse}."]
        names_it = answers.join([f"quella {b['it']}" for b, _ in unpaid], "it")
        names_en = answers.join([b["en"] for b, _ in unpaid], "en")
        return [f"Non tutte: manca {names_it}, e la prima scade {due}." if it and len(unpaid) == 1 else
                f"Non tutte: mancano {names_it}, e la prima scade {due}." if it else
                f"Not all of them: the {names_en} {'bill is' if len(unpaid) == 1 else 'bills are'} still to be paid, "
                f"and the first is due on {due}."]

    def _party(self, key: str, year: str, guest_of: str | None) -> dict[str, Any]:
        life = self.db["life"]
        others = [i.id for i in self._people() if i.id != guest_of]
        return self._keep(("party", key, year), lambda: {
            "room": self.rng.choice(PARTY_ROOMS), "cake": self.rng.randrange(len(life["cakes"])),
            "fun": self.rng.randrange(len(life["party_fun"])),
            "guest": self.rng.choice(others) if others and self.rng.random() < 0.7 else None})

    def _party_memory(self, t: str, asked: Any, lang: str) -> list[str]:
        it = lang == "it"
        life = self.db["life"]
        found, festivity = (asked, None) if asked else self._party_name(t)
        key = found.id if found else (festivity[1] if festivity else "house")
        m = re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", t)
        year = m.group(1) if m else str(self._keep(("party_year", key), lambda: self.rng.randint(1990, 2022)))
        d = self._party(key, year, found.id if found else None)
        birthday = bool(re.search(r"compleann|birthday", t)) and found is not None
        if found:
            title_it = f"La festa {'di compleanno ' if birthday else ''}di {found.name} del {year}"
            title_en = f"{found.name}'s {'birthday ' if birthday else ''}party in {year}"
        elif festivity:
            title_it, title_en = f"La festa {festivity[0]} del {year}", f"The {festivity[1]} party in {year}"
        else:
            title_it, title_en = f"La festa del {year}", f"The party in {year}"
        where = answers.room(self.ctx, d["room"], lang)
        cake, fun = life["cakes"][d["cake"]][lang], life["party_fun"][d["fun"]][lang]
        out = [f"Certo che me la ricordo! {title_it} si fece {where}." if it
               else f"Of course I remember! {title_en} was {where}.",
               f"C'era {cake}, e {fun}." if it else f"There was {cake}, and {fun}."]
        guest = self.ctx.identities.get(d["guest"]) if d["guest"] else None
        if guest:
            use = self.persona(guest)["passion"]["use"][lang]
            out.append(f"C'era anche {guest.name}, che {use}." if it else f"{guest.name} was there too, and {use}.")
        return out

    def _memory(self, ident: Any, lang: str) -> list[str]:
        """A memory of a character, with its date (always the same for the same memory)."""
        it = lang == "it"
        if ident.category in ANIMALS:
            line = self._choose(self.db["animal_anecdotes"], self.used.setdefault(f"anecdote:{ident.id}", set()),
                                who=ident)[lang].replace("{a}", ident.name)
            return ["Come dimenticarlo!" if it else "How could I forget!", line]
        used = self.used.setdefault(f"memory:{ident.id}", set())
        item = self._choose(self.db["memories"], used, generic=1)
        day, month, year = self._keep(("memory", ident.id, _key(item)),
                                      lambda: (*self._any_date(), self.rng.randint(1995, 2023)))
        when = date_text(lang, day, month)
        return [f"Come dimenticarlo! E io mi ricordo anche di quando {ident.name} {item['it']}, {when} del {year}."
                if it else
                f"How could I forget! And I also remember when {ident.name} {item['en']}, on {when}, {year}."]

    def knows(self, question: str) -> bool:
        """The question is about the life of the house: the database answers it, not the model of the commands
        (which took "Luca ha pagato le bollette?" for "where is Luca")."""
        return life_topic(question) is not None

    async def answer(self, question: str, names: list[str] | None = None, memory: bool = False) -> bool:
        """Answer a free question about the life of the house."""
        self.task = asyncio.current_task()
        return bool(await self._speak(self.life_answer(question, names, memory)))

    # ================================================================ chatty mode
    def chat_ready(self, identity: str) -> list[str]:
        return ["anecdote", "memory", "question"]

    def chat_lines(self, ident: Any, kind: str, lang: str | None = None) -> tuple[list[str], dict[str, Any] | None]:
        """A chatty line about a character; for a question also what to say after a yes and after a no."""
        lang = lang or self.lang
        it = lang == "it"
        db = self.db
        name = ident.name
        pet = ident.category in ANIMALS
        if kind == "question" and pet:
            kind = "anecdote"
        if kind == "memory" and pet:
            return self._memory(ident, lang)[1:], None
        if kind == "anecdote":
            if self.rng.random() < 0.3:          # the quirk of its personality, the same every time
                quirk = self.persona(ident)["quirk"][lang]
                return [f"Lo sapevate che {name} {quirk}? Io me ne accorgo sempre!" if it
                        else f"Did you know that {name} {quirk}? I always notice!"], None
            pool = db["animal_anecdotes"] if pet else db["anecdotes"]
            line = self._choose(pool, self.used.setdefault(f"anecdote:{ident.id}", set()), who=ident)
            return [line[lang].replace("{a}", name)], None
        if kind == "memory":
            if self.rng.random() < 0.5:          # a party of the past, the same one a visitor can ask about
                year = str(self._keep(("party_year", ident.id), lambda: self.rng.randint(1990, 2022)))
                d = self._party(ident.id, year, ident.id)
                life = db["life"]
                where = answers.room(self.ctx, d["room"], lang)
                cake, fun = life["cakes"][d["cake"]][lang], life["party_fun"][d["fun"]][lang]
                return ([f"Vi ricordate la festa di {name} del {year}?", f"Si fece {where}, con {cake}, e {fun}!"] if it
                        else [f"Do you remember {name}'s party in {year}?", f"It was {where}, with {cake}, and {fun}!"]), None
            item = self._choose(db["memories"], self.used.setdefault(f"memory:{ident.id}", set()), generic=1)
            day, month, year = self._keep(("memory", ident.id, _key(item)),
                                          lambda: (*self._any_date(), self.rng.randint(1995, 2023)))
            when = date_text(lang, day, month)
            return ([f"Vi ricordate quando {name} {item['it']}?", f"Era {when} del {year}!"] if it
                    else [f"Do you remember when {name} {item['en']}?", f"It was {when}, {year}!"]), None
        # a question about the life of the house, with the reply to a yes and to a no
        life = db["life"]
        q = self._choose(db["chat_questions"], self.used.setdefault(f"question:{ident.id}", set()), generic=1)
        slots: dict[str, str] = {"a": name}
        state: tuple | None = None
        topic = q["topic"]
        if topic == "bill":
            bill = self.rng.choice(life["bills"])
            slots["kind"] = bill[lang]
            slots["due"] = date_text(lang, *self._bill(bill["id"], ident)["due"])
            state = ("bill", bill["id"])
        elif topic == "insurance":
            ins = self.rng.choice(life["insurances"])
            slots["kind"] = ins[lang]
            d = self._keep(("insurance", ins["id"]), lambda: {"due": self._soon(20, 330), "owner": ident.id})
            slots["due"] = date_text(lang, *d["due"])
        elif topic == "shopping":
            d = self._keep(("shopping",), lambda: {"who": ident.id, "done": False, "when": 0,
                                                   "items": self.rng.randrange(len(life["groceries"]))})
            slots["items"] = life["groceries"][d["items"]][lang]
            state = ("shopping",)
        elif topic == "chore":
            chore = self.rng.choice(life["chores"])
            slots["chore"] = chore[lang]
            state = ("chore", chore["id"])
        elif topic == "holiday":
            idx = self._keep(("holiday", ident.id), lambda: self.rng.randrange(len(life["holidays"])))
            slots["place"] = life["holidays"][idx][lang]
        elif topic == "birthday":
            slots["date"] = date_text(lang, *self._keep(("birthday", ident.id), self._birthday))

        def fill(text: str) -> str:
            return _cap(re.sub(r"\{(\w+)\}", lambda m: slots.get(m.group(1), m.group(0)), text))
        return [fill(q[lang])], {"yes": fill(q["yes"][lang]), "no": fill(q["no"][lang]), "state": state}

    async def chat(self, ident: Any, room: str | None, kind: str) -> list[str]:
        """A line of small talk about a character in the house (chatty mode); returns what was said."""
        self.task = asyncio.current_task()
        sentences, reply = self.chat_lines(ident, kind)
        if reply is not None:
            self._pending_reply[ident.id] = reply
        else:
            self._pending_reply.pop(ident.id, None)
        return await self._speak(sentences)

    def remember_reply(self, ident: Any, verdict: bool, state: tuple | None) -> None:
        """What a visitor answered for a character becomes the life of the house ("Luca ha pagato la luce?")."""
        if not state:
            return
        life = self.db["life"]
        if state[0] == "bill":
            b = self._bill(state[1], ident)
            b.update(paid=verdict, owner=ident.id, when=len(WHEN["it"]) - 1 if verdict else b["when"])
        elif state[0] == "chore":
            self.life[state] = {"who": ident.id, "done": verdict, "when": len(WHEN["it"]) - 1,
                                "excuse": self.rng.randrange(len(life["excuses"]))}
        elif state[0] == "shopping":
            d = self._keep(state, lambda: {"items": self.rng.randrange(len(life["groceries"]))})
            d.update(who=ident.id, done=verdict, when=len(WHEN["it"]) - 1)

    async def chat_reply(self, ident: Any, question: str, answer: str) -> list[str]:
        """After a visitor answered for a character: the reply for a yes or a no, and the house remembers it."""
        from .chatter import yes_or_no            # here: chatter imports this module
        reply = self._pending_reply.pop(ident.id, None) or {}
        verdict = yes_or_no(answer, self.lang, strict=True) if answer else None
        if verdict is None:
            text = ({"it": "Ah, interessante!", "en": "Oh, interesting!"} if answer
                    else {"it": f"Va bene {ident.name}, me lo dirai un'altra volta.",
                          "en": f"All right {ident.name}, you can tell me another time."})[self.lang]
        else:
            text = reply.get("yes" if verdict else "no") or {"it": "D'accordo!", "en": "All right!"}[self.lang]
            self.remember_reply(ident, verdict, reply.get("state"))
        return await self._speak([text])
