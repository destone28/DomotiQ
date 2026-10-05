# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The sentence parser, the answers and the synthesized sounds."""

from __future__ import annotations

import pytest

from domotiq.voice.intents import name_from_speech, parse, parse_time
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
    ("quanti gradi ci sono in bagno", "temperature", {"room": "bathroom"}),
    ("la cucina è vuota?", "who_in", {"room": "kitchen"}),
    ("is the living room empty", "who_in", {"room": "living"}),
    ("la casa è vuota?", "who_in", {}),
    ("il garage è vuoto?", "car_where", {}),
    ("quante persone ci sono nella stanza vuota", "count", {}),
    ("fa freddo nella stanza vuota", "temperature", {}),
    ("how many degrees is it in the kitchen", "temperature", {"room": "kitchen"}),
    ("quante persone ci sono in cucina", "count", {"room": "kitchen"}),
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
    # as the Italian speech recognizer writes them, and with a word lost in a noisy room
    ("come la casa", "house_summary", {}),
    ("dove la macchina", "car_where", {}),
    ("dove marco", "where_is", {"name": "Marco"}),
    ("a nulla", "cancel", {}),
    ("buon giorno", "scene", {"scene": "normal"}),
    ("buona notte", "scene", {"scene": "night"}),
    ("cos'ha fatto Marco", "remember", {"name": "Marco"}),
    ("spegne la luce nel bagno", "lights_off", {"room": "bathroom"}),
    ("spendi tutte le luci", "lights_off", {}),
    ("accende la luce cucina", "lights_on", {"room": "kitchen"}),
    ("accedi alla luce in giardino", "lights_on", {"room": "garden"}),
    ("facciamo feste", "party", {}),
    ("chi in cucina", "who_in", {"room": "kitchen"}),
    ("chi si è cucina", "who_in", {"room": "kitchen"}),
    ("ti c'è in camera da letto", "who_in", {"room": "bedroom"}),
    ("se qualcuno in giardino", "who_in", {"room": "garden"}),
    ("a basso volume", "volume", {"direction": "down"}),
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
    assert parse("ho la pancia vuota", NAMES) is None
    assert parse("il frigo è vuoto", NAMES) is None
    assert parse("", NAMES) is None
    assert parse("dove sei", NAMES) is None
    assert parse("non serve a nulla", NAMES) is None
    assert parse("chi ha costruito questa casa", NAMES) is None
    assert parse("quanti anni hai", NAMES) is None                  # an age, not a head count


def test_whole_names():
    from domotiq.voice.intents import whole_names
    names = ["Honda Civic", "Mister Brown", "Mister Green", "Viola"]
    assert whole_names("honda mr", names) == []
    assert whole_names("mister green e viola", names) == ["Mister Green", "Viola"]
    assert whole_names("viola honda civic", names) == ["Viola", "Honda Civic"]


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


def test_name_from_speech():
    assert name_from_speech("ciao sono Marco") == "Marco"
    assert name_from_speech("mi chiamo Anna Maria") == "Anna Maria"
    assert name_from_speech("I'm Anna") == "Anna"
    assert name_from_speech("hello my name is Tom") == "Tom"
    assert name_from_speech("sono io") == ""
    assert name_from_speech("") == ""


def test_respellings_of_a_word_the_model_does_not_know():
    from domotiq.voice.stt import respellings
    r = respellings("rossellina")
    assert r[:3] == ["rosellina", "rosselina", "roselina"]
    assert "rosse lina" in r and "rose lina" in r
    assert respellings("leo") == []


class _Recognizer:
    """Vosk's recognizer, with the grammar it was given and a result already decided."""
    made: list = []
    final = {"text": "", "result": []}

    def __init__(self, model, rate, grammar=None):
        import json
        self.grammar = json.loads(grammar) if grammar else None
        _Recognizer.made.append(self)

    def SetWords(self, on):
        pass

    def AcceptWaveform(self, pcm):
        return False

    def PartialResult(self):
        import json
        return json.dumps({"partial": self.final["text"]})

    def FinalResult(self):
        import json
        return json.dumps(self.final)


