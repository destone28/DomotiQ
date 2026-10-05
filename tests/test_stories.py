# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Stories generated from the local database, the life of the house, memories of the day and facts."""

from __future__ import annotations

import asyncio
import random
import re
import time
from types import SimpleNamespace

import pytest

from domotiq.app import build, parse_args
from domotiq.voice import memory
from domotiq.voice.intents import Intent
from domotiq.voice.stories import MONTHS, fact_lang, is_job, load_db, sentence_lang

KITCHEN, LIVING, GARDEN = (80, 100), (300, 100), (300, 400)
SENTENCE = re.compile(r"^[A-ZÀ-Ú\"«].*[.!?]$", re.S)


@pytest.fixture
def ctx(tmp_path):
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera", "--no-llm"]))
    from domotiq.voice.manager import Voice
    c.voice = Voice(c)
    c.voice.stories.rng = random.Random(7)
    c.said = []
    c.bus.subscribe("say", lambda ev: c.said.append(ev.get("text")))
    c.voices = []                                   # (sentence, language of the voice) as synthesized

    async def speak(*args, **kwargs):
        await asyncio.sleep(0)

    async def synth(text, lang):
        c.voices.append((text, lang))
        return [0.0] * 10

    async def play(samples):
        await asyncio.sleep(c.play_s)
    c.play_s = 0.0
    c.voice.speak = speak
    c.voice.speaker.synth = synth
    c.voice.play = play
    yield c
    c.store.close()


def place(ctx, name, where, category="person"):
    ident = ctx.identities.add(name, category)
    ctx.sim.add(*where, category, ident.id, "#e03030", name)
    ctx.house.update_tracks(ctx.sim.tracks(), time.time())
    return ident


def well_formed(sentences):
    for s in sentences:
        assert "{" not in s and "}" not in s, s
        assert "  " not in s and " ," not in s and " ." not in s, s
        assert SENTENCE.match(s), s


# ------------------------------------------------------------------ the database
def test_the_database_holds_together():
    db = load_db()
    events = {e["id"] for e in db["events"]}
    for pool in ("discoveries", "reactions", "helps", "endings"):
        for piece in db[pool]:
            assert set(piece.get("for", ())) <= events, piece
    for e in db["events"]:                          # every event can be explained
        assert any(e["id"] in d.get("for", ()) for d in db["discoveries"]), e["id"]
    for group in ("people", "animals"):
        for slot, items in db[group].items():
            assert all(x.get("id") for x in items), (group, slot)
            assert len({x["id"] for x in items}) == len(items), (group, slot)
    for plot in db["plots"]:
        assert len(plot["it"]) == len(plot["en"]), plot["id"]
    for piece in db["relations"] + db["anecdotes"]:
        assert ("{a}" in piece["it"]) == ("{a}" in piece["en"]), piece


# ------------------------------------------------------------------ stories
def test_stories_are_well_formed_in_both_languages(ctx):
    st = ctx.voice.stories
    place(ctx, "Marco", KITCHEN)
    place(ctx, "Giulia", LIVING)
    place(ctx, "Fido", GARDEN, "dog")
    ctx.identities.add("Micio", "cat")
    casts = [None, ["Marco"], ["Fido"], ["Micio"], ["Marco", "Giulia"], ["Fido", "Micio"], ["Giulia", "Fido"]]
    for lang in ("it", "en"):
        for i in range(200):
            names = casts[i % len(casts)]
            sentences, cast = st.compose(names, room=("bathroom" if i % 11 == 0 else None), party=i % 9 == 0,
                                         lang=lang)
            well_formed(sentences)
            assert 4 <= len(sentences) <= 6
            assert all(c.name in " ".join(sentences) for c in cast)
    # a dog does not hiss and a cat does not bark
    for _ in range(80):
        cat_story = " ".join(st.compose(["Micio"], lang="it")[0])
        assert "abbai" not in cat_story and "scodinzol" not in cat_story


