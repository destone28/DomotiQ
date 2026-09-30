# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""From a sentence to an intent, without a language model.

Most of what visitors ask is short and predictable: "where is Marco?",
"turn on the kitchen light", "let's party". Keywords, the names of the
rooms and of the characters, colours and numbers are enough, and they are
tolerant of the mistakes of the speech recognizer. What this parser does
not understand goes to the language model.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..scenes import find_scene


@dataclass
class Intent:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "rules"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[’'`]", " ", text)
    text = re.sub(r"[^a-z0-9: ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


ROOMS = {
    "kitchen": ["cucina", "kitchen", "cucinino"],
    "living": ["soggiorno", "salotto", "sala", "living room", "living", "lounge", "sitting room", "salone"],
    "bedroom": ["camera da letto", "camera", "stanza da letto", "bedroom", "bed room", "letto"],
    "bathroom": ["bagno", "bathroom", "toilet", "toilette", "restroom"],
    "utility": ["locale tecnico", "tecnico", "ripostiglio", "utility room", "utility", "technical room"],
    "garage": ["garage", "box", "autorimessa"],
    "garden": ["giardino", "garden", "yard", "backyard", "cortile"],
    "driveway": ["vialetto", "ingresso", "entrata", "driveway", "front door", "entrance"],
}
COLORS = {
    "red": ["rosso", "rossa", "red"], "green": ["verde", "green"], "blue": ["blu", "blue"],
    "yellow": ["giallo", "gialla", "yellow"], "orange": ["arancione", "arancio", "orange"],
    "purple": ["viola", "purple", "violet"], "pink": ["rosa", "pink"], "white": ["bianco", "bianca", "white"],
    "cyan": ["azzurro", "azzurra", "celeste", "cyan", "light blue"], "warm": ["calda", "caldo", "warm"],
}
IT_NUMBERS = {"una": 1, "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
              "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "tredici": 13,
              "quattordici": 14, "quindici": 15, "sedici": 16, "diciassette": 17, "diciotto": 18,
              "diciannove": 19, "venti": 20, "ventuno": 21, "ventidue": 22, "ventitre": 23,
              "mezzanotte": 0, "mezzogiorno": 12, "trenta": 30, "quaranta": 40, "cinquanta": 50,
              "dieci minuti": 10}
EN_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
              "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "noon": 12, "midnight": 0}

# answers that are whole sentences on their own
SHORT_ONLY = ("cancel", "yes", "no")

# (intent, patterns); the first match wins, so order matters
PATTERNS: list[tuple[str, list[str]]] = [
    ("cancel", [r"\b(annulla|lascia stare|niente|cancel|never mind|stop)\b"]),
    ("set_time", [r"\bsono le\b", r"\be l una\b", r"\bit s \d", r"\bset the (time|clock)\b",
                  r"\bimposta l ora\b", r"\bl ora e\b", r"\bthe time is\b", r"\bo clock\b",
                  r"\bit (s|is) (half|quarter|\w+( \w+)? (minutes )?(past|to))\b", r"\bit (s|is) \w+( \w+)? (am|pm)\b",
                  r"\bit (s|is) (one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon|midnight)\b"]),
    ("time_now", [r"\bche or[ae]\b", r"\bche ora e\b", r"\bwhat time\b", r"\bwhat s the time\b"]),
    ("register", [r"\b(aggiungi|registra|nuovo|nuova) (un |una )?(personaggio|persona|oggetto|animale)\b",
                  r"\b(add|register) (a |an |new )*(character|person|object|pet)\b", r"\bnew character\b"]),
    ("language", [r"\b(parla|parliamo|in) (inglese|italiano)\b", r"\bspeak (english|italian)\b",
                  r"\bin (english|italian)\b", r"\b(english|inglese) please\b"]),
    ("verbosity", [r"\b(stai zitta|silenzio|zitta|be quiet|shut up|silent|quiet mode)\b",
                   r"\b(parla di piu|chiacchierona|talk more|chatty)\b", r"\b(parla normale|normal mode)\b"]),
    ("volume", [r"\bnon ti sento\b", r"\bi can t hear you\b", r"\b(alza|abbassa) (il |la )?(volume|musica)\b", r"\bvolume (su|giu|up|down)\b", r"\bpiu (forte|piano)\b",
                r"\b(louder|quieter|softer)\b", r"\b(turn|volume) (it )?(up|down)\b"]),
    ("party", [r"\b(festa|party|balliamo|ballare|musica|let s dance|dance)\b", r"\b(festeggia|celebr)\w*\b"]),
    ("grill", [r"\b(barbecue|grigliata|griglia|grill|bbq|grigliare|salsicce|braciole|sausages)\b"]),
    ("scene", [r"\bscenari[oa]\b", r"\bmodalita\b", r"\bscene\b", r"\bmode\b", r"\bcinema\b", r"\brelax\b",
               r"\bbuonanotte\b", r"\bgood night\b", r"\bbuongiorno\b", r"\bgood morning\b",
               r"\bvado a (dormire|letto)\b", r"\bandiamo a (dormire|letto)\b", r"\b(going|go) to (bed|sleep)\b",
               r"\b(usciamo|esco|esciamo|stiamo uscendo)\b", r"\b(we re|we are|i m|i am) (leaving|going out)\b",
               r"\bguardiamo un film\b", r"\bwatch a (film|movie)\b", r"\b(romantic|romantica|atmosfera)\b",
               r"\bserie tv\b", r"\bla tv\b", r"\bwatch tv\b", r"\brilassiam\w*\b", r"\brelax\w*\b"]),
    ("lights_off", [r"\b(spegni|spengi|turn off|switch off|lights off)\b", r"\bswitch (\w+ )?off\b", r"\bbuio\b",
                    r"\bturn (\w+ )?off\b", r"\btoo bright\b", r"\btroppa luce\b", r"\btogli la luce\b"]),
    ("lights_on", [r"\b(accendi|illumina|turn on|switch on|lights on|light up)\b", r"\bluce\b.*\b(rossa|verde|blu|gialla|viola|rosa|bianca|azzurra|arancione)\b",
                   r"\b(make|paint|colour|color)\b.*\b(red|green|blue|yellow|purple|pink|white|orange|cyan)\b"]),
    ("car_where", [r"\b(dov e|dove e|dove si trova|where is|where s) (l |la |the )?(auto|macchina|car|automobile)\b",
                   r"\b(auto|macchina|car)\b.*\b(garage|dove|where)\b"]),
    ("where_is", [r"\bdov e\b", r"\bdove e\b", r"\bdove si trova\b", r"\bdove sta\b", r"\bwhere is\b",
                  r"\bwhere s\b", r"\bwhere are\b", r"\bfind\b", r"\bcerca\b", r"\bin che stanza\b",
                  r"\bdove (si e |e )?(cacciat|finit|andat)\w*\b", r"\bwhere did \w+ go\b", r"\bwhere has \w+ gone\b"]),
    ("who_in", [r"\bchi c e\b", r"\bchi e in\b", r"\bchi sta\b", r"\bwho is in\b", r"\bwho s in\b",
                r"\bwho is there\b", r"\banyone in\b", r"\bc e qualcuno\b", r"\bis anyone\b",
                r"\bc e gente\b", r"\bis (there )?anybody\b", r"\bwho is (hanging|staying|sitting)\b"]),
    # "quanti gradi ci sono in bagno" asks for the temperature, not for a head count
    ("count", [r"\bquant[ie]\b(?!.*\b(gradi|umidita)\b)", r"\bhow many\b(?!.*\bdegrees\b)", r"\bnumero di persone\b", r"\b(crowded|affollat\w*)\b",
               r"\bsiamo in tanti\b"]),
    ("temperature", [r"\btemperatura\b", r"\bgradi\b", r"\bcaldo\b", r"\bfreddo\b", r"\btemperature\b",
                     r"\bsi gela\b", r"\bgela\b", r"\bfreezing\b",
                     r"\bhow (hot|warm|cold)\b", r"\bdegrees\b"]),
    ("humidity", [r"\bumidita\b", r"\bumido\b", r"\bhumidity\b", r"\bhumid\b", r"\bdoccia\b", r"\bshower\b",
                  r"\bvapore\b", r"\bsteam\w*\b"]),
    # "la cucina è vuota?": only about a room or the house ("il frigo è vuoto" is not a question for us)
    ("empty_room", [r"\bvuot[oa]\b", r"\bempty\b"]),
    ("joke", [r"\bbarzellett\w*\b", r"\bfammi ridere\b", r"\bjoke\b", r"\bmake me laugh\b", r"\bqualcosa di divertente\b"]),
    ("house_summary", [r"\bcom e la casa\b", r"\bcosa succede\b", r"\bsituazione\b", r"\bstato della casa\b",
                       r"\bhow is the house\b", r"\bwhat s happening\b", r"\bwhat is happening\b", r"\bstatus\b",
                       r"\braccont\w*\b", r"\bdescri\w*\b", r"\btell me about\b"]),
    ("who_are_you", [r"\bchi sei\b", r"\bcome ti chiami\b", r"\bwho are you\b", r"\bwhat s your name\b",
                     r"\bwhat is your name\b"]),
    ("help", [r"\bcosa sai fare\b", r"\baiuto\b", r"\bche cosa puoi\b", r"\bwhat can you do\b", r"\bhelp\b",
              r"\bcome funzioni\b", r"\bhow do you work\b", r"\bwhat do you know how to do\b", r"\bcosa puoi fare\b",
              r"\bwhat are you able to do\b", r"\bcosa sei capace\b"]),
    ("yes", [r"^(si|sì|certo|esatto|giusto|ok|okay|va bene|yes|yeah|yep|right|correct|sure)( .*)?$"]),
    ("no", [r"^(no|sbagliato|non e (lui|lei|giusto)|nope|wrong|not (him|her|right))( .*)?$"]),
]


# the words around a name when somebody introduces themselves: "ciao, sono Marco", "I'm Anna"
NAME_FILLERS = {"sono", "io", "mi", "chiamo", "chiama", "e", "il", "la", "lo", "l", "un", "una", "nome", "mio",
                "ciao", "salve", "buongiorno", "buonasera", "allora", "beh", "eh", "ehm", "si", "ok", "okay",
                "i", "am", "m", "it", "s", "is", "my", "name", "this", "call", "me", "the", "a", "hello", "hi",
                "hey", "well", "yes", "so", "um", "uh", "piacere", "grazie", "tu", "che", "di", "ho", "anni",
                "nice", "meet", "you", "to", "called", "and", "here", "im"}


def name_from_speech(text: str) -> str:
    """The name in a spoken introduction: at most two words, capitalised; "" if there is none."""
    words = [w for w in normalize(text).split() if w not in NAME_FILLERS and not w.isdigit()]
    return " ".join(words[:2]).title()


def find_room(text: str) -> str | None:
    for room, words in ROOMS.items():
        for w in sorted(words, key=len, reverse=True):
            if re.search(rf"\b{re.escape(w)}\b", text):
                return room
    return None


def find_color(text: str) -> str | None:
    for color, words in COLORS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", text) for w in words):
            return color
    return None


def find_name(text: str, names: Iterable[str], cutoff: float = 0.78) -> str | None:
    """The registered name mentioned in the sentence, tolerating recognizer errors."""
    names = list(names)
    if not names:
        return None
    norm = {normalize(n): n for n in names}
    for nn, orig in sorted(norm.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(nn)}\b", text):
            return orig
    words = text.split()
    grams = words + [" ".join(words[i:i + 2]) for i in range(len(words) - 1)]
    best, score = None, 0.0
    for g in grams:
        for nn, orig in norm.items():
            r = difflib.SequenceMatcher(None, g, nn).ratio()
            if r > score:
                best, score = orig, r
    return best if score >= cutoff else None


def _it_numbers() -> dict[str, int]:
    units = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici",
             "dodici", "tredici", "quattordici", "quindici", "sedici", "diciassette", "diciotto", "diciannove"]
    out = {w: i for i, w in enumerate(units)}
    for tens, word in ((20, "venti"), (30, "trenta"), (40, "quaranta"), (50, "cinquanta")):
        out[word] = tens
        for u in range(1, 10):
            stem = word[:-1] if u in (1, 8) else word          # ventuno, ventotto
            out[stem + units[u]] = tens + u
    out.update({"una": 1, "mezzanotte": 0, "mezzogiorno": 12})
    return out


IT_NUM = _it_numbers()
EN_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
            "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def _numbers(words: list[str]) -> list[int | str]:
    """Words with the numbers turned into integers ("twenty five" -> 25, "venticinque" -> 25)."""
    out: list[int | str] = []
    i = 0
    while i < len(words):
        w = words[i]
        if w.isdigit():
            out.append(int(w))
        elif w in IT_NUM:
            out.append(IT_NUM[w])
        elif w in EN_TENS:
            val = EN_TENS[w]
            if i + 1 < len(words) and words[i + 1] in EN_UNITS[1:10]:
                val += EN_UNITS.index(words[i + 1])
                i += 1
            out.append(val)
        elif w in EN_UNITS:
            out.append(EN_UNITS.index(w))
        elif w in ("noon", "midday"):
            out.append(12)
        elif w == "midnight":
            out.append(0)
        else:
            out.append(w)
        i += 1
    return out


def parse_time(text: str) -> tuple[int, int] | None:
    """A time of day said in Italian or English: "sono le tre e venticinque", "it's half past three"."""
    t = normalize(text)
    m = re.search(r"\b(\d{1,2})[: ](\d{2})\b", t)
    hour = minute = None
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        w = _numbers(t.split())
        nums = [(k, v) for k, v in enumerate(w) if isinstance(v, int)]
        text_w = [x if isinstance(x, str) else "numx" for x in w]
        joined = " ".join(text_w)

        def after(k):
            return next((v for j, v in nums if j > k), None)

        # English: half past three, quarter to five, twenty past six, ten to seven
        m2 = re.search(r"\b(half|quarter|numx)( minutes?)? (past|to) numx\b", joined)
        if m2:
            k_rel = len(joined[:m2.start()].split())
            first = w[k_rel]
            mins = 30 if first == "half" else 15 if first == "quarter" else first
            h = after(k_rel + (0 if isinstance(first, str) else 0))
            if isinstance(first, int):
                h = next((v for j, v in nums if j > k_rel), None)
            if h is not None and isinstance(mins, int):
                if m2.group(3) == "past":
                    hour, minute = h, mins
                else:
                    hour, minute = (h - 1) % 24, 60 - mins
        if hour is None and nums:
            k0, hour = nums[0]
            rest = text_w[k0 + 1:]
            later = [v for j, v in nums if j > k0]
            if "mezza" in rest or "mezzo" in rest:
                minute = 30
            elif re.search(r"\btre quarti\b", t):
                minute = 45
            elif "meno" in rest:
                i_meno = k0 + 1 + rest.index("meno")
                if "quarto" in text_w[i_meno:]:
                    minute = 45
                else:
                    m_less = next((v for j, v in nums if j > i_meno), None)
                    minute = 60 - m_less if m_less else 0
                hour = (hour - 1) % 24
            elif "quarto" in rest:
                minute = 15
            elif later:
                minute = later[0]
            else:
                minute = 0
    if hour is None or minute is None or hour > 23 or minute > 59:
        return None
    if re.search(r"\b(pm|pomeriggio|sera|stasera|evening|afternoon)\b", t) and hour < 12:
        hour += 12
    return hour, minute


def parse(text: str, names: Iterable[str] = ()) -> Intent | None:
    t = normalize(text)
    if not t:
        return None
    names = list(names)
    short = len(t.split()) <= 3
    for intent, patterns in PATTERNS:
        if intent in SHORT_ONLY and not short:
            continue                 # "si gela in camera" is not a yes, "the barbecue can stop now" is not a cancel
        if not any(re.search(p, t) for p in patterns):
            continue
        args: dict[str, Any] = {}
        if intent == "where_is":
            name = find_name(t, names)
            if not name:
                if find_room(t) and re.search(r"\b(chi|who)\b", t):
                    return Intent("who_in", {"room": find_room(t)}, 0.8)
                continue
            args["name"] = name
        elif intent == "empty_room":
            room = find_room(t)
            if not room and not re.search(r"\b(casa|house)\b", t):
                continue
            if room == "garage":
                return Intent("car_where", {}, 0.8)       # an empty garage is about the car
            return Intent("who_in", {"room": room} if room else {}, 0.9)
        elif intent in ("who_in", "count", "temperature", "humidity", "lights_off", "lights_on"):
            room = find_room(t)
            if room:
                args["room"] = room
            if intent == "lights_on":
                color = find_color(t)
                if color:
                    args["color"] = color
            if intent == "count":
                args["what"] = "animals" if re.search(r"\b(animali|animals|pets|cani|gatti|dogs|cats)\b", t) else "persons"
        elif intent == "scene":
            if re.search(r"buonanotte|good night", t):
                args["greeting"] = "night"
            elif re.search(r"buongiorno|good morning", t):
                args["greeting"] = "morning"
            scene = find_scene(t) or {"night": "night", "morning": "normal"}.get(args.get("greeting", ""))
            if not scene:
                for pattern, sid in ((r"\bnotte\b|\bnight\b|dormire|letto|bed|sleep", "night"),
                                     (r"uscia|esco|escia|uscendo|leaving|going out", "away"),
                                     (r"film|movie|\btv\b", "cinema"), (r"romantic|atmosfera|rilass|relax", "relax")):
                    if re.search(pattern, t):
                        scene = sid
                        break
            if not scene:
                continue
            args["scene"] = scene
        elif intent == "language":
            args["language"] = "en" if re.search(r"inglese|english", t) else "it"
        elif intent == "verbosity":
            args["level"] = ("silent" if re.search(r"zitta|silenzio|quiet|shut|silent", t)
                             else "chatty" if re.search(r"di piu|chiacchierona|more|chatty", t) else "normal")
        elif intent == "volume":
            args["direction"] = "down" if re.search(r"abbassa|giu|piano|down|quieter|softer", t) else "up"
        elif intent == "set_time":
            hm = parse_time(t)
            if not hm:
                continue
            args["hour"], args["minute"] = hm
        elif intent == "party" and re.search(r"\b(spegni|basta|stop|ferma)\b", t):
            continue
        elif intent == "grill" and re.search(r"\b(spegni|stop|ferma|turn off)\b", t):
            return Intent("grill_stop", {}, 0.9)
        return Intent(intent, args, 0.9)
    # a bare name is a "where is" question
    name = find_name(t, names, 0.85)
    if name and len(t.split()) <= 3:
        return Intent("where_is", {"name": name}, 0.7)
    return None