def _listener(monkeypatch, tmp_path, vocabulary):
    import sys
    import types

    from domotiq.voice import stt
    monkeypatch.setitem(sys.modules, "vosk", types.SimpleNamespace(KaldiRecognizer=_Recognizer, Model=object,
                                                                   SetLogLevel=lambda level: None))
    listener = stt.Listener(tmp_path)
    listener._models["it"] = object()
    listener.known = lambda phrase, lang: all(w in vocabulary for w in phrase.split())
    return listener


def test_a_name_the_model_does_not_know_is_heard_with_a_spelling_it_knows(monkeypatch, tmp_path):
    """"Rossellina" is no word of the Italian model, and a grammar drops it: it is listened for as "rosellina" and
    the result has the name itself."""
    listener = _listener(monkeypatch, tmp_path, {"rosellina", "viola", "rosse", "lina", "mister", "green"})
    _Recognizer.final = {"text": "rosellina", "result": [{"word": "rosellina", "conf": 0.9}]}
    s = listener.session("it", ["Rossellina", "Viola", "Mister Green", "Qwzx"])
    assert _Recognizer.made[-1].grammar == ["rosellina", "viola", "mister green", "[unk]"]
    assert s.result() == ("rossellina", 0.9)
    s = listener.session("it", ["Rossellina"])
    assert s.feed_partial(b"") == "rossellina"
    assert s.sureness("rossellina") == 0.9
    _Recognizer.final = {"text": "viola rosellina", "result": [{"word": "viola", "conf": 1.0},
                                                               {"word": "rosellina", "conf": 0.8}]}
    assert listener.session("it", ["Rossellina", "Viola"]).result() == ("viola rossellina", 0.9)
    # the word of activation is listened for only as the model writes it (the free recognizer must find it too)
    listener.session("it", ["Rossellina"], False)
    assert _Recognizer.made[-1].grammar == ["[unk]"]
    # no spelling of one word as two that are part of the grammar: the name as two words the model knows
    listener = _listener(monkeypatch, tmp_path, {"rosse", "lina"})
    listener.session("it", ["Rossellina"])
    assert _Recognizer.made[-1].grammar == ["rosse lina", "[unk]"]


def test_alternatives_of_a_request(monkeypatch, tmp_path):
    """With alternatives the recognizer gives no confidence word by word: the result is the best sentence, sure as
    much as it is likelier than the others, and the other sentences come after it."""
    listener = _listener(monkeypatch, tmp_path, set())
    _Recognizer.final = {"alternatives": [{"text": "chi già in cucina", "confidence": 78.0},
                                          {"text": "chi c'è in cucina", "confidence": 78.0},
                                          {"text": "chi è cucina", "confidence": 70.0}]}

    def alternatives(self, n):
        self.n = n
    monkeypatch.setattr(_Recognizer, "SetMaxAlternatives", alternatives, raising=False)
    s = listener.session("it", None, True, 5)
    assert _Recognizer.made[-1].n == 5
    text, conf = s.result()
    assert text == "chi già in cucina"
    assert 0.49 < conf < 0.5
    assert s.alternatives() == ["chi già in cucina", "chi c'è in cucina", "chi è cucina"]
    # an utterance in two parts: each alternative of one part with the best of the other
    s.parts = [{"alternatives": [{"text": "accendi la luce", "confidence": 9.0}, {"text": "accendi la luna",
                                                                                 "confidence": 1.0}]},
               {"alternatives": [{"text": "in cucina", "confidence": 5.0}, {"text": "in cantina",
                                                                           "confidence": 4.0}]}]
    assert s.alternatives() == ["accendi la luce in cucina", "accendi la luna in cucina",
                                "accendi la luce in cantina"]
