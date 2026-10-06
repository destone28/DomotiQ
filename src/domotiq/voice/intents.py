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

_IT_UNITS = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici",
             "dodici", "tredici", "quattordici", "quindici", "sedici", "diciassette", "diciotto", "diciannove"]
_IT_TENS = {2: "venti", 3: "trenta", 4: "quaranta", 5: "cinquanta", 6: "sessanta", 7: "settanta", 8: "ottanta",
            9: "novanta"}
_EN_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
             "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}


def number_words(n: int, lang: str) -> str:
    """A number from 0 to 999 as the speech recognizer writes it: 21 is "ventuno" or "twenty one"."""
    if lang == "it":
        if n < 20:
            return _IT_UNITS[n]
        if n < 100:
            tens, unit = _IT_TENS[n // 10], n % 10
            if unit in (1, 8):
                tens = tens[:-1]                  # ventuno, ventotto
            return tens + (_IT_UNITS[unit] if unit else "")
        hundreds, rest = divmod(n, 100)
        return ("cento" if hundreds == 1 else _IT_UNITS[hundreds] + "cento") + (number_words(rest, lang) if rest else "")
    if n < 20:
        return _EN_UNITS[n]
    if n < 100:
        return _EN_TENS[n // 10] + (" " + _EN_UNITS[n % 10] if n % 10 else "")
    hundreds, rest = divmod(n, 100)
    return _EN_UNITS[hundreds] + " hundred" + (" " + number_words(rest, lang) if rest else "")


def spoken(text: str, lang: str) -> str:
    """A phrase as the speech recognizer would write it: normalized, numbers in words ("Casa 2" and "casa2" are
    "casa due", "R2D2" is "r due d due")."""
    t = normalize(re.sub(r"(?<=[a-zA-Z])(?=\d)|(?<=\d)(?=[a-zA-Z])", " ", text or ""))
    return " ".join(number_words(int(w), lang) if w.isdigit() and int(w) < 1000 else w for w in t.split())


# answers that are whole sentences on their own
SHORT_ONLY = ("cancel", "yes", "no")

# the words of the rooms, for the patterns that need one
_ROOMS = "|".join(sorted({w for ws in ROOMS.values() for w in ws}, key=len, reverse=True))

# Several patterns also take the sentence as the Italian speech recognizer writes it: "dov'è" and "com'è" come out
# as "dove" and "come", "annulla" as "a nulla", "spegni" and "accendi" as "spegne", "accende" or "accedi", and a
# word lost in a noisy room ("chi in cucina" for "chi c'è in cucina").

# (intent, patterns); the first match wins, so order matters
PATTERNS: list[tuple[str, list[str]]] = [
    ("cancel", [r"\b(annulla|lascia stare|niente|cancel|never mind|stop)\b", r"^a nulla$"]),
    ("set_time", [r"\bsono le\b", r"\be l una\b", r"\bit s \d", r"\bset the (time|clock)\b",
                  r"\bimposta l ora\b", r"\bl ora e\b", r"\bthe time is\b", r"\bo clock\b",
                  r"\bit (s|is) (half|quarter|\w+( \w+)? (minutes )?(past|to))\b", r"\bit (s|is) \w+( \w+)? (am|pm)\b",
                  r"\bit (s|is) (one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon|midnight)\b"]),
    ("time_now", [r"\bche or[ae]\b", r"\bche ora e\b", r"\bwhat time\b", r"\bwhat s the time\b"]),
    # "ricorda che Marco fa il medico": something to use in the stories (before everything that has a name)
    ("fact", [r"^(ricorda|ricordati|ricordate|memorizza|segnati) che\b", r"^(remember|note|keep in mind) that\b"]),
    # "l'ospite in soggiorno è Rosaria", "quello in cucina si chiama Marco": who a presence is, said aloud
    ("name_presence", [r"\b(l ospite|ospite|il personaggio|personaggio|la statuina|statuina|quello|quella|quel|"
                       r"la persona|il nuovo|la nuova|the guest|the figurine|the character|the one|the person|"
                       r"the new one)\b.*\b(si chiama|e|is called|is named|s name is|is)\s+\w+"]),
    # what the house really saw today (before where_is: "dov'è stato Marco" is not "dov'è Marco")
    ("remember", [r"\bcosa ha fatto\b", r"\bche (cosa )?ha fatto\b", r"\bdove e (stato|stata|andato|andata)\b",
                  r"\bdov e (stato|stata|andato|andata)\b", r"\bwhat (did|has) \w+( \w+)? (do|done|been doing)\b",
                  r"\bwhere (has|did) \w+( \w+)? (been|go)\b", r"\bchi e (stato|stata|passato|passata|entrato|entrata)\b",
                  r"\bchi c e stato\b", r"\bwho (has been|was|went) in\b", r"\bquante feste\b", r"\bhow many parties\b",
                  r"\bquante grigliate\b", r"\bhow many barbecues\b", r"\bcos ha fatto\b"]),
    ("story", [r"\b(raccont|narr|invent)\w* (una |un |la |qualche )?(storia|storie|favola|fiaba|racconto|avventura)\b",
               r"\b(storia|favola|fiaba|racconto) (su|di|della|del|dei|delle|sulla|sul|con)\b",
               r"\btell (me |us )?(a |another )?(story|tale|fairy tale)\b", r"\b(story|tale) about\b",
               r"\b(another|a new) story\b", r"\bun altra storia\b", r"\bstoria nuova\b"]),
    # a memory of the house (not a real one: the house makes it up, and then remembers it)
    ("recall", [r"\bti ricordi\b", r"\bvi ricordate\b", r"\bte lo ricordi\b", r"\bdo you remember\b",
                r"\bremember when\b", r"\bdo you recall\b"]),
    ("about", [r"\bcosa sai (di|su|del|della)\b", r"\bche sai (di|su)\b", r"\bparlami (di|del|della)\b",
               r"\bchi e\b", r"\bwhat do you know about\b", r"\btell me (something )?about\b", r"\bwho is\b",
               # with a name, these are about the character, never about the whole house
               r"\braccont\w* (anche |pure )?(qualcosa |tutto |quello che sai |cosa sai )?(di|su|del|della|dello|sul|sulla)\b",
               r"\bdimmi (qualcosa|tutto|quello che sai|cosa sai) (di|su|del|della|sul|sulla)\b",
               r"\bcosa (mi )?(sai|dici|racconti) (di|su|del|della|sul|sulla)\b", r"\bdescriv\w*\b", r"\bcosa fa\b",
               r"\bwhat about\b", r"\bwhat does \w+( \w+)? do\b"]),
    # "Mister Brown e Rossellina stanno insieme": two characters touching, one blob for both (two names needed)
    ("together", [r"\b(stanno|sono|state|stiamo|siamo) (tutti e due |tutte e due |entrambi |entrambe )?insieme\b",
                  r"\b(stanno|sono) (vicini|vicine|attaccati|attaccate|abbracciati|abbracciate)\b",
                  r"\b(are|stand|stay|sit) (both )?together\b", r"\bare (next to|close to) each other\b"]),
    # "accendi la luce preferita di Marco": the light in the colour a character told the house (a name is needed)
    # "chi sono i personaggi che conosci?": the characters the house knows, and who is in now
    ("characters", [r"\bchi (sono|son) (i|le|tutti i|tutte le) (personaggi|persone|statuine|ospiti)\b",
                    r"\b(quali|che) (personaggi|statuine|persone) (conosci|ci sono|hai)\b", r"\bchi conosci\b",
                    r"\b(personaggi|statuine) (che )?conosci\b", r"\bwho do you know\b",
                    r"\b(which|what) (characters|figurines|people) do you know\b", r"\bcharacters you know\b"]),
    ("lights_fav", [r"\b(luce|luci|colore|colori) preferit\w*\b", r"\bfavou?rite (light|lights|colou?r)\b"]),
    # "cosa mangia Marco?", "che musica piace a Giulia?": what the house was told about a character, by the
    # keywords of facts.py (before the commands: "musica" would start a party, a name alone is "where is")
    ("ask_fact", [r"\w"]),
    ("register", [r"\b(aggiungi|registra|nuovo|nuova) (un |una )?(personaggio|persona|oggetto|animale)\b",
                  r"\b(add|register) (a |an |new )*(character|person|object|pet)\b", r"\bnew character\b"]),
    ("language", [r"\b(parla|parliamo|in) (inglese|italiano)\b", r"\bspeak (english|italian)\b",
                  r"\bin (english|italian)\b", r"\b(english|inglese) please\b"]),
    ("verbosity", [r"\b(stai zitta|silenzio|zitta|be quiet|shut up|silent|quiet mode)\b",
                   r"\b(parla di piu|chiacchierona|talk more|chatty)\b", r"\b(parla normale|normal mode)\b"]),
    ("volume", [r"\bnon ti sento\b", r"\bi can t hear you\b", r"\b(alza|abbassa) (il |la )?(volume|musica)\b", r"\bvolume (su|giu|up|down)\b", r"\bpiu (forte|piano)\b",
                r"\ba basso volume\b",
                r"\b(louder|quieter|softer)\b", r"\b(turn|volume) (it )?(up|down)\b"]),
    # "fai presto", "let's body": "fai festa" and "let's party" as the recognizer heard them at the bench
    ("party", [r"\b(festa|feste|party|balliamo|ballare|musica|let s dance|dance)\b", r"\b(festeggia|celebr)\w*\b",
               r"\b(fai|facciamo|famo) presto\b", r"\blet s (body|bodies|potty)\b"]),
    ("grill", [r"\b(barbecue|grigliata|griglia|grill|bbq|grigliare|salsicce|braciole|sausages)\b"]),
    ("scene", [r"\bscenari[oa]\b", r"\bmodalita\b", r"\bscene\b", r"\bmode\b", r"\bcinema\b", r"\brelax\b",
               r"\bbuonanotte\b", r"\bbuona notte\b", r"\bgood night\b", r"\bbuongiorno\b", r"\bbuon giorno\b",
               r"\bgood morning\b",
               r"\bvado a (dormire|letto)\b", r"\bandiamo a (dormire|letto)\b", r"\b(going|go) to (bed|sleep)\b",
               r"\b(usciamo|esco|esciamo|stiamo uscendo)\b", r"\b(we re|we are|i m|i am) (leaving|going out)\b",
               r"\bguardiamo un film\b", r"\bwatch a (film|movie)\b", r"\b(romantic|romantica|atmosfera)\b",
               r"\bserie tv\b", r"\bla tv\b", r"\bwatch tv\b", r"\brilassiam\w*\b", r"\brelax\w*\b"]),
    # the air conditioning and the heating: the house has neither, and shows them with a wave of light, as the
    # thermostat does ("accendi il condizionatore" turned on the lights before)
    ("climate", [r"\b(condizionatore|climatizzatore|aria condizionata|riscaldamento|termosifon\w*|stufa|"
                 r"air conditioning|air conditioner|aircon|heating|heater)\b",
                 r"\b(accendi|spegni|spengi|spegne|metti|attiva|disattiva|turn on|turn off|switch on|switch off)\b"
                 r".*\bclima\b"]),
    ("lights_off", [r"\b(spegni|spengi|spegne|turn off|switch off|lights off)\b", r"\bswitch (\w+ )?off\b", r"\bbuio\b",
                    r"\bspendi (la|le|il|i|tutte|tutto)\b",
                    r"\bturn (\w+ )?off\b", r"\btoo bright\b", r"\btroppa luce\b", r"\btogli la luce\b"]),
    ("lights_on", [r"\b(accendi|illumina|turn on|switch on|lights on|light up)\b", r"\b(accende|accedi)\b.*\bluc[ei]\b", r"\bluce\b.*\b(rossa|verde|blu|gialla|viola|rosa|bianca|azzurra|arancione)\b",
                   r"\b(make|paint|colour|color)\b.*\b(red|green|blue|yellow|purple|pink|white|orange|cyan)\b",
                   r"\blights?\b.*\b(red|green|blue|yellow|purple|pink|white|orange|cyan)\b"]),
    ("car_where", [r"\b(dov e|dove e|dove|dove si trova|where is|where s) (l |la |the )?(auto|macchina|car|automobile)\b",
                   r"\b(auto|macchina|car)\b.*\b(garage|dove|where)\b"]),
    ("where_is", [r"\bdov e\b", r"\bdove e\b", r"^dove\b", r"\bdove si trova\b", r"\bdove sta\b", r"\bwhere is\b",
                  r"\bwhere s\b", r"\bwhere are\b", r"\bfind\b", r"\bcerca\b", r"\bin che stanza\b",
                  r"\bdove (si e |e )?(cacciat|finit|andat)\w*\b", r"\bwhere did \w+ go\b", r"\bwhere has \w+ gone\b"]),
    ("who_in", [r"\bchi c e\b", r"\bchi e in\b", r"\bchi sta\b", r"\bwho is in\b", r"\bwho s in\b",
                r"\bwho is there\b", r"\banyone in\b", r"\bc e qualcuno\b", r"\bis anyone\b",
                r"\bc e gente\b", r"\bis (there )?anybody\b", r"\bwho is (hanging|staying|sitting)\b",
                r"\b(ci|se) qualcuno\b", rf"^chi\b.*\b({_ROOMS})\b", rf"^(\w+ )?c e (in|nel|nella|dentro) (il |la |l )?({_ROOMS})\b"]),
    # "quanti gradi ci sono in bagno" asks for the temperature, "quanti anni hai" an age: not for a head count
    ("count", [r"\bquant[ie]\b(?!.*\b(gradi|umidita|anni)\b)", r"\bhow many\b(?!.*\bdegrees\b)", r"\bnumero di persone\b", r"\b(crowded|affollat\w*)\b",
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
                       r"\braccont\w*\b", r"\bdescri\w*\b", r"\btell me about\b", r"^come (e )?(a|da|la) casa$"]),
    ("who_are_you", [r"\bchi sei\b", r"\bcome ti chiami\b", r"\bwho are you\b", r"\bwhat s your name\b",
                     r"\bwhat is your name\b"]),
    ("help", [r"\bcosa sai fare\b", r"\baiuto\b", r"\bche cosa puoi\b", r"\bwhat can you do\b", r"\bhelp\b",
              r"\bcosa (ti )?(posso|possiamo|potrei) (chiederti|chiedere|dirti|dire|fare)\b",
              r"\bcosa ti (posso|si puo) (chiedere|dire)\b", r"\bwhat can (i|we) (ask|say|tell)\b",
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


NAME_ALIKE = 0.82        # a name heard a little wrong ("rossellino" for Rossellina) is still that name
# words that are part of many names, or ordinary words: a name of two words is not recognized by one of these alone
NAME_COMMON = {"mister", "signor", "signora", "signorina", "nonno", "nonna", "zio", "zia", "papa", "mamma", "babbo",
               "natale", "dottor", "dottore", "doctor", "miss", "lady", "king", "queen", "regina", "principe",
               "principessa", "capitan", "capitano", "super", "baby", "little", "piccolo", "piccola", "grande", "bello",
               "bella", "casa", "house"}


def find_names(text: str, names: Iterable[str]) -> list[str]:
    """Every known name in the sentence, in the order they are said ("Marco e Giulia"), also heard a little wrong
    ("rossellino" for Rossellina), and a name of two words also by the word only it has ("james brown" for Mister
    Brown; not a colour or an ordinary word: "verde" is no Mister Green)."""
    names = [n for n in dict.fromkeys(names) if n and normalize(n)]
    words = text.split()
    used = [False] * len(words)
    found: list[tuple[int, str]] = []

    def take(i: int, k: int, n: str) -> None:
        found.append((i, n))
        for j in range(i, i + k):
            used[j] = True
    for n in sorted(names, key=lambda n: -len(normalize(n))):          # as they are written, longest first
        key = normalize(n).split()
        k = len(key)
        for i in range(len(words) - k + 1):
            if not any(used[i:i + k]) and words[i:i + k] == key:
                take(i, k, n)
                break
    taken = {n for _, n in found}
    for n in names:                                                     # heard a little wrong
        if n in taken:
            continue
        key = " ".join(normalize(n).split())
        k = len(key.split())
        best, where = 0.0, None
        for i in range(len(words) - k + 1):
            if any(used[i:i + k]) or len(" ".join(words[i:i + k])) < 4:
                continue
            r = difflib.SequenceMatcher(None, " ".join(words[i:i + k]), key).ratio()
            if r > best:
                best, where = r, i
        if where is not None and best >= NAME_ALIKE:
            take(where, k, n)
            taken.add(n)
    colours = {w for ws in COLORS.values() for w in ws}
    owners: dict[str, list[str]] = {}
    for n in names:
        for w in set(normalize(n).split()):
            owners.setdefault(w, []).append(n)
    for n in names:                                                     # by the word only it has
        if n in taken or len(normalize(n).split()) < 2:
            continue
        own = [w for w in normalize(n).split() if len(owners[w]) == 1 and len(w) >= 4 and w not in NAME_COMMON
               and w not in colours and not find_room(w)]
        for i, w in enumerate(words):
            if not used[i] and w in own:
                take(i, 1, n)
                taken.add(n)
                break
    return [n for _, n in sorted(found)]


def whole_names(text: str, names: Iterable[str]) -> list[str]:
    """The known names said whole in the sentence, in the order they are said: for what a recognizer that knows only
    the names heard, where a word of a name alone ("honda" out of "andato") is no name."""
    words = text.split()
    found: list[tuple[int, str]] = []
    for n in sorted(dict.fromkeys(names), key=lambda n: -len(normalize(n))):
        key = normalize(n).split()
        for i in range(len(words) - len(key) + 1):
            if key and words[i:i + len(key)] == key and not any(i <= j < i + len(key) for j, _ in found):
                found.append((i, n))
                break
    return [n for _, n in sorted(found)]


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


# words that deny what comes after them ("non è Viola", "né Viola né Rosaria", "non la pizza, la pasta"); a "no"
# only denies what comes before it ("il mare no, la montagna"): "no, la pasta" chooses the pasta
DENY = {"non", "not", "niente", "mai", "never", "ne", "neither", "nor", "neanche", "nemmeno", "don", "dont", "isn",
        "nessun", "nessuna"}


def said_options(text: str, options: list[list[str]]) -> list[int]:
    """The options (each a list of words or phrases) said in the text and not denied, by their number:
    "non la pizza, la pasta" says the pasta, "il mare no, la montagna" the mountains, "né Viola né Rosaria"
    neither, "non so, il rosso" the red."""
    words = normalize(text).split()
    spots = []                                    # (first word, last word, option) of every mention
    for k, phrases in enumerate(options):
        for p in phrases:
            pw, n = normalize(p).split(), len(normalize(p).split())
            if pw:
                spots += [(i, i + n - 1, k) for i in range(len(words) - n + 1) if words[i:i + n] == pw]

    def denied(first: int, last: int) -> bool:
        if last + 1 < len(words) and words[last + 1] == "no":
            return True
        for j in range(max(0, first - 5), first):
            if words[j] in DENY and words[j + 1:j + 2] not in (["so"], ["saprei"], ["lo"]) \
                    and not any(j < f < first for f, _, _ in spots):
                return True                       # denied, and nothing else said between the denial and here
        return False

    return sorted({k for f, last, k in spots if not denied(f, last)})


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


def _about_character(text: str, names: list[str]) -> bool:
    """A question about the tastes, the job, the origin... of a character, not about the life of the house
    ("Luca ha pagato le bollette?" is for stories.py), except the holidays, which a fact may tell."""
    from . import facts                       # here: both modules import this one
    from .stories import life_topic
    if not facts.asks_about(text, names):
        return False
    return life_topic(text) in (None, "holiday") or facts.liking(text, names)


# words that are not the name of somebody after "dov'è" or "si chiama"
NOT_A_NAME = {"il", "lo", "la", "l", "i", "gli", "le", "un", "una", "uno", "the", "a", "an", "mio", "mia", "tuo", "tua",
              "nostro", "nostra", "my", "your", "our", "lui", "lei", "loro", "him", "her", "them", "it", "esso", "questo",
              "questa", "quello", "quella", "this", "that", "nessuno", "nobody", "vuoto", "vuota", "empty", "qui", "qua",
              "li", "la", "here", "there", "andato", "andata", "finito", "finita", "gone", "ora", "adesso", "now",
              "sempre", "always", "anche", "too", "also", "uguale", "same", "lo stesso", "nuovo", "nuova", "new"}


def _unknown_name(t: str) -> str | None:
    """"dov'è emilio": the name after "dov'è" when it is no character of the house (a name, not a thing: no article)."""
    m = re.search(r"\b(?:dov e|dove e|dove si trova|dove sta|where is|where s)\s+(\w+(?: \w+)?)\s*$", t)
    if not m:
        return None
    words = m.group(1).split()
    if words[0] in NOT_A_NAME or any(w in NOT_A_NAME for w in words) or find_room(m.group(1)) or find_color(m.group(1)):
        return None
    return " ".join(w.capitalize() for w in words)


def _named_as(t: str, names: list[str]) -> str | None:
    """The name said for a presence ("...si chiama Rosaria", "...è Marco"): a registered one if it sounds like it,
    otherwise the words as said (a new character)."""
    m = re.search(r"\b(?:si chiama|e|is called|is named|s name is|is)\s+(\w+(?: \w+)?)\s*$", t)
    if not m:
        return None
    said = m.group(1)
    known = find_names(said, names)
    if known:
        return known[0]
    words = said.split()
    if words[0] in NOT_A_NAME or any(w in NOT_A_NAME for w in words) or find_room(said) or find_color(said) \
            or len(said) < 3:
        return None
    return " ".join(w.capitalize() for w in words)


# a fact told as it is, with no "ricorda che" ("il colore preferito di Mister Blu è l'azzurro", "Mister Blu's
# favourite colour is light blue"), on lower case text with its accents and apostrophes
_STATED = [
    ("it", re.compile(r"^(?:il|la|lo|i|gli|le|l')\s*(?P<what>[^\W\d_]+(?: preferit[oaie])?) "
                      r"(?:di|del|della|dello|dei|degli|delle) (?P<who>.+?) (?:è|e|sono) (?P<value>.+)$")),
    ("en", re.compile(r"^(?P<who>.+?)'s (?P<what>favou?rite [a-z]+) (?:is|are) (?P<value>.+)$")),
    ("en", re.compile(r"^the (?P<what>favou?rite [a-z]+) of (?P<who>.+?) (?:is|are) (?P<value>.+)$")),
]


def stated_fact(text: str, names: Iterable[str]) -> dict[str, str] | None:
    """A fact about a character told as it is: its name, the fact as it reads after the name ("ha come colore
    preferito l'azzurro", the line of the answer to "qual è il tuo colore preferito?") and, for a colour, that
    question (the fact takes the place of the older answer). None for anything else: a question, a sentence
    about two characters, about something the facts do not tell ("la casa di Viola è...")."""
    from . import facts
    low = re.sub(r"\s+", " ", text.lower().replace("’", "'")).strip(" .!")
    for lang, rx in _STATED:
        m = rx.match(low)
        if m is None:
            continue
        who, what, value = find_names(normalize(m["who"]), names), m["what"], m["value"].strip()
        if len(who) != 1 or find_names(normalize(value), names) or "?" in value \
                or len(normalize(m["who"]).split()) > len(normalize(who[0]).split()) + 1:
            return None                     # "...di Viola e Rossana": two characters; "...è il rosso?": a question
        topics = facts.topics(what)
        if not topics and not re.search(r"preferit|favou?rite", what):
            return None
        if "colour" in topics and find_color(normalize(value)):
            line = facts.answer_line("a-colour", f"colour {find_color(normalize(value))}", "", lang)
            return {"name": who[0], "fact": line, "question": "a-colour"}
        if lang == "en":
            fact = f"loves {value}"
        elif "job" in topics:
            fact = f"fa {value}"            # "il lavoro di Mister Green è il pompiere": "fa il pompiere"
        else:
            fact = f"ha come {what} {value}"
        return {"name": who[0], "fact": fact}
    return None


def parse(text: str, names: Iterable[str] = ()) -> Intent | None:
    t = normalize(text)
    if not t:
        return None
    names = list(names)
    stated = stated_fact(text, names)
    if stated is not None:
        return Intent("fact", stated, 0.9)
    short = len(t.split()) <= 3
    found_names = find_names(t, names)
    for intent, patterns in PATTERNS:
        if intent in SHORT_ONLY and not short:
            continue                 # "si gela in camera" is not a yes, "the barbecue can stop now" is not a cancel
        if not any(re.search(p, t) for p in patterns):
            continue
        args: dict[str, Any] = {}
        if intent == "time_now" and found_names and _about_character(text, names):
            continue                 # "a che ora si sveglia Marco?" asks about Marco
        if intent == "fact":
            if not found_names:
                continue
            args["name"] = found_names[0]
        elif intent == "remember":
            room = find_room(t)
            if re.search(r"quante (feste|grigliate)|how many (parties|barbecues)", t):
                return Intent("remember", {"what": "parties"})
            if found_names:
                return Intent("remember", {"what": "day", "name": found_names[0]})
            if room and re.search(r"\bchi\b|\bwho\b", t):
                return Intent("remember", {"what": "room", "room": room})
            continue
        elif intent == "story":
            if found_names:
                args["names"] = found_names[:3]
            room = find_room(t)
            if room:
                args["room"] = room
            if re.search(r"\bfest|\bparty|\bcompleanno|\bbirthday", t):
                args["party"] = True
        elif intent == "recall":
            if found_names:
                args["names"] = found_names[:3]
        elif intent == "about":
            if not found_names:
                continue            # "chi è in cucina", "tell me about the house": other intents
            if re.search(r"\bchi e (in|nel|nella|dentro)\b|\bwho is in\b", t):
                continue
            args["name"] = found_names[0]
        elif intent == "together":
            if not found_names:
                continue                      # one name only: the house asks who the other one is
            args["names"] = found_names[:3]
            room = find_room(t)
            if room:
                args["room"] = room
        elif intent in ("house_summary", "help", "who_are_you") and found_names:
            continue                # with a name, the question is about that character
        elif intent == "lights_fav":
            # a request ("accendi", "metti", "turn on"...), not a question ("qual è il colore preferito di Marco?")
            if not found_names or not re.search(r"\b(accend\w*|mett\w*|fai|turn|switch|put|light up|show|make)\b", t):
                continue
            args["name"] = found_names[0]
            room = find_room(t)
            if room:
                args["room"] = room
        elif intent == "ask_fact":
            if not found_names or not _about_character(text, names):
                continue
            from . import facts
            args["name"] = found_names[0]
            args["topic"] = facts.question_topic(text, names)
        elif intent == "where_is":
            name = find_name(t, names)
            if not name:
                if find_room(t) and re.search(r"\b(chi|who)\b", t):
                    return Intent("who_in", {"room": find_room(t)}, 0.8)
                unknown = _unknown_name(t)
                if unknown:
                    return Intent("where_is", {"name": unknown}, 0.6)   # "dov'è Emilio?": not one it knows
                continue
            args["name"] = name
        elif intent == "name_presence":
            room = find_room(t)
            said = _named_as(t, names)
            if not room or not said:
                continue
            args["room"], args["name"] = room, said
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
            if re.search(r"buonanotte|buona notte|good night", t):
                args["greeting"] = "night"
            elif re.search(r"buongiorno|buon giorno|good morning", t):
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
        elif intent == "climate":
            args["mode"] = "warm" if re.search(r"riscald|termosif|stufa|heat", t) else "cool"
            args["on"] = not re.search(r"\b(spegni|spengi|spegne|disattiva|ferma|basta|stop|turn off|switch off)\b", t)
        elif intent == "language":
            args["language"] = "en" if re.search(r"inglese|english", t) else "it"
        elif intent == "verbosity":
            args["level"] = ("silent" if re.search(r"zitta|silenzio|quiet|shut|silent", t)
                             else "chatty" if re.search(r"di piu|chiacchierona|more|chatty", t) else "normal")
        elif intent == "volume":
            args["direction"] = "down" if re.search(r"abbassa|basso|giu|piano|down|quieter|softer", t) else "up"
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
