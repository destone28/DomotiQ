# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the house learns when it does not know.

When a question gets no answer from the rules, the facts of the characters
or the life of the house, the house:
- answers with what it was told before for the same question, or one alike
  (the same words, or the same subject: "che tempo fa domani?" and "domani
  piove?" are both about the weather of tomorrow);
- about itself, imagines a plausible answer and says it is what it thinks
  ("Penso che..."), always the same for the same question;
- otherwise asks whoever asked ("Tu lo sai?"), and keeps the answer.

The answers about a character the facts can hold become its facts
(facts.learned_line); the others are kept here, in var/config/knowledge.json,
with the character they are about. An answer about today or tomorrow ("domani
piove") is kept for a day only.
"""

from __future__ import annotations

import difflib
import json
import logging
import random
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from .intents import find_names, find_room, normalize

log = logging.getLogger(__name__)

MAX_ITEMS = 300
DAY_S = 24 * 3600.0
ALIKE = 0.5                 # share of the words two questions must have in common to be the same question

# words that do not tell what a question is about
STOP = set("""cosa come dove quando quale quali chi perche quanto quanti quanta quante che non piu molto poco anche
ancora sempre mai gia sono sei siamo siete essere stato stata stati hanno avere hai ha abbiamo fare fatto fanno fa fai
fara faranno dice dire detto sapere sai sa so puoi posso dimmi raccontami parlami qualcosa tutto tutti quello questa
questo quella il lo la i gli le un una uno di del della dello dei degli delle da dal dalla in nel nella con su sul
sulla per tra fra a al alla e ed o ma se mi ti ci vi si ne suo sua suoi sue mio mia tuo tua loro c l secondo te tu
lei lui noi voi oggi ora adesso what which who whom does do did doing about would could should have has had with from
that this they them their there where when why how your you are is was were the a an of to in on at it be can will
tell know me my""".split())
TIMELY = re.compile(r"\b(oggi|domani|stasera|stamattina|stanotte|adesso|today|tomorrow|tonight|now)\b")
WEATHER = re.compile(r"\b(meteo|tempo fa|che tempo|tempo fara|piov\w*|pioggia|sole|soleggiat\w*|nuvol\w*|neve|nevic\w*|"
                     r"temporal\w*|vento|ombrello|weather|rain\w*|sunny|snow\w*|cloud\w*|umbrella)\b")
# a question about the house itself: its rooms and things, or asked to it ("quanti anni hai?")
HOUSE = re.compile(r"\b(casa|casetta|plastico|diorama|house|home|stanz\w*|pareti?|tett\w*|finestr\w*|porta|mobil\w*|"
                   r"divano|letto|cucina|bagno|garage|giardino|vialetto|totem|luci|led|webcam|telecamera|"
                   r"tu|te|ti|tuo|tua|tuoi|tue|hai|sei|you|your|yours)\b")
YES_NO = re.compile(r"^(si|sì|no|certo|certo che si|certo che no|yes|no|of course|of course not|sure)$")
# the word a question starts from: "come si fa la pizza?" and "dove si compra la pizza?" are not the same question
ASKS = {"come": "come", "how": "come", "dove": "dove", "where": "dove", "quando": "quando", "when": "quando",
        "perche": "perche", "why": "perche", "chi": "chi", "who": "chi", "quanto": "quanto", "quanti": "quanto",
        "quanta": "quanto", "quante": "quanto", "quale": "quale", "quali": "quale", "qual": "quale", "which": "quale",
        "cosa": "cosa", "what": "cosa"}
QUESTION = re.compile(r"^(ma |e |allora )?(come|cosa|che|chi|dove|quando|perche|quanto|quanti|quanta|quante|quale|"
                      r"quali|qual|how|what|who|where|when|why|which|is|are|do|does|can)\b")
# somebody wants to teach the house ("te lo dico io", "te lo dico io come si fa la pizza"), or tells it that what it
# has just said is wrong ("sbagliato", "non è vero, si fa con acqua e farina")
TEACH = re.compile(r"^(no |ma |adesso |allora |aspetta |guarda )*((te|ti) )?(lo |la )?(dico io|ti dico io|"
                   r"insegno io|spiego io|so io|i ll tell you|i will tell you|let me tell you)\b ?(?P<rest>.*)$")
WRONG = re.compile(r"^(no |ma |guarda )*(e |hai |la risposta e |risposta |that s |you re |that is |you are |it s )?"
                   r"(sbagliat\w*|non e vero|non e cosi|non e giusto|non e esatto|non e corretto|ti sbagli|falso|"
                   r"wrong|not true|not right|incorrect)\b ?(?P<rest>.*)$")


def _stems(text: str, names: Iterable[str] = ()) -> set[str]:
    """The words that tell what a question is about, cut to five letters ("piove" and "pioverà" are alike); the names
    of the characters, also heard a little wrong ("rossellino"), are no subject."""
    names = [n for n in names if n]
    t = normalize(text)
    for n in sorted({normalize(n) for n in names}, key=len, reverse=True):
        t = f" {t} ".replace(f" {n} ", " ").strip()
    name_words = {w for n in find_names(normalize(text), names) for w in normalize(n).split()}
    words = [w for w in t.split()
             if not any(difflib.SequenceMatcher(None, w, nw).ratio() >= 0.8 for nw in name_words)]
    return {w[:5] for w in words if w not in STOP and len(w) > 1}


def _asks(text: str) -> str | None:
    return next((ASKS[w] for w in normalize(text).split() if w in ASKS), None)


def lesson(text: str) -> tuple[str, str] | None:
    """("teach", what follows) for "te lo dico io (come si fa la pizza)", ("correct", what follows) for "sbagliato(,
    si fa con...)", None for anything else."""
    t = normalize(text)
    for kind, pattern in (("teach", TEACH), ("correct", WRONG)):
        m = pattern.match(t)
        if m:
            return kind, m.group("rest").strip()
    return None


def is_question(text: str) -> bool:
    return bool(QUESTION.match(normalize(text)))


def about_house(text: str) -> bool:
    t = normalize(text)
    return bool(HOUSE.search(t) or find_room(t))


def subject(text: str) -> str | None:
    """What a question is about, when its words are not the same as another's: the weather."""
    return "weather" if WEATHER.search(normalize(text)) else None


class Knowledge:
    def __init__(self, path: Path | str | None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self.items: list[dict[str, Any]] = []
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.items = [i for i in data if isinstance(i, dict) and i.get("q") and i.get("a")]
            except (OSError, ValueError) as e:
                log.warning("what the house learned could not be read: %s", e)
        for item in self.items:
            item.setdefault("id", uuid.uuid4().hex[:10])   # to be corrected or deleted from the web app

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".part")
            tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1))
            tmp.replace(self.path)
        except OSError as e:
            log.warning("what the house learned could not be kept: %s", e)

    def find(self, question: str, who: str | None = None, names: Iterable[str] = (),
             now: float | None = None) -> dict[str, Any] | None:
        """What the house was told (or imagined, or thought) for this question or one alike, about the same character
        (None: about no character). What somebody told wins over what the house imagined or thought; then the
        closest, then the latest."""
        best = self._alike(question, who, names, now)
        return best[0] if best else None

    def _alike(self, question: str, who: str | None, names: Iterable[str], now: float | None,
               every: bool = False) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        mine, topic, asks = _stems(question, names), subject(question), _asks(question)
        found: list[tuple[float, dict[str, Any]]] = []
        for item in self.items:
            if item.get("who") != who or (item.get("until") and item["until"] < now):
                continue
            theirs = set(item.get("k") or [])
            if topic and item.get("topic") == topic:
                s = 1.0 + (0.5 if mine & theirs else 0.0)
            elif mine and theirs:
                s = len(mine & theirs) / len(mine | theirs)
                if s < ALIKE and not (len(theirs) >= 2 and theirs <= mine):
                    continue
                if asks and _asks(item["q"]) not in (None, asks):
                    continue                           # "dove si compra la pizza?" is no "come si fa la pizza?"
            else:
                s = 1.0 if normalize(item["q"]) == normalize(question) else 0.0
                if not s:
                    continue
            found.append((s, item))
        if every:
            return [item for _, item in found]
        found.sort(key=lambda f: (not (f[1].get("generated") or f[1].get("invented")), f[0], f[1].get("at", 0)),
                   reverse=True)
        return [item for _, item in found]

    def learn(self, question: str, answer: str, who: str | None = None, names: Iterable[str] = (),
              invented: bool = False, now: float | None = None, generated: bool = False) -> dict[str, Any]:
        now = time.time() if now is None else now
        item = {"id": uuid.uuid4().hex[:10], "q": question.strip(), "a": answer.strip(),
                "k": sorted(_stems(question, names)), "topic": subject(question), "who": who, "at": round(now)}
        if invented:
            item["invented"] = True
        if generated:
            item["generated"] = True                       # written by the free answers model
        if TIMELY.search(normalize(question)) or TIMELY.search(normalize(answer)):
            item["until"] = round(now + DAY_S)             # "domani piove": true for a day
        with self._lock:
            for old in self._alike(question, who, names, now, every=True):
                # what somebody tells takes the place of every answer to that question (a wrong one the house thought
                # of first, above all); what the house thinks takes only the place of what it thought before
                if not (invented or generated) or old.get("generated") or old.get("invented"):
                    self.items.remove(old)
            self.items.append(item)
            del self.items[:-MAX_ITEMS]
            self._save()
        return item

    def get(self, item_id: str) -> dict[str, str] | None:
        """The question (as "name", for the change log) and the answer of one item, as they are now."""
        item = next((i for i in self.items if i.get("id") == item_id), None)
        return {"name": item["q"], "answer": item["a"]} if item else None

    def listing(self) -> list[dict[str, Any]]:
        """Everything learned, the latest first, for the web app."""
        return sorted(reversed(self.items), key=lambda i: i.get("at", 0), reverse=True)

    def correct(self, item_id: str, answer: str, question: str | None = None,
                names: Iterable[str] = ()) -> dict[str, Any] | None:
        """Somebody corrected an answer, and maybe the question heard wrong ("come si fa la vita"), in the web app:
        from now on it is what they told."""
        answer = re.sub(r"\s+", " ", answer or "").strip()[:300]
        question = re.sub(r"\s+", " ", question or "").strip()[:200]
        with self._lock:
            item = next((i for i in self.items if i.get("id") == item_id), None)
            if item is None or not answer:
                return None
            item["a"] = answer
            if question and question != item["q"]:
                item.update(q=question, k=sorted(_stems(question, names)), topic=subject(question))
            item.pop("generated", None)
            item.pop("invented", None)
            item["at"] = round(time.time())
            self._save()
        return item

    def forget(self, item_id: str) -> bool:
        with self._lock:
            before = len(self.items)
            self.items = [i for i in self.items if i.get("id") != item_id]
            if len(self.items) != before:
                self._save()
            return len(self.items) != before

    def forget_who(self, who: str) -> None:
        with self._lock:
            self.items = [i for i in self.items if i.get("who") != who]
            self._save()