def test_every_story_about_a_character_is_new(ctx):
    st = ctx.voice.stories
    marco = place(ctx, "Marco", KITCHEN)
    place(ctx, "Giulia", LIVING)
    told = [tuple(st.compose(["Marco"], lang="it")[0]) for _ in range(12)]
    assert len(set(told)) == 12
    plots = {k for k in st.used[marco.id] if k.startswith("plot:")}
    assert plots == {"plot:alone", "plot:job", "plot:pair", "plot:pair_quirk", "plot:room"}
    firsts = [s[0] for s in told[:5]]
    assert len(set(firsts)) == 5


def test_a_character_keeps_its_personality_until_the_restart(ctx):
    st = ctx.voice.stories
    marco = place(ctx, "Marco", KITCHEN)
    giulia = place(ctx, "Giulia", LIVING)
    first = st.persona(marco)
    job_it, job_en = first["job"]["it"], first["job"]["en"]
    jobs_said = set()
    for _ in range(40):
        for lang in ("it", "en"):
            text = " ".join(st.compose(["Marco"], lang=lang)[0])
            if "Marco, che " + job_it in text or "Marco, who " + job_en in text:
                jobs_said.add(lang)
            for other in st.db["people"]["jobs"]:
                if other["id"] != first["job"]["id"]:
                    assert f"Marco, che {other['it']}" not in text and f"Marco, who {other['en']}" not in text
    assert jobs_said == {"it", "en"}
    assert st.persona(marco) is first
    assert st.persona(giulia)["job"]["id"] != first["job"]["id"]          # everyone their own
    st.reset()                                                           # what a restart does
    assert st.personas == {}


def test_the_facts_of_the_staff_come_first(ctx):
    st = ctx.voice.stories
    marco = place(ctx, "Marco", KITCHEN)
    ctx.identities.update(marco.id, facts=["fa il medico", "ama il jazz", "is afraid of spiders"])
    marco = ctx.identities.get(marco.id)
    assert st.job(marco, "it")["text"] == "fa il medico"
    assert st.job(marco, "en")["text"] == "works at the hospital"         # the same job in the other language
    it_texts = [" ".join(st.compose(["Marco"], lang="it")[0]) for _ in range(40)]
    en_texts = [" ".join(st.compose(["Marco"], lang="en")[0]) for _ in range(40)]
    assert any("Marco, che fa il medico" in t for t in it_texts)
    assert any("ama il jazz" in t for t in it_texts)
    assert any("Marco, who works at the hospital" in t for t in en_texts)
    assert any("is afraid of spiders" in t for t in en_texts)
    assert not any("spiders" in t for t in it_texts) and not any("ama il jazz" in t for t in en_texts)


def test_what_a_fact_is():
    assert is_job("fa il medico") and is_job("è una maestra") and is_job("is a doctor") and is_job("a nurse")
    assert is_job("lavora in banca") and is_job("fa il medico di famiglia")
    assert not is_job("fa la spesa ogni sabato") and not is_job("è un grande amico di Luca")
    assert not is_job("ama il jazz") and not is_job("loves jazz")
    assert fact_lang("ama il jazz") == "it" and fact_lang("loves jazz") == "en" and fact_lang("Juventus") is None


def test_the_language_of_a_sentence_typed_by_the_staff():
    assert sentence_lang("Proprio in quel momento dal soffitto cominciò a cadere qualche goccia d'acqua.", "it") == "it"
    assert sentence_lang("Marco entrò in cucina con una torta.", "en") == "it"
    assert sentence_lang("Then he saw that the cake was gone and the kitchen was empty.", "it") == "en"
    assert sentence_lang("Marco is in the kitchen.", "en") == "en"


