# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the house knows about its characters: the answers of chatty mode kept as facts, and the questions
about them answered from the facts (keywords first, then the language model, mocked here)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from domotiq.app import build, parse_args
from domotiq.voice import chatter as chatter_mod
from domotiq.voice import facts as F
from domotiq.voice.chatter import QUESTIONS
from domotiq.voice.intents import COLORS, Intent, parse
from domotiq.voice.stories import fact_lang

KITCHEN, LIVING = (80, 100), (300, 100)
NAMES = ["Rossellina", "Marco", "Viola", "Mister Brown", "Fido"]


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(chatter_mod, "ECHO_S", 0.0)
    from domotiq.voice import manager, variants
    monkeypatch.setattr(manager, "TAG_DELAY_S", 0.0)
    monkeypatch.setattr(variants.VARIETY, "pick", lambda key, options: options[0])   # the first way of saying it
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera", "--no-llm"]))
    from domotiq.voice.manager import Voice
    c.voice = Voice(c)
    c.voice.listener = SimpleNamespace(ok=True)      # as if the speech model and the microphone were there
    c.voice.mic.device = "test"
    c.said = []
    c.bus.subscribe("say", lambda ev: c.said.append(ev.get("text")))
    c.voices = []                                    # (sentence, language of the voice) as synthesized
    v = c.voice

    async def speak(*args, **kwargs):                # like the real one, without Piper
        v.in_flight += 1
        await asyncio.sleep(0)
        v.in_flight -= 1
        v.voice_end = time.monotonic()

    async def synth(text, lang):
        c.voices.append((text, lang))
        return [0.0] * 10

    async def play(samples):
        await asyncio.sleep(0)
    v.speak, v.speaker.synth, v.play = speak, synth, play
    yield c
    c.store.close()


def hear(ctx, answers, confidence=1.0):
    """The microphone hears these answers, one per listen."""
    queue = list(answers)
    last = {"text": ""}

    async def listen(grammar_words, *, stop=None, max_s=5.0, auto_end=True, **_):
        item = queue.pop(0) if queue else ""
        if callable(item):
            item = await item(stop)
        last["text"] = item
        return item, confidence if item else 0.0, b"x" if item else b""

    async def recognize(audio, grammar_words):
        return last["text"], confidence if last["text"] else 0.0
    ctx.voice._listen, ctx.voice._recognize = listen, recognize


def place(ctx, name, where, facts=None, category="person"):
    ident = ctx.identities.add(name, category)
    if facts:
        ctx.identities.update(ident.id, facts=facts)
    ctx.sim.add(*where, category, ident.id, "#e03030", name)
    ctx.house.update_tracks(ctx.sim.tracks(), time.time())
    return ctx.identities.get(ident.id)


def question(qid):
    return next(q for q in QUESTIONS if q["id"] == qid)


class Model:
    """The language model: a topic for the sentences it is given, "other" for the rest."""

    def __init__(self, topics=None, command=None):
        self.topics = topics or {}
        self.command = command
        self.asked: list[str] = []
        self.understood: list[str] = []

    async def topic(self, sentence, least=F.MIN_CONFIDENCE):
        self.asked.append(sentence)
        return self.topics.get(sentence, "other")

    async def understand(self, sentence, names):
        self.understood.append(sentence)
        return self.command


def with_model(ctx, model):
    ctx.voice.llm = model
    ctx.voice.llm_ready = True
    return model


# ------------------------------------------------------------------ answers that become facts
GENDERED = {"nato", "nata", "contento", "contenta", "matto", "matta", "pazzo", "pazza", "goloso", "golosa",
            "he", "she", "his", "her", "him"}


OPEN_VALUES = {"k-dish": ("la pizza", "pizza"), "a-from": ("da Torino", "Torino")}


def all_lines():
    for qid, spec in F.ANSWER_FACTS.items():
        pairs = [tuple(t.replace("{v}", OPEN_VALUES[qid][i]) for i, t in enumerate(spec["open"]))] \
            if "open" in spec else []
        pairs += spec.get("options", []) + list(spec.get("colour", {}).values())
        pairs += [spec[k] for k in ("yes", "no") if k in spec]
        for pair in pairs:
            yield qid, pair