def told(item: dict[str, Any], lang: str, name: str | None = None) -> str:
    """How the house says what it was told (or what it imagined, as it is)."""
    a = item["a"].strip().rstrip(".!")
    if item.get("invented") or item.get("generated"):
        return a + "."                                     # what the house imagined or thought: as it is
    it = lang == "it"
    if YES_NO.match(normalize(a)):
        yes = not normalize(a).startswith(("no", "of course not", "certo che no"))
        if it:
            return "Mi hanno detto di sì." if yes else "Mi hanno detto di no."
        return "I was told yes." if yes else "I was told no."
    if name and it:
        return f"Di {name} mi hanno detto questo: {a}."
    if name:
        return f"About {name} I was told this: {a}."
    return f"Mi hanno detto che {a}." if it else f"I was told that {a}."


# ------------------------------------------------------------------ what the house imagines about itself
INVENT = {
    "perche": [("Penso che sia perché chi mi ha costruita voleva così.",
                "I think it's because whoever built me wanted it that way."),
               ("Penso che sia per far stare più comodi i miei personaggi.",
                "I think it's to make my characters more comfortable."),
               ("Penso che sia perché così porto fortuna a chi mi abita.",
                "I think it's because that way I bring luck to whoever lives in me."),
               ("Penso che qualcuno l'abbia deciso tanto tempo fa, e nessuno l'abbia più cambiato.",
                "I think somebody decided it long ago, and nobody ever changed it.")],
    "chi": [("Penso che sia stato {name}: è sempre in mezzo a tutto!", "I think it was {name}: always in the middle of it!"),
            ("Penso che sia stato qualcuno con tanta pazienza e una stampante 3D.",
             "I think it was somebody with a lot of patience and a 3D printer.")],
    "quando": [("Penso che sia successo {when}.", "I think it happened {when_en}."),
               ("Penso che sia stato {when}, ma non ne sono sicura.", "I think it was {when_en}, but I'm not sure.")],
    "dove": [("Penso che sia {room}: è lì che finisce sempre tutto.", "I think it's {room_en}: that's where everything ends up."),
             ("Penso {room}, ma potrei sbagliarmi.", "I think {room_en}, but I could be wrong.")],
    "quanto": [("Penso che siano più di quanti immagini!", "I think there are more than you'd imagine!"),
               ("Penso circa {n}, ma non li ho mai contati bene.", "I think about {n}, but I never counted them properly.")],
    "come": [("Penso che sia una di quelle cose che si capiscono solo vivendo in una casa come me.",
              "I think it's one of those things you only understand living in a house like me."),
             ("Penso che funzioni con un po' di magia e tanti fili colorati.",
              "I think it works with a little magic and lots of coloured wires.")],
    "other": [("Penso che sia così perché sono una casa un po' speciale.",
               "I think it's like that because I'm a rather special house."),
              ("Penso di sì, ma è solo quello che penso io.", "I think so, but that's only what I think."),
              ("Penso che dipenda da chi abita qui: ognuno ha le sue abitudini.",
               "I think it depends on who lives here: everyone has their own habits.")],
}
WHEN = [("qualche anno fa, in una sera di festa", "a few years ago, on a party evening"),
        ("la settimana scorsa", "last week"), ("un lunedì mattina", "on a Monday morning"),
        ("il giorno in cui sono stata montata", "on the day I was put together")]
