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

import json
import logging
import random
import re
import threading
import time
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


def _stems(text: str, names: Iterable[str] = ()) -> set[str]:
    """The words that tell what a question is about, cut to five letters ("piove" and "pioverà" are alike)."""
    t = normalize(text)
    for n in sorted({normalize(n) for n in names if n}, key=len, reverse=True):
        t = f" {t} ".replace(f" {n} ", " ").strip()
    return {w[:5] for w in t.split() if w not in STOP and len(w) > 1}


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
        """What the house was told (or imagined) for this question or one alike, about the same character (None:
        about no character); the latest wins."""
        now = time.time() if now is None else now
        mine, topic = _stems(question, names), subject(question)
        best, score = None, 0.0
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
            else:
                s = 1.0 if normalize(item["q"]) == normalize(question) else 0.0
                if not s:
                    continue
            if s >= score:
                best, score = item, s
        return best

    def learn(self, question: str, answer: str, who: str | None = None, names: Iterable[str] = (),
              invented: bool = False, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        item = {"q": question.strip(), "a": answer.strip(), "k": sorted(_stems(question, names)),
                "topic": subject(question), "who": who, "at": round(now)}
        if invented:
            item["invented"] = True
        if TIMELY.search(normalize(question)) or TIMELY.search(normalize(answer)):
            item["until"] = round(now + DAY_S)             # "domani piove": true for a day
        with self._lock:
            old = self.find(question, who, names, now)
            if old is not None and old.get("k") == item["k"]:
                self.items.remove(old)                     # told again: the newer answer wins
            self.items.append(item)
            del self.items[:-MAX_ITEMS]
            self._save()
        return item

    def forget_who(self, who: str) -> None:
        with self._lock:
            self.items = [i for i in self.items if i.get("who") != who]
            self._save()


def told(item: dict[str, Any], lang: str, name: str | None = None) -> str:
    """How the house says what it was told (or what it imagined, as it is)."""
    a = item["a"].strip().rstrip(".!")
    if item.get("invented"):
        return a + "."
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
