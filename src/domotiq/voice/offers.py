# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the visitor means when the house offers to do something.

"Ti va un po' di musica?", "Accendo il barbecue?", "Siete in tanti in
soggiorno: facciamo festa?" may be answered with a word ("sì", "magari",
"no"), with a sentence ("sì dai, mettiamo un po' di musica", "no grazie, non
adesso"), or with another command of the house ("no, accendi il barbecue",
"metti la luce rossa in soggiorno"): a yes runs what was offered, a command
runs that command instead.

Short, common answers are understood at once by a few rules, and a command
in the answer is found by the parser of the commands (intents.py). Any other
sentence goes to the language model, which only says whether the visitor
accepts, refuses or neither: a grammar forces its output to one of the
three. Its instructions stay in a slot of llama-server of their own, read
once after each start.

Only offers are read this way. In a chat ("Qual è il tuo piatto
preferito?") an answer is never run as a command: "mi piace la musica" must
not start a party.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

from .intents import PATTERNS, Intent, normalize, parse

# what an offer can do, and what an answer may ask for instead
ACTIONS = ("party", "grill", "grill_stop", "scene", "lights_on", "lights_off")


@dataclass
class Answer:
    kind: str                       # yes, no, command, unsure, other, silence
    intent: Intent | None = None    # the command said instead (kind "command")
    source: str = "rules"
    accepted: bool = False          # a command said after a yes: what was offered is wanted too
    text: str = ""                  # the answer, normalized (kind "command")


# ------------------------------------------------------------------ rules
# all normalized (no accents, no apostrophes), checked in the order of by_rules()
NO_PHRASES = {"it": ["certo che no", "assolutamente no", "proprio no", "anche no", "ma quando mai"],
              "en": ["of course not", "absolutely not", "certainly not", "definitely not", "no way"]}
YES_PHRASES = {"it": ["perche no", "come no", "non vedo l ora", "non chiedo di meglio", "nessun problema",
                      "non c e problema"],
               "en": ["why not", "of course", "can t wait", "i d love to", "i would love to", "go ahead", "go for it",
                      "let s go", "let s do it", "do it", "sounds good", "sounds great", "sounds fun", "good idea",
                      "great idea", "count me in", "all right", "alright", "i d like that", "yes please",
                      "no problem"]}
# not now, or fine as things are: a no
LATER = {"it": ["piu tardi", "dopo", "un altra volta", "un altro giorno", "domani", "non ora", "non adesso",
                "lascia stare", "lascia perdere", "lasciamo stare", "lasciamo perdere", "meglio di no", "per ora no",
                "no grazie", "preferirei di no", "preferisco di no", "va bene cosi", "sto bene cosi",
                "stiamo bene cosi", "e gia tanto cosi"],
         "en": ["later", "not now", "another time", "some other time", "tomorrow", "no thanks", "no thank you",
                "rather not", "not really", "not today", "forget it", "never mind", "not right now", "i m fine",
                "i m good", "we re fine", "we re good", "i m ok"]}
# going away: a no, even with a yes inside ("let's go home")
LEAVING = {"it": ["andiamo via", "andiamo a casa", "torniamo a casa", "vado a casa", "devo andare", "dobbiamo andare",
                  "me ne vado", "ce ne andiamo"],
           "en": ["go home", "going home", "let s leave", "i have to go", "we have to go", "we re leaving",
                  "i m leaving"]}
UNSURE = {"it": ["non lo so", "non so", "boh", "forse", "dipende", "vediamo", "non saprei", "fai tu", "decidi tu",
                 "scegli tu", "come vuoi"],
          "en": ["i don t know", "don t know", "dunno", "not sure", "maybe", "depends", "up to you", "you decide",
                 "whatever", "let me think"]}
NO = {"it": ["no", "non", "mai", "niente", "nulla", "macche", "basta", "neanche", "nemmeno", "nessuno"],
      "en": ["no", "nope", "nah", "not", "never", "nothing", "don t", "stop"]}
YES = {"it": ["certo", "certamente", "esatto", "esattamente", "giusto", "va bene", "volentieri", "ok", "okay",
              "ovvio", "ovviamente", "sicuro", "sicuramente", "magari", "assolutamente", "dai", "vai", "andiamo",
              "facciamolo", "fallo", "fai pure", "procedi", "accendilo", "accendila", "mettila", "mettilo", "perfetto",
              "ottimo", "ottima idea", "bella idea", "buona idea", "benissimo", "d accordo", "evviva", "evvai",
              "mi va", "ci sta", "daje", "yes"],
       "en": ["yes", "yeah", "yep", "yup", "sure", "ok", "okay", "please", "absolutely", "definitely", "certainly",
              "great", "cool", "perfect", "lovely", "awesome", "right"]}
# the yes words that cannot be a piece of another word ("andiamo" may be "mangiamo" heard badly)
CLEAR_YES = {"it": ["si", "certo", "certamente", "volentieri", "va bene", "ok", "okay", "magari", "assolutamente",
                    "perche no", "come no", "esatto", "ovvio", "sicuro", "perfetto", "evviva", "d accordo",
                    "non vedo l ora"],
             "en": ["yes", "yeah", "yep", "sure", "ok", "okay", "absolutely", "definitely", "of course", "why not",
                    "i d love to", "sounds good"]}
# a yes at the start that also accepts the offer when a command follows ("sì, e accendi la luce")
FIRST_YES = {"it": ["si", "certo", "ok", "okay", "va bene", "volentieri", "certamente", "sicuro"],
             "en": ["yes", "yeah", "yep", "sure", "ok", "okay"]}
# "si" is also a pronoun ("si vede bene"): a yes at the start of the answer, after these, or in a short one
BEFORE_SI = {"eh", "ah", "oh", "beh", "ma", "e", "allora", "ehm", "uhm", "mah", "si"}
# "mi piace la musica" tells what someone likes, it asks for nothing
LIKING = ["mi piace", "mi piacciono", "adoro", "amo", "i like", "i love", "i enjoy"]
QUESTION_WORDS = {"cosa", "come", "dove", "dov", "quando", "perche", "chi", "quanto", "quanti", "quale", "qual",
                  "what", "how", "where", "when", "why", "who", "which", "is", "are", "do", "does", "can"}
# said to the house, not about the offer: "sei bellissima", "you're funny"
TO_THE_HOUSE = ["sei", "ti voglio", "ti amo", "you re", "you are", "i love you"]
NEGATIONS = {"non", "niente", "nessun", "nessuna", "senza", "mai", "not", "never", "don", "dont"}
# right before a yes phrase they turn it into a no: "not a good idea", "don't do it"
NOT_BEFORE = {"non", "mai", "not", "never", "t", "dont"}
# what someone cannot stand is a no to it: "odio la musica", "the barbecue stinks"
DISLIKE = re.compile(r"\b(odio|odiamo|detesto|detestiamo|schifo|puzza|puzzano|troppo alta|troppo forte|hate|dislike|"
                     r"can t stand|stinks|too loud)\b")
# a command asked for, not just named: "metti la musica", "facciamo festa", "light the barbecue"
REQUEST = re.compile(r"\b(accend\w*|mett\w*|fai|facciamo|fate|avvi\w*|attiv\w*|inizi\w*|cominci\w*|guardiam\w*|"
                     r"balliamo|festeggiamo|grigliamo|alza|voglio|vogliamo|vorrei|vorremmo|ci vuole|organizz\w*|"
                     r"prepar\w*|light|start|put|play|turn on|switch on|let s|lets|want|wanna|would like|d like|"
                     r"throw|fire up|watch|dance)\b")
# what may come with a command named alone ("un po' di musica", "the barbecue please")
FILLER = {"il", "lo", "la", "l", "i", "gli", "le", "un", "uno", "una", "po", "di", "del", "della", "dei", "delle",
          "e", "allora", "eh", "oh", "ah", "beh", "dai", "grazie", "the", "a", "an", "some", "of", "please", "and",
          "thanks"}
# switching off what was offered is a no ("spegni la musica" to "ti va un po' di musica?")
STOP = re.compile(r"\b(spegni|spengi|basta|stop|ferma|turn off|switch off)\b")
# a light command must say which light: "accendi il..." with a word the recognizer got wrong is no command
LIGHT_WORDS = {"luce", "luci", "lampada", "lampade", "tutto", "tutte", "light", "lights", "lamp", "lamps",
               "everything", "all"}
# the nouns a bare "no" can deny ("no musica"); before a verb it ends the refusal ("no, accendi la luce")
NOUNS = {"festa", "musica", "party", "music", "barbecue", "griglia", "grigliata", "grill", "bbq", "film", "movie",
         "cinema", "luce", "luci", "light", "lights"}

# words of the list given to the speech recognizer, besides yes and no: those of the command offered
COMMAND_WORDS = {
    "party": {"it": ["festa", "musica", "balliamo", "ballare"], "en": ["party", "music", "dance", "dancing"]},
    "grill": {"it": ["barbecue", "griglia", "grigliata", "accendilo"], "en": ["barbecue", "grill", "light it"]},
    "scene": {"it": ["film", "cinema", "guardiamo", "guardiamolo"], "en": ["film", "movie", "cinema", "watch"]},
    "lights_on": {"it": ["luce", "luci", "abbassa"], "en": ["light", "lights", "dim"]},
}
# in the spelling of the speech models
GRAMMAR_YES = {"it": ["sì", "certo", "certamente", "esatto", "giusto", "va bene", "volentieri", "ok", "okay",
                      "ovvio", "sicuro", "magari", "assolutamente", "perché no", "come no", "dai", "vai", "andiamo",
                      "facciamolo", "perfetto", "ottimo", "evviva", "d'accordo", "non vedo l'ora"],
               "en": ["yes", "yeah", "yep", "sure", "ok", "okay", "please", "absolutely", "definitely", "why not",
                      "of course", "go ahead", "let's go", "let's do it", "sounds good", "great", "i'd love to"]}
GRAMMAR_NO = {"it": ["no", "non", "niente", "mai", "grazie", "adesso", "dopo", "più tardi", "lascia stare",
                     "meglio di no", "non lo so", "non so", "boh", "forse"],
              "en": ["no", "nope", "not", "never", "thanks", "later", "not now", "no thanks", "maybe",
                     "i don't know", "not sure"]}


def grammar(offer: Intent, lang: str) -> list[str]:
    """What the speech recognizer listens for after an offer: yes, no, not now, and the words of the command."""
    return GRAMMAR_YES[lang] + GRAMMAR_NO[lang] + COMMAND_WORDS.get(offer.name, {}).get(lang, [])


def _has(t: str, phrase: str) -> bool:
    return f" {phrase} " in f" {t} "


def same(command: Intent, offer: Intent) -> bool:
    """The command does what was offered ("facciamo festa" to "ti va un po' di musica?")."""
    if command.name != offer.name:
        return False
    if command.name == "scene":
        return command.args.get("scene") == offer.args.get("scene")
    if command.name == "lights_on":
        return command.args.get("room") in (None, offer.args.get("room")) and "color" not in command.args
    return True


def _trigger(t: str, intent: str) -> re.Match | None:
    """Where the words that made the parser choose this command are."""
    found = [m for name, patterns in PATTERNS if name == intent for p in patterns if (m := re.search(p, t))]
    return min(found, key=lambda m: m.start()) if found else None


def _denied(t: str, intent: str, reach: int = 3) -> bool:
    """Is the command itself denied ("non accendere il barbecue", "niente musica", "la festa no",
    "don't light the barbecue")?"""
    m = _trigger(t, intent)
    if m is None:
        return False
    before, after = t[:m.start()].replace("don t ", "dont ").split(), t[m.end():].split()
    if any(w in NEGATIONS for w in before[-reach:]):
        return True
    noun = m.group(0).split()[0] in NOUNS
    return noun and (before[-1:] == ["no"] or after[:1] == ["no"])


def _named_alone(t: str, intent: str) -> bool:
    """Only the command, with a few small words around it: "musica", "un po' di musica", "barbecue!"."""
    m = _trigger(t, intent)
    return m is not None and all(w in FILLER for w in (t[:m.start()] + " " + t[m.end():]).split())


def _asked(t: str, intent: str) -> bool:
    """The command is asked for: a request ("mettiamo la musica"), or the command named alone."""
    return bool(REQUEST.search(t)) or _named_alone(t, intent)


def _phrase(t: str, phrases: list[str]) -> bool:
    """One of the phrases, not right after a negation ("not a good idea" is no "good idea")."""
    for p in phrases:
        for m in re.finditer(rf"(?<!\S){re.escape(p)}(?!\S)", t):
            if not NOT_BEFORE & set(t[:m.start()].split()[-2:]):
                return True
    return False


def clear_yes(text: str, lang: str) -> bool:
    t = normalize(text)
    return any(_has(t, w) for w in CLEAR_YES[lang])


def _says_yes(words: list[str], t: str, lang: str) -> bool:
    if any(_has(t, w) for w in YES[lang]):
        return True
    if lang != "it" or "si" not in words:
        return False
    i = words.index("si")
    return len(words) <= 3 or all(w in BEFORE_SI for w in words[:i])


def by_rules(text: str, lang: str, offer: Intent, names: list[str] | None = None) -> Answer | None:
    """A short, clear answer, or a command of the house; None when the sentence needs the language model."""
    t = normalize(text)
    if not t:
        return Answer("silence")
    words = t.split()
    if any(_has(t, p) for p in NO_PHRASES[lang]) or any(_has(t, p) for p in LEAVING[lang]):
        return Answer("no")
    if _phrase(t, YES_PHRASES[lang]):
        return Answer("yes")
    if STOP.search(t) and any(_has(t, w) for w in COMMAND_WORDS.get(offer.name, {}).get(lang, [])):
        return Answer("no")
    yes = _says_yes(words, t, lang)
    denied = any(w in NO[lang] for w in words) or any(_has(t, p) for p in NO[lang] if " " in p)
    liking = any(_has(t, p) for p in LIKING)
    command = parse(text, names or [])
    if command is not None and command.name in ("lights_on", "lights_off") and not (
            command.args.get("room") or command.args.get("color") or LIGHT_WORDS & set(words)):
        command = None
    if command is not None and command.name in ACTIONS:
        if same(command, offer):
            # the offered command itself denied, switched off or disliked: a no, whatever yes comes with it
            if _denied(t, command.name, reach=4) or STOP.search(t) or DISLIKE.search(t):
                return Answer("no")
            if denied and not yes:
                return Answer("no")
            if yes or liking or _asked(t, command.name):
                return Answer("yes")
            return None             # only talked about ("ieri abbiamo fatto festa"): the model tells
        lights = command.name in ("lights_on", "lights_off")       # a light command always asks for something
        if not liking and not _denied(t, command.name) and not DISLIKE.search(t) \
                and words[0] not in QUESTION_WORDS and (lights or _asked(t, command.name)):
            accepted = any(t == p or t.startswith(p + " ") for p in FIRST_YES[lang])
            return Answer("command", command, accepted=accepted, text=t)
    if any(_has(t, p) for p in LATER[lang]):
        return Answer("no")
    if any(_has(t, p) for p in UNSURE[lang]):
        return Answer("unsure")
    if denied:
        return Answer("no")
    if any(t.startswith(p + " ") for p in TO_THE_HOUSE) and not clear_yes(t, lang):
        return Answer("other")      # a compliment, even with a yes word in it: "you're great"
    if yes:
        return Answer("yes")
    if liking and any(_has(t, w) for w in COMMAND_WORDS.get(offer.name, {}).get(lang, [])):
        return Answer("yes")        # "I like music" to "how about some music?"
    if liking or words[0] in QUESTION_WORDS:
        return Answer("other")      # what someone likes, a question: nothing to run
    return None


def about(text: str, lang: str, offer: Intent) -> bool:
    """The answer is about the offer itself: it names what was offered ("niente musica", "sì, mettiamo la
    musica") or is one of the set phrases of a yes or a no ("no grazie, non mi va", "perché no")."""
    t = normalize(text)
    return (_trigger(t, offer.name) is not None or _phrase(t, YES_PHRASES[lang])
            or any(_has(t, p) for p in NO_PHRASES[lang] + LATER[lang] + LEAVING[lang]))


def action_intent(action: dict[str, Any], room: str | None) -> Intent | None:
    """A chatty question's action as the command the voice runs: the light is the one of the room asked about."""
    what = action.get("do")
    if what in ("party", "grill"):
        return Intent(what, {})
    if what == "scene":
        return Intent("scene", {"scene": action.get("scene", "normal")})
    if what == "light" and room:
        return Intent("lights_on", {"room": room, "color": action.get("color", "warm"),
                                    "brightness": int(action.get("brightness", 60))})
    return None


# ------------------------------------------------------------------ language model
SYSTEM = """A model smart home has just offered to do something for the visitors (music for a party, the barbecue, a film, softer lights...). Classify the visitor's answer to the offer.
Forms: yes (the answer accepts the offer or asks for it), no (the answer refuses it, says not now, or gives a reason against it), other (anything else).
The answers come from speech recognition, in Italian or English, and are often wrong. Unrelated words, a question, a compliment to the house, chit-chat or words that make no sense here are other."""

_EXAMPLES = [
    ("Ti va un po' di musica?", "sì dai mettiamo qualcosa", "yes"), ("Facciamo festa?", "che figata", "yes"),
    ("Accendo il barbecue?", "ho già mangiato", "no"), ("Guardiamo un film?", "che bello", "yes"),
    ("Ti abbasso le luci per riposare?", "sono proprio stanco", "yes"), ("Facciamo festa?", "sono stanco", "no"),
    ("Shall we party?", "I'm not in the mood", "no"), ("How about some music?", "that would be lovely", "yes"),
    ("Guardiamo un film?", "la porta del vicino", "other"), ("Ti va un po' di musica?", "che ore sono", "other"),
    ("Accendo il barbecue?", "di don", "other"), ("Shall we watch a film?", "what time is it", "other"),
    ("Accendo il barbecue?", "eh no", "no"), ("Ti va un po' di musica?", "magari più tardi", "no"),
    ("Shall we party?", "hell yeah", "yes"), ("Shall I dim the lights so you can rest?", "no I'm fine", "no"),
    ("Guardiamo un film?", "sei simpatica", "other"), ("Accendo il barbecue?", "alla grande", "yes"),
    ("Shall we watch a film?", "I'd rather not", "no"), ("Ti va un po' di musica?", "non ne ho voglia", "no"),
    ("Facciamo festa?", "venti trentanove", "other"), ("Shall I light the barbecue?", "I'm not hungry", "no"),
    ("Accendo il barbecue?", "abbiamo una fame da lupi", "yes"), ("Shall we party?", "count me in", "yes"),
    ("Guardiamo un film?", "c'è troppa gente", "no"), ("Facciamo festa?", "dov'è Marco", "other"),
    ("How about some music?", "you're funny", "other"), ("Ti va un po' di musica?", "sarebbe fantastico", "yes"),
    ("Facciamo festa?", "che bella casa", "other"), ("Shall I light the barbecue?", "the blue car", "other"),
    ("Ti abbasso le luci per riposare?", "sto bene così", "no"), ("Shall we watch a film?", "I'm bored", "yes"),
    ("Ti va un po' di musica?", "spezzoni lingua", "other"), ("How about some music?", "I love your garden", "other"),
    ("Guardiamo un film?", "ho troppo da fare", "no"), ("Shall we party?", "my feet hurt", "no"),
    ("Accendo il barbecue?", "il divano è comodo", "other"), ("Facciamo festa?", "è il compleanno di Anna", "yes"),
]


def _mixed(examples: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    out = list(examples)
    random.Random(7).shuffle(out)
    return out


EXAMPLES = _mixed(_EXAMPLES)
MIN_CONFIDENCE = 0.5       # below this the form was a guess: not understood
SURE = 0.9                 # a yes less sure than this is asked again: the wrong ones tend to be below it
GRAMMAR_GBNF = 'root ::= "yes" | "no" | "other"'


def _user(question: str, sentence: str) -> str:
    return f"Offer: {question}\nAnswer: {sentence}"


def messages(question: str, sentence: str) -> list[dict[str, str]]:
    out = [{"role": "system", "content": SYSTEM}]
    for asked, said, form in EXAMPLES:
        out.append({"role": "user", "content": _user(asked, said)})
        out.append({"role": "assistant", "content": form})
    out.append({"role": "user", "content": _user(question, sentence)})
    return out


def from_model(form: str, confidence: float = 1.0) -> Answer | None:
    """The model's form as an answer: a guess is not understood, and a yes it is not sure of is asked again
    (the small model takes a compliment or a misheard word for a yes now and then)."""
    head = form.strip().split()[:1]
    if head not in (["yes"], ["no"], ["other"]):
        return None
    if confidence < MIN_CONFIDENCE:
        return Answer("other", source="llm")
    if head == ["yes"] and confidence < SURE:
        return Answer("unsure", source="llm")
    return Answer(head[0], source="llm")