def test_every_answer_fact_follows_its_question():
    for qid, spec in F.ANSWER_FACTS.items():
        q = question(qid)
        assert spec["topic"] in F.TOPIC_IDS, qid
        if "open" in spec:
            assert q["kind"] == "open", qid
        if "options" in spec:
            assert q["kind"] == "choice" and len(spec["options"]) == len(q["options"]), qid
        if "colour" in spec:
            assert q["kind"] == "color" and set(spec["colour"]) == set(COLORS), qid
        if "yes" in spec:
            assert q["kind"] == "yesno" and not q.get("action"), qid     # an offer says nothing about anybody


def test_answer_facts_read_back_in_both_languages_and_agree_with_any_name():
    for qid, (it, en) in all_lines():
        for lang, line in (("it", it), ("en", en)):
            got = F.read(line)
            assert got is not None and got[:2] == (qid, lang), line
            assert fact_lang(line) == lang, line
            assert not set(line.lower().split()) & GENDERED, line
        assert F.translated(it, "it") == it and F.translated(en, "en") == en
        assert F.translated(it, "en") == en, (it, en)
        if qid not in OPEN_VALUES:              # an open answer said in English has no Italian article to get back
            assert F.translated(en, "it") == it, (it, en)


@pytest.mark.parametrize("qid,text,lang,value", [
    ("k-dish", "la pizza", "it", "la pizza"),
    ("k-dish", "il mio piatto preferito è la pizza margherita", "it", "la pizza margherita"),
    ("k-dish", "beh direi le lasagne grazie", "it", "le lasagne"),
    ("k-dish", "mi piacciono tanto gli spaghetti", "it", "gli spaghetti"),
    ("k-dish", "pizza", "it", "pizza"),
    ("k-dish", "boh", "it", None), ("k-dish", "non lo so", "it", None), ("k-dish", "niente", "it", None),
    ("k-dish", "allora la pizza che faceva sempre mia nonna la domenica a pranzo", "it", None),   # too long
    ("k-dish", "my favourite dish is fish and chips", "en", "fish and chips"),
    ("k-dish", "i love sushi", "en", "sushi"), ("k-dish", "i don't know", "en", None),
    ("a-from", "vengo da torino", "it", "da Torino"), ("a-from", "sono di napoli", "it", "da Napoli"),
    ("a-from", "sono nata a reggio emilia", "it", "da Reggio Emilia"),
    ("a-from", "dalla francia", "it", "dalla Francia"), ("a-from", "milano", "it", "da Milano"),
    ("a-from", "vengo dall'inghilterra", "it", "dall'Inghilterra"),
    ("a-from", "i'm from new york", "en", "New York"), ("a-from", "london", "en", "London"),
    # about the speaker, not a dish or a place: no fact
    ("a-from", "sono italiana", "it", None), ("a-from", "sono torinese", "it", None),
    ("a-from", "mi chiamo Giulia", "it", None), ("a-from", "i'm italian", "en", None),
    ("a-from", "sono di Varese", "it", "da Varese"),
    ("k-dish", "sono vegetariano", "it", None), ("k-dish", "sono allergico al glutine", "it", None),
    ("k-dish", "i don't eat meat", "en", None), ("k-dish", "i hate vegetables", "en", None),
    ("k-dish", "a me piace la pizza", "it", "la pizza"), ("k-dish", "hmm la carbonara", "it", "la carbonara"),
])
def test_the_value_of_an_open_answer(qid, text, lang, value):
    assert F.answer_value(qid, text, lang) == value


def test_which_answers_become_facts():
    assert F.answer_line("k-dish", "answered", "la pizza", "it") == "adora mangiare la pizza"
    assert F.answer_line("k-dish", "answered", "sushi", "en") == "loves eating sushi"
    assert F.answer_line("a-from", "answered", "vengo da torino", "it") == "viene da Torino"
    assert F.answer_line("k-cook", "option 1", "la pasta", "it") == "preferisce la pasta alla pizza"
    assert F.answer_line("a-colour", "colour blue", "blu", "it") == "ha come colore preferito il blu"
    assert F.answer_line("a-colour", "colour purple", "purple", "en") == "loves the colour purple"
    assert F.answer_line("a-house", "no", "no", "en") == "is not too fond of this house"
    assert F.answer_line("k-hungry", "yes", "sì", "it") is None          # a passing state
    assert F.answer_line("l-music", "yes", "sì", "it") is None           # an offer
    assert F.answer_line("k-dish", "none", "", "it") is None
    assert F.answer_line("k-cook", "unclear", "il sushi", "it") is None


