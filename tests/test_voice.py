# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The sentence parser, the answers and the synthesized sounds."""

from __future__ import annotations

import pytest

from domotiq.voice.intents import parse, parse_time
from domotiq.voice.tts import normalize as tts_normalize

NAMES = ["Marco", "Sofia", "Luna", "Leo"]

CASES = [
    ("dov'è Marco?", "where_is", {"name": "Marco"}),
    ("dove si trova sofia", "where_is", {"name": "Sofia"}),
    ("where is marko", "where_is", {"name": "Marco"}),
    ("chi c'è in cucina", "who_in", {"room": "kitchen"}),
    ("who's in the living room", "who_in", {"room": "living"}),
    ("quante persone ci sono in casa", "count", {"what": "persons"}),
    ("how many people are in the bathroom", "count", {"room": "bathroom"}),
    ("che temperatura c'è", "temperature", {}),
    ("quanta umidità c'è in bagno", "humidity", {"room": "bathroom"}),
    ("accendi la luce in cucina", "lights_on", {"room": "kitchen"}),
    ("luce rossa in camera", "lights_on", {"room": "bedroom", "color": "red"}),
    ("turn off the lights in the garage", "lights_off", {"room": "garage"}),
    ("spegni tutto", "lights_off", {}),
    ("fai festa", "party", {}),
    ("let's dance", "party", {}),
    ("accendi il barbecue", "grill", {}),
    ("spegni il barbecue", "grill_stop", {}),
    ("scenario cinema", "scene", {"scene": "cinema"}),
    ("buonanotte", "scene", {"scene": "night"}),
    ("dov'è la macchina", "car_where", {}),
    ("where is the car", "car_where", {}),
    ("che ore sono", "time_now", {}),
    ("sono le tre e mezza", "set_time", {"hour": 3, "minute": 30}),
    ("sono le 15 e 45", "set_time", {"hour": 15, "minute": 45}),
    ("com'è la casa", "house_summary", {}),
    ("cosa sai fare", "help", {}),
    ("parla inglese", "language", {"language": "en"}),
    ("speak italian", "language", {"language": "it"}),
    ("stai zitta", "verbosity", {"level": "silent"}),
    ("alza il volume", "volume", {"direction": "up"}),
    ("abbassa la musica", "volume", {"direction": "down"}),
    ("aggiungi un personaggio", "register", {}),
    ("chi sei", "who_are_you", {}),
    ("sì", "yes", {}),
    ("no", "no", {}),
    ("luna", "where_is", {"name": "Luna"}),
]


@pytest.mark.parametrize("text,intent,args", CASES)
def test_parse(text, intent, args):
    got = parse(text, NAMES)
    assert got is not None, text
    assert got.name == intent, (text, got)
    for k, v in args.items():
        assert got.args.get(k) == v, (text, got.args)


def test_nonsense_is_not_understood():
    assert parse("il cielo è blu stamattina", NAMES) is None
    assert parse("", NAMES) is None


def test_parse_time():
    assert parse_time("sono le dieci") == (10, 0)
    assert parse_time("sono le 9 e un quarto") == (9, 15)
    assert parse_time("it s 18 30") == (18, 30)


def test_tts_normalization():
    assert tts_normalize("Ci sono 24.3 °C", "it") == "Ci sono 24 virgola 3 gradi"
    assert tts_normalize("Humidity is 52%", "en") == "Humidity is 52 percent"


def test_sounds_and_music():
    from domotiq.audio import RATE, music, sounds
    for name in sounds.NAMES:
        s = sounds.sound(name)
        assert 0 < len(s) < RATE * 3 and abs(s).max() <= 0.81
    x = music.render(7, 5.0, 124)
    assert len(x) == RATE * 5 and abs(x).max() <= 0.86


def test_answers(env):
    from domotiq.model import Track
    from domotiq.voice import answers

    class Ctx:
        pass
    ctx = Ctx()
    ctx.layout, ctx.identities, ctx.house = env.layout, env.identities, env.house
    marco = env.identities.add("Marco", "person", color="#ff0000")
    env.house.update_tracks([Track("t1", 80, 100, category="person", identity=marco.id),
                             Track("t2", 90, 120, category="dog")], now=10)
    assert answers.where_is(ctx, "marco", "it") == "Marco è in cucina."
    assert answers.where_is(ctx, "Marco", "en") == "Marco is in the kitchen."
    assert "non conosco" in answers.where_is(ctx, "Pippo", "it").lower()
    assert answers.who_in(ctx, "kitchen", "it") == "In cucina ci sono Marco e un cane."
    assert answers.count(ctx, None, "persons", "it") == "In casa c'è 1 persona."
    assert answers.count(ctx, "bathroom", "persons", "en") == "There are 0 people in the bathroom."


def test_spoken_times_in_both_languages():
    from domotiq.voice.intents import parse
    cases = {
        "it's half past three": (3, 30), "it is quarter to five": (4, 45), "it's twenty past six": (6, 20),
        "it's ten to seven pm": (18, 50), "it's twenty five past eleven": (11, 25), "it's five twenty": (5, 20),
        "sono le tre e venticinque": (3, 25), "sono le otto meno venti": (7, 40), "sono le tre e tre quarti": (3, 45),
        "sono le sette e mezza di sera": (19, 30), "è l'una e dieci": (1, 10), "sono le 15 e 30": (15, 30),
    }
    for text, (h, m) in cases.items():
        i = parse(text, [])
        assert i is not None and i.name == "set_time", text
        assert (i.args["hour"], i.args["minute"]) == (h, m), text
    assert parse("what time is it", []).name == "time_now"