_ASKED = [("perche", r"^(ma )?(perche|why)\b"), ("chi", r"^(ma )?(chi|who)\b"), ("quando", r"^(ma )?(quando|when)\b"),
          ("dove", r"^(ma )?(dove|dov|where)\b"), ("quanto", r"^(ma )?(quant\w*|how (many|much|old|long))\b"),
          ("come", r"^(ma )?(come|how)\b")]


def invent(question: str, lang: str, names: list[str], rooms: list[tuple[str, str]], rng: random.Random) -> str:
    """A plausible answer about the house, said as what the house thinks."""
    t = normalize(question)
    kind = next((k for k, p in _ASKED if re.search(p, t)), "other")
    if kind == "chi" and not names:
        options = INVENT["chi"][1:]
    else:
        options = INVENT[kind]
    line = rng.choice(options)[0 if lang == "it" else 1]
    when = rng.choice(WHEN)
    room = rng.choice(rooms) if rooms else ("in cucina", "in the kitchen")
    values = {"name": rng.choice(names) if names else "", "when": when[0], "when_en": when[1], "room": room[0],
              "room_en": room[1], "n": str(rng.choice((7, 12, 20, 42, 100)))}
    for k, v in values.items():
        line = line.replace("{" + k + "}", v)
    return line


def asked_about(question: str, names: Iterable[str]) -> list[str]:
    """The characters a question names."""
    return find_names(normalize(question), list(names))