def test_answers_in_the_other_language():
    assert F.translated("adora mangiare la pizza", "en") == "loves eating pizza"
    assert F.translated("loves eating fish and chips", "it") == "adora mangiare fish and chips"
    assert F.translated("viene dalla Francia", "en") == "comes from Francia"
    assert F.translated("comes from London", "it") == "viene da London"
    assert F.translated("è più da sera che da mattina", "en") == "is more of an evening person"
    assert F.translated("ama il jazz", "en") is None                     # typed: it stays as it was written
    assert F.read("viene spesso a trovarci") is None                     # not where somebody comes from
    assert fact_lang("comes from London") == "en" and fact_lang("viene da Torino") == "it"


def test_a_new_answer_takes_the_place_of_the_old_one_never_of_a_typed_line():
    assert F.put(["fa la maestra", "adora mangiare la pizza"], "k-dish", "loves eating sushi", 8) == \
        ["fa la maestra", "loves eating sushi"]
    typed = [f"fatto numero {i}" for i in range(6)]
    full = typed[:3] + ["viene da Torino"] + typed[3:] + ["preferisce il divano alla poltrona"]
    assert F.put(full, "k-dish", "adora mangiare la pizza", 8) == \
        typed + ["preferisce il divano alla poltrona", "adora mangiare la pizza"]
    assert F.put([f"fatto numero {i}" for i in range(8)], "k-dish", "adora mangiare la pizza", 8) is None


def test_a_typed_line_shaped_like_an_answer_stays_as_it_is():
    typed = ["viene da una famiglia di musicisti", "comes from a family of farmers"]
    assert [F.read(t) for t in typed] == [None, None] and F.translated(typed[0], "en") is None
    assert F.put(typed + ["fa il medico"], "a-from", "viene da Torino", 8) == typed + ["fa il medico", "viene da Torino"]


# ------------------------------------------------------------------ what a question is about
@pytest.mark.parametrize("text,topic", [
    ("Cosa mangia Rossellina?", "food"), ("Qual è il pranzo preferito da Rossellina?", "food"),
    ("Cosa posso cucinare a Rossellina?", "food"), ("What does Rossellina like to eat?", "food"),
    ("Cosa mangia Marco la sera?", "food"), ("Di dove è Rossellina?", "origin"), ("Where is Marco from?", "origin"),
    ("Rossellina è torinese?", "origin"), ("Che lavoro fa Marco?", "job"), ("Is Marco a doctor?", "job"),
    ("Marco fa il dottore?", "job"), ("Che musica piace a Marco?", "music"),
    ("Viola ha paura dei ragni?", "fear"),                         # Viola is a name, not a colour, here
    ("Is Viola an early riser?", "sleep"), ("Cosa piace a Marco?", F.LIKES),
    ("Would Rossellina run from a spider?", None), ("Dov'è Marco?", None), ("Marco è in giardino?", None),
    # where somebody is now, not where it likes to sit
    ("Where is Marco sitting?", None), ("Marco è sul divano?", None), ("Is Marco on the sofa?", None),
    ("Marco preferisce il divano?", "seat"), ("Dove si siede di solito Marco?", "seat"),
])
def test_what_a_question_is_about(text, topic):
    assert F.question_topic(text, NAMES) == topic