def test_facts_by_voice_and_what_the_house_knows(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        await ctx.voice.execute(Intent("fact", {"name": "Marco", "text": "ricorda che marco fa il medico"}))
        assert ctx.identities.get(marco.id).facts == ["fa il medico"]
        assert ctx.said[-1] == "Me lo ricorderò: Marco fa il medico."
        ctx.identities.add_fact(marco.id, "loves jazz")
        await ctx.voice.execute(Intent("about", {"name": "Marco"}))
        p = ctx.voice.stories.persona(ctx.identities.get(marco.id))
        assert ctx.said[-5] == "Marco è in cucina."                       # where Marco is now, first
        assert ctx.said[-4] == "Mi hai detto che Marco fa il medico."
        assert ctx.said[-2] == "Marco loves jazz."
        assert ctx.said[-1].startswith("E poi so che Marco " + p["trait"]["it"])
        assert p["job"]["it"] not in ctx.said[-1]                          # the job the staff gave, not another
        assert ("Marco loves jazz.", "en") in ctx.voices                   # read by the English voice
        assert ctx.said[-3] == "Me l'hai detto anche in inglese:"
        en = ctx.voice.stories.about("Marco", "en")
        assert en[0] == ("Marco is in the kitchen.", "en")
        assert en[1] == ("You told me that Marco loves jazz.", "en") and en[2] == ("You also told me in Italian:", "en")
    asyncio.run(scenario())


def test_a_story_is_told_and_the_lights_go_back(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        assert await ctx.voice.stories.tell(["Marco"])
        assert 4 <= len(ctx.said) <= 6
        assert all(lang == "it" for _, lang in ctx.voices)
        assert ctx.lights.state()["kitchen"]["source"] in ("auto", "off", "follow")
        assert ctx.store.events(types=["story"])[0]["data"]["cast"][0] == "Marco"
    asyncio.run(scenario())


def test_talk_stops_a_story(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        v = ctx.voice
        ctx.play_s = 0.2

        async def listen(grammar, *, stop=None, max_s=5.0, auto_end=True, **_):
            return "", 0.0, b""
        v._listen = listen
        v._talk_task = v._spawn(v.execute(Intent("story", {"names": ["Marco"]})))
        for _ in range(30):
            await asyncio.sleep(0.01)
        assert v.stories.active
        await v.talk_button(True)
        await v.talk_button(False)
        await asyncio.gather(*list(v._tasks), return_exceptions=True)
        assert len(ctx.said) < 4                                           # stopped halfway
    asyncio.run(scenario())


def test_a_story_stops_when_the_language_changes(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        ctx.play_s = 0.2
        v = ctx.voice
        task = v._spawn(v.execute(Intent("story", {"names": ["Marco"]})))
        for _ in range(30):
            await asyncio.sleep(0.01)
        told = len(ctx.said)
        await ctx.actions.set_language("en")
        await asyncio.wait({task}, timeout=2)
        assert task.done()
        assert told < 4 and len(ctx.said) <= told + 2                      # at most the announcement after it
    asyncio.run(scenario())


# ------------------------------------------------------------------ the life of the house
def month_of(text):
    for lang in ("it", "en"):
        for i, m in enumerate(MONTHS[lang]):
            if re.search(rf"\b{m}\b", text):
                return i
    return None


def test_the_life_of_the_house_stays_the_same(ctx):
    st = ctx.voice.stories
    place(ctx, "Luca", KITCHEN)
    place(ctx, "Giulia", LIVING)
    for q_it, q_en in [("Luca ha pagato le bollette?", "Did Luca pay the bills?"),
                       ("Luca ha pagato la bolletta della luce?", "Did Luca pay the electricity bill?"),
                       ("Quando scade l'assicurazione dell'auto?", "When does the car insurance run out?"),
                       ("Chi ha fatto la spesa?", "Who did the shopping?"),
                       ("Giulia ha portato fuori la spazzatura?", "Did Giulia take out the rubbish?"),
                       ("Quando è il compleanno di Giulia?", "When is Giulia's birthday?"),
                       ("Dove va in vacanza Luca?", "Where does Luca go on holiday?"),
                       ("L'auto ha fatto il tagliando?", "Has the car had its service?")]:
        it = st.life_answer(q_it, lang="it")
        assert st.life_answer(q_it, lang="it") == it                      # asked again: the same answer
        en = st.life_answer(q_en, lang="en")
        well_formed(it + en)
        assert it[0].startswith("Sì") == en[0].startswith("Yes"), (it, en)
        assert it[0].startswith("No") == en[0].startswith("No"), (it, en)
        assert month_of(" ".join(it)) == month_of(" ".join(en)), (it, en)
        assert re.findall(r"\d+", " ".join(it).replace(" primo ", " 1 ")) == re.findall(r"\d+", " ".join(en)), (it, en)


def test_a_party_of_the_past_is_remembered(ctx):
    st = ctx.voice.stories
    place(ctx, "Marco", KITCHEN)
    it = st.life_answer("ti ricordi la festa di compleanno di giulia del 1998?", recall=True, lang="it")
    assert it[0].startswith("Certo che me la ricordo! La festa di compleanno di Giulia del 1998 si fece ")
    assert st.life_answer("ti ricordi la festa di compleanno di giulia del 1998?", recall=True, lang="it") == it
    en = st.life_answer("do you remember giulia's birthday party in 1998?", recall=True, lang="en")
    assert en[0].startswith("Of course I remember! Giulia's birthday party in 1998 was ")
    rooms = {"in giardino": "in the garden", "in soggiorno": "in the living room", "in cucina": "in the kitchen"}
    assert rooms[it[0].split(" si fece ")[1].rstrip(".")] == en[0].split(" was ")[1].rstrip(".")
    well_formed(it + en)
    xmas = st.life_answer("ti ricordi la festa di natale del 2005?", recall=True, lang="it")
    assert "La festa di Natale del 2005" in xmas[0]


def test_other_free_questions(ctx):
    st = ctx.voice.stories
    place(ctx, "Marco", KITCHEN)
    place(ctx, "Fido", GARDEN, "dog")
    for lang, questions in {"it": ["hai dato da mangiare al cane?", "ti ricordi quando marco è caduto dalla bici?",
                                   "marco è simpatico?", "chi ha vinto i mondiali?", "le bollette sono pagate?"],
                            "en": ["did you feed the dog?", "do you remember when marco fell off his bike?",
                                   "is marco nice?", "who won the world cup?", "are the bills paid?"]}.items():
        for q in questions:
            lines = st.life_answer(q, recall="ricord" in q or "remember" in q, lang=lang)
            assert lines
            well_formed(lines)
    assert "Fido" in st.life_answer("hai dato da mangiare al cane?", lang="it")[0]
    assert st.life_answer("chi ha vinto i mondiali?", lang="it")[0] in [u["it"] for u in st.db["unknown"]]


def test_free_questions_by_voice(ctx):
    async def scenario():
        place(ctx, "Luca", KITCHEN)
        await ctx.voice.handle("ti ricordi la festa di compleanno di giulia del 1998")
        assert any("Giulia del 1998" in s for s in ctx.said)
        ctx.said.clear()
        await ctx.voice.handle("quando scade l'assicurazione dell'auto")
        assert ctx.said and ctx.said[-1].startswith("L'assicurazione dell'auto scade ")
        # never to the model of the commands, which took it for "where is Luca"
        asked = []

        class Llm:
            async def understand(self, text, names):
                asked.append(text)
                return Intent("where_is", {"name": "Luca"}, 0.9, "llm")
        ctx.voice.llm = Llm()
        ctx.said.clear()
        await ctx.voice.handle("luca ha pagato le bollette")
        assert not asked and ctx.said[-1].startswith(("Sì, Luca", "Non ancora", "Non tutte"))
    asyncio.run(scenario())


# ------------------------------------------------------------------ chatty mode
def test_chatty_lines_are_well_formed(ctx):
    st = ctx.voice.stories
    marco = place(ctx, "Marco", KITCHEN)
    fido = place(ctx, "Fido", GARDEN, "dog")
    for lang in ("it", "en"):
        for _ in range(60):
            for ident in (marco, fido):
                for kind in st.chat_ready(ident.id):
                    lines, reply = st.chat_lines(ident, kind, lang)
                    well_formed(lines + ([reply["yes"], reply["no"]] if reply else []))
                    assert ident.name in " ".join(lines)


def test_a_chatty_question_is_answered_and_remembered(ctx):
    async def scenario():
        from domotiq.voice import chatter as chatter_mod
        chatter_mod.ECHO_S = 0.0
        st = ctx.voice.stories
        st.db["chat_questions"] = [q for q in st.db["chat_questions"] if q["topic"] == "bill"]
        marco = place(ctx, "Marco", KITCHEN)
        ctx.settings.set("voice.verbosity", "chatty")
        ctx.voice.listener = SimpleNamespace(ok=True)
        ctx.voice.mic.device = "test"
        answers = iter(["sì"])

        async def listen(grammar, *, stop=None, max_s=5.0, auto_end=True, **_):
            text = next(answers, "")
            return text, 1.0, b"x" if text else b""

        async def recognize(audio, grammar):
            return "sì", 1.0
        ctx.voice._listen, ctx.voice._recognize = listen, recognize
        await ctx.voice.chatter._ask(marco.id, {"id": "gen-question", "kind": "generated", "gen": "question"})
        m = re.match(r"Marco, hai pagato la bolletta (della luce|del gas|dell'acqua|di internet)\?", ctx.said[0])
        assert m
        assert ctx.said[1] == "Perfetto, una cosa in meno a cui pensare!"
        # now the house knows it
        assert st.life_answer(f"Marco ha pagato la bolletta {m.group(1)}?", lang="it")[0].startswith("Sì, Marco ha pagato")
        ev = ctx.store.events(types=["chatter"])[0]["data"]
        assert ev["question"] == "gen-question" and ev["outcome"] == "answered" and "heard" not in ev
    asyncio.run(scenario())


# ------------------------------------------------------------------ memories of the day
def test_what_a_character_did_today(ctx):
    marco = ctx.identities.add("Marco", "person")
    t0 = time.time() - 1800
    rows = [(t0 + s, "v1", marco.id, 80, 100, "kitchen") for s in range(0, 600, 5)]
    rows += [(t0 + 600 + s, "v1", marco.id, 300, 100, "living") for s in range(0, 300, 5)]
    rows += [(t0 + 900 + s, "v1", marco.id, 500, 100, "bedroom") for s in range(0, 100, 5)]
    ctx.store.add_positions(rows)
    ctx.store.add_event("party", {"state": "started"}, ts=t0 + 700)
    ctx.clock.source = "settings"                  # the house knows the time: "today" starts at midnight
    text = memory.day_of(ctx, "Marco", "it", now=t0 + 1000)
    assert "per la prima volta" in text and "Ha passato più tempo in cucina" in text
    assert "poi in soggiorno e in camera" in text and "una festa" in text
    en = memory.day_of(ctx, "Marco", "en", now=t0 + 1000)
    assert "spent most of the time in the kitchen" in en and "a party" in en
    assert "Marco" in memory.room_day(ctx, "kitchen", "it", now=t0 + 1000)
    assert "una festa" in memory.parties_today(ctx, "it", now=t0 + 1000)
    assert memory.day_of(ctx, "Nessuno", "it").startswith("Non conosco")


def test_a_question_that_goes_on_from_the_house_question(ctx, monkeypatch):
    """"Viola, lo sai che manca poco al tuo compleanno?" - "Quando?": the birthday, not "interesting"."""
    async def scenario():
        viola = place(ctx, "Viola", KITCHEN)
        st = ctx.voice.stories
        replies = {}
        for topic, answer, expected in (("birthday", "Quando?", "Il compleanno di Viola è "),
                                        ("holiday", "e dove?", "Viola "),
                                        ("birthday", "che ore sono", None),
                                        ("birthday", "boh, vedremo", "Ah, interessante!")):
            q = next(q for q in st.db["chat_questions"] if q["topic"] == topic)
            monkeypatch.setattr(st, "_choose", lambda pool, used=None, q=q, **kw: q)
            lines, reply = st.chat_lines(viola, "question")
            replies[topic] = reply
            st._pending_reply[viola.id] = reply
            before = len(ctx.said)
            await st.chat_reply(viola, lines[0], answer)
            said = ctx.said[before:]
            if expected is None:                                   # a question for the house: answered as such
                assert said and "compleanno" not in said[-1] and not said[-1].startswith("Ah, interessante")
            else:
                assert said[-1].startswith(expected), (answer, said)
            if answer == "Quando?":
                date = said[-1][len(expected):-1]
        assert replies["birthday"]["no"].startswith(f"È {date}:")      # the same date the house keeps
    asyncio.run(scenario())
