# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Many ways to say the same thing, so that the house does not repeat itself.

Every phrase is a pair (Italian, English). `pick(key, options)` chooses one of
the options at random, never the one said last time for the same key, and
`fill(pair, name=..., where=...)` puts the values in place. Only the exact
placeholders are replaced (no `str.format`: a name typed by a visitor must not
be able to build a sentence of its own). Every line agrees with any name: no
adjective or participle that changes with the character.
"""

from __future__ import annotations

import random

Pair = tuple[str, str]


class Variety:
    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self._last: dict[str, int] = {}

    def pick(self, key: str, options: list[Pair]) -> Pair:
        if len(options) == 1:
            return options[0]
        last = self._last.get(key)
        i = self.rng.choice([k for k in range(len(options)) if k != last])
        self._last[key] = i
        return options[i]


VARIETY = Variety()


def pick(key: str, options: list[Pair]) -> Pair:
    return VARIETY.pick(key, options)


def fill(pair: Pair, **values: str) -> Pair:
    out = []
    for text in pair:
        for key, value in values.items():
            text = text.replace("{" + key + "}", value)
        out.append(text)
    return out[0], out[1]


def said(key: str, options: list[Pair], **values: str) -> Pair:
    """pick() and fill() together."""
    return fill(pick(key, options), **values)


def said_each(key: str, options: list[Pair], it: dict[str, str], en: dict[str, str]) -> Pair:
    """pick(), then each language filled with its own values (a room, a noun, a question in that language)."""
    a, b = pick(key, options)
    return fill((a, a), **it)[0], fill((b, b), **en)[1]


def capital(text: str) -> str:
    return text[:1].upper() + text[1:]


# ------------------------------------------------------------------ "who is it?"
NEWCOMER_Q = [
    ("{Where} vedo {noun}, giusto? {ask}", "I see {noun} {where}, right? {ask}"),
    ("C'è {noun} {where}, vero? {ask}", "There's {noun} {where}, isn't there? {ask}"),
    ("Mi sembra di vedere {noun} {where}: è così? {ask}", "I think I see {noun} {where}: is that right? {ask}"),
    ("{Where} è comparso qualcuno: {noun}, giusto? {ask}", "Someone has turned up {where}: {noun}, right? {ask}"),
]
ASK_NAME = {
    "person": [("Come si chiama?", "What's their name?"), ("Qual è il suo nome?", "What's the name?"),
               ("Mi dici come si chiama?", "Can you tell me the name?"), ("Che nome ha?", "What name do they have?")],
    "animal": [("Come si chiama?", "What's its name?"), ("Che nome ha?", "What's it called?"),
               ("Qual è il suo nome?", "What name does it have?")],
    "car": [("Come la chiamo?", "What shall I call it?"), ("Che nome le diamo?", "What name shall we give it?"),
            ("Come la vuoi chiamare?", "What would you like to call it?")],
    "object": [("Come lo chiamo?", "What shall I call it?"), ("Che nome gli diamo?", "What name shall we give it?"),
               ("Come lo vuoi chiamare?", "What would you like to call it?")],
}
CANDIDATES = [
    ("È {names}, o come si chiama?", "Is it {names}, or what's its name?"),
    ("È {names}? Oppure come si chiama?", "Is that {names}? Or what's its name?"),
    ("Si tratta di {names}, o di qualcun altro?", "Is it {names}, or someone else?"),
]
CONFIRM_KIND = [
    ("{Noun} di nome {name}, giusto?", "{Noun} called {name}, right?"),
    ("Quindi {noun} che si chiama {name}, vero?", "So {noun} called {name}, is that right?"),
    ("Ho capito {name}: {noun}, giusto?", "I got {name}: {noun}, right?"),
]
CONFIRM_NAME = [
    ("Si chiama {name}, giusto?", "The name is {name}, right?"),
    ("{name}, ho capito bene?", "{name}, did I get that right?"),
    ("Il nome è {name}, vero?", "So the name is {name}?"),
]
CONFIRM_AGAIN = [
    ("Dimmi sì o no: si chiama {name}?", "Say yes or no: is the name {name}?"),
    ("Scusa, è sì o no? Si chiama {name}?", "Sorry, yes or no? Is the name {name}?"),
]
NAME_AGAIN = [
    ("Come si chiama, allora?", "What's the name, then?"),
    ("E allora qual è il nome?", "So what is the name?"),
    ("Dimmi di nuovo il nome, per favore.", "Tell me the name again, please."),
]
WELCOME = [
    ("Piacere, {name}!", "Nice to meet you, {name}!"),
    ("Ciao {name}, piacere di conoscerti!", "Hello {name}, nice to meet you!"),
    ("Che bel nome! Piacere, {name}!", "What a nice name! Hello, {name}!"),
]
NAMED = [
    ("D'accordo: {name}!", "All right: {name}!"),
    ("Perfetto, {name}!", "Perfect, {name}!"),
    ("Segnato: {name}!", "Got it: {name}!"),
]
KNOWN = [
    ("Ah, è {name}! Grazie.", "Oh, it's {name}! Thanks."),
    ("Ma certo, {name}! Grazie.", "Of course, {name}! Thanks."),
    ("Ah, {name}! Adesso so chi è.", "Oh, {name}! Now I know who it is."),
]
NOTHING = [
    ("Ah, allora ho visto male: scusate!", "Oh, I must have seen wrong: sorry!"),
    ("Scusate, era solo un'impressione.", "Sorry, it was just my imagination."),
    ("Ops, mi ero sbagliata: non c'è nessuno.", "Oops, my mistake: nobody is there."),
]
ELSEWHERE = [
    ("{name} è già {where}: allora qui ho visto male, scusate!",
     "{name} is already {where}: so I saw wrong here, sorry!"),
    ("Ma {name} è {where}! Allora qui non c'è nessuno.", "But {name} is {where}! So nobody is here."),
    ("{name} è {where}, non qui: ho visto male.", "{name} is {where}, not here: I saw wrong."),
]
TOGETHER = [
    ("Ah, sono in due: {names}!", "Oh, there are two of them: {names}!"),
    ("Capito: {names}, insieme {where}.", "Got it: {names}, together {where}."),
    ("Ah, {names}, vicini vicini {where}!", "Oh, {names}, side by side {where}!"),
]
WHICH_ONES = [
    ("Chi sono, allora? Dimmi i nomi.", "Who are they, then? Tell me the names."),
    ("Quali? Dimmi i loro nomi.", "Which ones? Tell me their names."),
]
LATER = [
    ("Va bene, nessun problema: se vuoi me lo dici dalla webapp.",
     "All right, no problem: you can tell me later in the web app."),
    ("D'accordo, me lo dirai dopo dalla webapp.", "Fine, you can tell me later in the web app."),
    ("Nessun problema: puoi scriverlo sul telefono quando vuoi.", "No problem: you can type it on a phone whenever you like."),
]
GIVE_UP = [
    ("Va bene, lasciamo stare: me lo puoi dire dalla webapp.", "All right, let's leave it: you can tell me in the web app."),
    ("Lasciamo perdere per ora: c'è sempre la webapp.", "Let's leave it for now: there's always the web app."),
    ("Va bene, ci penseremo dopo: si può scrivere sul telefono.", "All right, we'll see later: it can be typed on a phone."),
]
WAITING = [
    ("Certo, aspetto.", "Sure, I'll wait."),
    ("Fai pure con calma.", "Take your time."),
    ("Nessuna fretta, aspetto.", "No hurry, I'll wait."),
]
WHAT_IS_IT = [
    ("Ah, scusa! Allora cos'è: una persona, un animale, un'auto o un oggetto?",
     "Oh, sorry! So what is it: a person, an animal, a car or an object?"),
    ("Ops! Che cos'è, allora: una persona, un animale, un'auto o un oggetto?",
     "Oops! What is it, then: a person, an animal, a car or an object?"),
    ("Scusa! Dimmi tu che cos'è: una persona, un animale, un'auto o un oggetto?",
     "Sorry! You tell me what it is: a person, an animal, a car or an object?"),
]
NOT_A_NAME = [
    ("Scusa, mi serve il nome. {ask}", "Sorry, I need the name. {ask}"),
    ("Scusa, non era un nome. {ask}", "Sorry, that wasn't a name. {ask}"),
    ("Non ho capito il nome. {ask}", "I didn't catch the name. {ask}"),
]
AFTER_COMMAND = [
    ("E il nuovo arrivato {where}? {ask}", "And the newcomer {where}? {ask}"),
    ("Torniamo al nuovo arrivato {where}. {ask}", "Back to the newcomer {where}. {ask}"),
]
YES_ASK = [("Bene! {ask}", "Good! {ask}"), ("Perfetto! {ask}", "Great! {ask}"), ("Ottimo! {ask}", "Perfect! {ask}")]
KIND_ASK = [("Ah, {noun}! {ask}", "Oh, {noun}! {ask}"), ("Capito, {noun}. {ask}", "I see, {noun}. {ask}"),
            ("Ah, allora {noun}! {ask}", "Oh, so {noun}! {ask}")]
NONE_OF_ASK = [("Va bene. {ask}", "All right. {ask}"), ("D'accordo. {ask}", "OK. {ask}"), ("Allora: {ask}", "Then: {ask}")]
THINKING = [("Fammi pensare...", "Let me think..."), ("Vediamo...", "Let me see..."), ("Un attimo...", "One moment...")]
WAKE_PROMPT = [("Dimmi!", "Yes?"), ("Sì, dimmi!", "Yes, tell me!"), ("Eccomi!", "I'm here!")]   # said at once

# ------------------------------------------------------------------ what happens in the house
ARRIVE = [
    ("Ecco {name} {where}!", "Here's {name} {where}!"),
    ("Guarda chi c'è {where}: {name}!", "Look who's {where}: {name}!"),
    ("{name} ora è {where}.", "{name} is now {where}."),
]
ENTER = [
    ("{name} entra in casa.", "{name} comes into the house."),
    ("Ecco {name} che entra in casa.", "Here comes {name} into the house."),
    ("{name} è in casa.", "{name} is in the house."),
]
TO_DRIVEWAY = [
    ("{name} esce sul vialetto.", "{name} goes out onto the driveway."),
    ("{name} va sul vialetto.", "{name} heads to the driveway."),
    ("{name} esce di casa.", "{name} steps out of the house."),
]
MOVE = [
    ("{name} va {where}.", "{name} goes {to}."),
    ("{name} si sposta {where}.", "{name} moves {to}."),
    ("{name} passa {where}.", "{name} heads {to}."),
]
LEAVE = [
    ("Ciao {name}, a presto!", "Bye {name}, see you soon!"),
    ("Arrivederci, {name}!", "Goodbye, {name}!"),
    ("A presto, {name}!", "See you soon, {name}!"),
]
CAR_PARKED = [
    ("L'auto è parcheggiata in garage.", "The car is parked in the garage."),
    ("Auto in garage!", "Car in the garage!"),
    ("L'auto è al suo posto, in garage.", "The car is in its place, in the garage."),
]
REST = [                                # on the bed or the sofa: fine
    ("{name} è {on}.", "{name} is {on}."),
    ("Ecco {name} {on}!", "Here's {name} {on}!"),
    ("{name} si mette {on}.", "{name} gets {on}."),
]
GET_OFF = [                             # on a table, a bench, the fridge...: not there!
    ("{name}, scendi subito {off}!", "{name}, get {off} right now!"),
    ("Ehi {name}, giù {off}, per favore!", "Hey {name}, get {off}, please!"),
    ("{name}! Scendi {off}, subito!", "{name}! Come down {off}, now!"),
]


def fixed_lines(*tables: list[Pair]) -> dict[str, list[str]]:
    """The lines with no placeholder, in both languages: synthesized ahead of time."""
    out: dict[str, list[str]] = {"it": [], "en": []}
    for table in tables:
        for it, en in table:
            if "{" not in it:
                out["it"].append(it)
            if "{" not in en:
                out["en"].append(en)
    return out