@pytest.mark.parametrize("text,intent,args", [
    ("Cosa mangia Rossellina?", "ask_fact", {"name": "Rossellina", "topic": "food"}),     # not "where is"
    ("Che musica piace a Marco?", "ask_fact", {"name": "Marco", "topic": "music"}),       # not a party
    ("Qual è il film preferito di Marco?", "ask_fact", {"name": "Marco", "topic": F.LIKES}),   # not the cinema
    ("a che ora si sveglia Marco", "ask_fact", {"name": "Marco", "topic": "sleep"}),     # not the time
    ("dov'è nata Rossellina", "ask_fact", {"name": "Rossellina", "topic": "origin"}),
    ("Quanti anni ha Marco?", "ask_fact", {"name": "Marco", "topic": "age"}),           # not a head count
    ("Dove va in vacanza Marco?", "ask_fact", {"name": "Marco", "topic": "travel"}),
    ("dov'è Marco", "where_is", {"name": "Marco"}), ("Marco", "where_is", {"name": "Marco"}),
    ("cosa sai di Marco", "about", {"name": "Marco"}),
    ("ricorda che Marco adora la pizza", "fact", {"name": "Marco"}),
    ("accendi la luce preferita di Marco", "lights_fav", {"name": "Marco"}), ("che ore sono", "time_now", {}),
    ("facciamo festa", "party", {}), ("parla inglese con Marco", "language", {"language": "en"}),
    # a request that names a character is still a request
    ("Marco vuole sentire la musica", "party", {}), ("musica per Marco", "party", {}),
    ("puoi mettere la musica preferita di Marco", "party", {}), ("Marco ama la musica, facciamo festa", "party", {}),
    ("Marco is hungry, light the barbecue", "grill", {}), ("Where is Marco sitting?", "where_is", {"name": "Marco"}),
    ("cosa vuole ascoltare Marco", "ask_fact", {"name": "Marco", "topic": "music"}),
])
def test_questions_about_a_character_are_told_from_commands(text, intent, args):
    got = parse(text, NAMES)
    assert got is not None and got.name == intent, (text, got)
    assert args.items() <= got.args.items(), (text, got.args)


def test_the_topic_of_a_fact_is_not_told_by_a_name_or_a_lookalike_word():
    names = NAMES + ["Bianca", "Celeste"]
    assert F.select("colour", ["fa il medico", "vive con Bianca", "va d'accordo con Celeste"], names=names) == []
    assert F.select("origin", ["adora la cucina italiana e viene spesso a trovarci"], names=names) == []
    assert F.select("origin", ["viene da Bari", "è napoletano"], names=names) == [1, 0]
    assert F.select("family", ["ha un grande cuore"], names=names) == []
    assert F.select("family", ["has two grandchildren"], names=names) == [0]
    facts = ["fa il tifo per la Juve", "fa la torta per tutti", "è un amante della musica", "is a vegetarian",
             "is a heavy sleeper", "fa il medico"]
    assert F.select("job", facts, names=names, most=9) == [5]


def test_the_life_of_the_house_keeps_its_own_questions():
    assert parse("Marco ha pagato le bollette?", NAMES) is None           # stories.py answers it
    assert parse("Marco ha lavato i piatti?", NAMES) is None


# ------------------------------------------------------------------ chatty mode keeps the answers
def test_a_chatty_answer_becomes_a_fact_and_a_new_one_replaces_it(ctx):
    async def scenario():
        ros = place(ctx, "Rossellina", KITCHEN, ["fa la maestra"])
        ctx.settings.set("voice.verbosity", "chatty")
        hear(ctx, ["la pizza"])
        await ctx.voice.chatter._ask(ros.id, question("k-dish"))
        assert ctx.identities.get(ros.id).facts == ["fa la maestra", "adora mangiare la pizza"]
        assert ctx.said[-1] == "Me lo segno: Rossellina adora mangiare la pizza."
        ev = ctx.store.events(types=["chatter"])[0]["data"]
        assert ev["outcome"] == "answered" and "pizza" not in str(ev)       # the log keeps the outcome only
        shown = next(i for i in ctx.identities.to_list() if i["id"] == ros.id)
        assert "adora mangiare la pizza" in shown["facts"]                  # what the web app shows
        hear(ctx, ["le lasagne"])
        ctx.voice.chatter.recent.clear()
        await ctx.voice.chatter._ask(ros.id, question("k-dish"))
        assert ctx.identities.get(ros.id).facts == ["fa la maestra", "adora mangiare le lasagne"]
        await ctx.actions.set_language("en")
        hear(ctx, ["my favourite dish is sushi"])
        await ctx.voice.chatter._ask(ros.id, question("k-dish"))
        assert ctx.identities.get(ros.id).facts == ["fa la maestra", "loves eating sushi"]   # either language
        assert ctx.said[-1] == "I'll remember that: Rossellina loves eating sushi."
    asyncio.run(scenario())