WAIT = re.compile(r"\b(aspett\w*|attend\w*|pensaci|ci pensi|pensa\w*|rispondi tu|dimmelo tu|dimmi tu|volentieri|"
                  r"tranquill\w*|wait|think|go ahead|you tell me)\b|"
                  r"^(s[iì]|ok|okay|va bene|certo|dai|yes|sure|ok dimmi|dimmi)( dai| pure| certo| va bene| ok)?$")
TELL = re.compile(r"\b(te lo dico io|lo dico io|dico io|te lo dico|ti dico io|lo so io|so io|glielo dico|"
                  r"i ll tell you|i will tell you|i know it|let me tell you)\b|^lo so\b|^i know\b")
DROP = re.compile(r"^(no|niente|nulla)$|\b(lascia stare|lascia perdere|non importa|non fa niente|no grazie|"
                  r"forget it|never mind|no thanks|doesn t matter)\b")


def think_choice(heard: str) -> str:
    """What the visitor chose after "aspetti qualche secondo, o me lo dici tu?": "wait" (also silence), "tell" (they
    will say it), "drop" (nobody knows, never mind) or "answer" (they said the answer itself)."""
    from .facts import nothing_told
    t = normalize(heard)
    if not t:
        return "wait"
    if DROP.search(t) or nothing_told(heard):
        return "drop"
    if TELL.search(t):
        return "tell"
    if WAIT.search(t) and len(t.split()) <= 5:
        return "wait"
    return "answer"