def test_closed_answers_become_facts_in_silence(ctx):
    async def scenario():
        marco = place(ctx, "Marco", LIVING)
        ctx.settings.set("voice.verbosity", "chatty")
        hear(ctx, ["il divano"])
        await ctx.voice.chatter._ask(marco.id, question("l-sofa"))
        hear(ctx, ["il viola"])
        await ctx.voice.chatter._ask(marco.id, question("a-colour"))
        assert ctx.identities.get(marco.id).facts == ["preferisce il divano alla poltrona",
                                                      "ha come colore preferito il viola"]
        assert ctx.said[-1] == "Ecco il tuo colore, Marco!" and ctx.lights.state()["living"]["color"] == "purple"
        hear(ctx, ["boh"])
        await ctx.voice.chatter._ask(marco.id, question("a-from"))
        hear(ctx, ["sì"])
        await ctx.voice.chatter._ask(marco.id, question("l-film"))           # an offer: no fact
        assert len(ctx.identities.get(marco.id).facts) == 2
    asyncio.run(scenario())


def test_an_answer_heard_badly_or_spoken_over_is_not_kept(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        ctx.settings.set("voice.verbosity", "chatty")
        hear(ctx, ["la pizza"], confidence=0.3)
        await ctx.voice.chatter._ask(marco.id, question("k-dish"))
        assert ctx.identities.get(marco.id).facts == []

        async def rule_speaks(stop):
            await ctx.actions.say({"it": "Attenzione: il locale tecnico è riservato!", "en": "x"})
            return "pizza"
        hear(ctx, [rule_speaks])
        await ctx.voice.chatter._ask(marco.id, question("k-cook"))
        assert ctx.identities.get(marco.id).facts == []
    asyncio.run(scenario())


# ------------------------------------------------------------------ questions about a character
ROSSELLINA = ["adora mangiare la pizza", "viene da Torino", "fa la maestra"]


def test_questions_are_answered_from_the_facts(ctx):
    async def scenario():
        place(ctx, "Rossellina", KITCHEN, ROSSELLINA)
        model = with_model(ctx, Model())
        for q in ("Cosa mangia Rossellina?", "qual è il pranzo preferito da Rossellina",
                  "cosa posso cucinare a Rossellina"):
            await ctx.voice.handle(q)
            assert ctx.said[-1] == "So che Rossellina adora mangiare la pizza.", q
        await ctx.voice.handle("di dove è Rossellina")
        assert ctx.said[-1] == "So che Rossellina viene da Torino."
        await ctx.voice.handle("che musica ascolta Rossellina")
        assert ctx.said[-1] == "Non lo so: Rossellina non me l'ha ancora detto."
        assert model.asked == [] and model.understood == []        # the keywords were enough
        await ctx.actions.set_language("en")
        await ctx.voice.handle("what does Rossellina like to eat")
        assert ctx.said[-1] == "I know that Rossellina loves eating pizza."
        await ctx.voice.handle("what is Rossellina's job")
        assert ctx.said[-2:] == ["You told me in Italian:", "Rossellina fa la maestra."]
        assert ("Rossellina fa la maestra.", "it") in ctx.voices    # read by the Italian voice
    asyncio.run(scenario())


def test_without_the_model_a_question_with_no_keyword_goes_on_as_before(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN, ["fa il medico"])
        await ctx.voice.handle("Marco è medico?")
        assert ctx.said[-1] == "Marco è in cucina."                 # "a name alone is where is", as before
    asyncio.run(scenario())


def test_the_model_tells_the_topic_the_keywords_miss(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN, ["fa il medico", "ama il jazz"])
        model = with_model(ctx, Model({"Marco cura i malati?": "job", "A Marco piacciono i Beatles?": "music"},
                                      command=Intent("where_is", {"name": "Marco"}, 0.9, "llm")))
        await ctx.voice.handle("Marco cura i malati?")
        assert ctx.said[-1] == "So che Marco fa il medico." and model.understood == []
        await ctx.voice.handle("A Marco piacciono i Beatles?")      # only a word of liking: the model tells more
        assert ctx.said[-1] == "So che Marco ama il jazz."
        await ctx.voice.handle("Marco gioca con Fido?")             # nothing about it: the commands decide
        assert model.understood == ["Marco gioca con Fido?"] and ctx.said[-1] == "Marco è in cucina."
        await ctx.voice.handle("dove Marco")                         # where somebody is: no need to ask the model
        assert "dove Marco" not in model.asked and ctx.said[-1] == "Marco è in cucina."
        assert ctx.said.count("Vediamo...") == 3                    # one word while the model thinks, not two
        ctx.voice.llm_ready = False                                 # still reading its instructions after a start
        await ctx.voice.handle("Marco cura i malati?")
        assert model.asked.count("Marco cura i malati?") == 1 and ctx.said[-1] == "Marco è in cucina."
    asyncio.run(scenario())


def test_a_topic_with_no_fact_about_it_is_not_known(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN, ["ama il jazz"])
        model = with_model(ctx, Model({"Marco cura i malati?": "job", "Marco va matto per qualcosa?": "likes",
                                       "Marco è sul divano?": "seat"},
                                      command=Intent("where_is", {"name": "Marco"}, 0.9, "llm")))
        await ctx.voice.handle("Marco cura i malati?")              # no job told: not the answer to another question
        assert ctx.said[-1] in {it.replace("{name}", "Marco") for it, _ in F.UNKNOWN} and model.understood == []
        await ctx.voice.handle("Marco va matto per qualcosa?")      # the model said "likes": not asked twice
        assert ctx.said[-1] == "So che Marco ama il jazz." and model.asked.count("Marco va matto per qualcosa?") == 1
        await ctx.voice.handle("Marco è sul divano?")               # maybe where it is now: the commands decide
        assert model.understood == ["Marco è sul divano?"] and ctx.said[-1] == "Marco è in cucina."
    asyncio.run(scenario())


def test_a_fact_no_keyword_describes_gets_its_topic_from_the_model(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN, ["ha un debole per i fumetti", "fa il medico"])
        model = with_model(ctx, Model({"ha un debole per i fumetti": "hobby"}))
        await ctx.voice._tag_facts()
        assert model.asked == ["ha un debole per i fumetti"]        # the job was told by its keywords
        assert ctx.voice.fact_topics == {"ha un debole per i fumetti": "hobby"}
        await ctx.voice.handle("Marco ha un hobby?")
        assert ctx.said[-1] == "So che Marco ha un debole per i fumetti."
        await ctx.voice._tag_facts()                                # known: not asked again
        assert len(model.asked) == 1
    asyncio.run(scenario())


def test_a_change_of_the_facts_is_looked_at_and_a_learned_colour_is_not(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        model = with_model(ctx, Model({"ha un debole per i fumetti": "hobby"}))
        ctx.identities.update(marco.id, facts=["ha un debole per i fumetti"])     # typed in the web app
        await asyncio.gather(*list(ctx.voice._tasks))
        assert ctx.voice.fact_topics == {"ha un debole per i fumetti": "hobby"}
        tagging = ctx.voice._tagging
        ctx.identities.update(marco.id, signature=[0.1, 0.2, 0.3])               # the vision learning a colour
        assert ctx.voice._tagging is tagging and model.asked == ["ha un debole per i fumetti"]
    asyncio.run(scenario())


def test_the_life_of_the_house_answers_what_no_fact_tells(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN, ["fa il medico"])
        await ctx.voice.handle("Dove va in vacanza Marco?")
        assert ctx.said[-1].startswith("Marco vorrebbe andare ")      # made up by the stories, then kept
        ctx.identities.update(marco.id, facts=["fa il medico", "preferisce il mare alla montagna"])
        await ctx.voice.handle("Dove va in vacanza Marco?")
        assert ctx.said[-1] == "So che Marco preferisce il mare alla montagna."
        await ctx.voice.handle("Marco ha pagato le bollette?")
        assert ctx.said[-1].startswith(("Sì, Marco", "Non ancora", "Non tutte"))
    asyncio.run(scenario())


def test_the_stories_use_an_answer_in_both_languages(ctx):
    ros = place(ctx, "Rossellina", KITCHEN, ["adora mangiare la pizza", "ama il jazz"])
    st = ctx.voice.stories
    assert st.facts_in(ros, "en") == ["loves eating pizza"]
    assert st.facts_in(ros, "it") == ["adora mangiare la pizza", "ama il jazz"]
    en = st.about("Rossellina", "en")
    assert en[0] == ("You told me that Rossellina loves eating pizza.", "en")
    assert en[1] == ("You also told me in Italian:", "en") and en[2] == ("Rossellina ama il jazz.", "it")
