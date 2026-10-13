# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the house does not know it asks, and learns: about a character, about the world, and what it imagines
about itself (voice/knowledge.py)."""

from __future__ import annotations

import asyncio

from domotiq.voice import knowledge
from domotiq.voice import variants as V
from test_facts import hear, place
from test_offers import KITCHEN, ctx  # noqa: F401 - the fixture


def test_what_the_house_does_not_know_about_a_character_it_asks_and_keeps(ctx):
    """What the house does not know about a character it asks aloud, keeps the answer, and gives it again to the
    same question in other words."""
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN, ["fa il medico"])
        hear(ctx, ["le piace il gelato"])
        await ctx.voice.handle("cosa ama Marco")
        assert any(ask in ctx.said[-2] for ask, _ in V.TEACH_ASK)     # it does not know, and asks
        assert ctx.said[-1] in ("Grazie! Me lo segno: Marco ama il gelato.", "Bene, adesso lo so: Marco ama il gelato.")
        assert ctx.identities.get(marco.id).facts == ["fa il medico", "ama il gelato"]
        # the same question in other words: the same answer
        for q in ("cosa piace a Marco", "cosa ama Marco"):
            await ctx.voice.handle(q)
            assert ctx.said[-1].endswith("Marco ama il gelato."), q
    asyncio.run(scenario())


def test_nobody_knows_and_nothing_is_kept(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN, ["fa il medico"])
        hear(ctx, ["boh non lo so"])
        await ctx.voice.handle("che musica ascolta Marco")
        assert ctx.said[-1] in [it for it, _ in V.TEACH_NOBODY]
        assert ctx.identities.get(marco.id).facts == ["fa il medico"]
        hear(ctx, ["accendi la luce in cucina"])                # not an answer: done, not kept
        await ctx.voice.handle("che sport fa Marco")
        assert ctx.said[-1] == "Fatto." and ctx.identities.get(marco.id).facts == ["fa il medico"]
    asyncio.run(scenario())


def test_an_answer_with_no_place_among_the_facts_is_kept_as_it_was_said(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN, ["fa il medico"])
        hear(ctx, ["sì"])
        await ctx.voice.handle("Marco ha la patente?")
        await ctx.voice.handle("Marco ha la patente?")
        assert ctx.said[-1] == "Mi hanno detto di sì."
    asyncio.run(scenario())


def test_about_the_world_it_asks_and_answers_the_next_question_alike(ctx):
    async def scenario():
        hear(ctx, ["domani piove"])
        await ctx.voice.handle("che tempo farà domani")
        assert any(ask in ctx.said[-2] for ask, _ in V.TEACH_ASK)
        await ctx.voice.handle("che tempo fa domani")
        assert ctx.said[-1] == "Mi hanno detto che domani piove."
        await ctx.voice.handle("domani piove")                 # two words, but the house was told about it
        assert ctx.said[-1] == "Mi hanno detto che domani piove."
    asyncio.run(scenario())


def test_about_itself_it_imagines_and_says_it_is_what_it_thinks(ctx):
    async def scenario():
        await ctx.voice.handle("perché la cucina è gialla")
        first = ctx.said[-1]
        assert first.startswith("Penso")
        await ctx.voice.handle("perché la cucina è gialla")    # the same answer every time
        assert ctx.said[-1] == first
    asyncio.run(scenario())


def test_a_question_heard_without_its_subject_finds_it_in_an_alternative(ctx):
    """A question heard without its subject finds it in the next likeliest sentence of the recognizer."""
    async def scenario():
        place(ctx, "Rossellina", KITCHEN, ["ama ballare", "fa la maestra"])
        await ctx.voice.handle("cosa ma rossellino", alternatives=["cosa ama rossellina"])
        assert ctx.said[-1].endswith("Rossellina ama ballare.")
    asyncio.run(scenario())


def test_knowledge_matches_alike_questions_and_forgets_tomorrow(tmp_path):
    k = knowledge.Knowledge(tmp_path / "k.json")
    k.learn("che tempo farà domani", "domani piove", now=1000.0)
    assert k.find("domani piove?", now=2000.0)["a"] == "domani piove"     # the weather, said otherwise
    assert k.find("che tempo fa domani", now=1000.0 + 25 * 3600) is None    # a day later it is not true any more
    k.learn("chi ha dipinto la cucina", "Viola", now=1000.0)
    assert k.find("chi ha dipinto la cucina?", now=1001.0)["a"] == "Viola"
    assert k.find("chi ha costruito il garage", now=1001.0) is None
    assert knowledge.Knowledge(tmp_path / "k.json").find("chi ha dipinto la cucina", now=1001.0)["a"] == "Viola"


# ------------------------------------------------------------------ a question about the world: think, or be told
PIZZA = "Si impasta farina, acqua e lievito. Poi si stende e si cuoce in forno."


def said_back(line, options, q, a):
    """The line is one of the options, with this question and answer said back."""
    return line in [V.fill((it, en), q=q, a=a)[0] for it, en in options]


class _Chat:
    """The free answers model, with its answer already written."""
    ready = True

    def __init__(self, text=PIZZA):
        self.text, self.asked = text, []

    async def answer(self, question, lang):
        self.asked.append(question)
        return self.text


def test_waiting_for_the_free_answer_and_asked_again(ctx):
    """A question about the world is not taken for one about a character ("Di chi?"): the house offers to think,
    waits for the free answer, and the next time answers at once."""
    async def scenario():
        chat = ctx.voice.chat = _Chat()
        hear(ctx, ["aspetto"])
        await ctx.voice.handle("come si fa la pizza")
        assert any(offer in " ".join(ctx.said) for offer, _ in V.THINK_OFFER)
        assert "Di chi?" not in ctx.said
        assert any(wait in ctx.said for wait, _ in V.THINK_WAIT)
        assert ctx.said[-1].endswith(PIZZA) and chat.asked == ["come si fa la pizza"]
        await ctx.voice.handle("come si fa la pizza")          # again: at once, from what it thought
        assert ctx.said[-1] == PIZZA and chat.asked == ["come si fa la pizza"]
    asyncio.run(scenario())


def test_silence_is_waiting(ctx):
    async def scenario():
        chat = ctx.voice.chat = _Chat()
        hear(ctx, [""])
        await ctx.voice.handle("perché il cielo è azzurro di giorno")
        assert ctx.said[-1].endswith(PIZZA) and chat.asked
    asyncio.run(scenario())


def test_told_by_the_visitor_instead(ctx):
    async def scenario():
        chat = ctx.voice.chat = _Chat()
        hear(ctx, ["te lo dico io", "si impasta e si cuoce nel forno a legna"])
        await ctx.voice.handle("come si fa la pizza")
        assert any(t in ctx.said for t, _ in V.THINK_TELL)
        assert said_back(ctx.said[-1], V.TEACH_KEPT, "come si fa la pizza", "si impasta e si cuoce nel forno a legna")
        assert chat.asked == []
        await ctx.voice.handle("come si fa la pizza")
        assert ctx.said[-1] == "Mi hanno detto che si impasta e si cuoce nel forno a legna."
        hear(ctx, ["con farina acqua e lievito poi nel forno"])     # the answer at once, no "te lo dico io"
        await ctx.voice.handle("come si fa il pane")
        assert said_back(ctx.said[-1], V.TEACH_KEPT, "come si fa il pane", "con farina acqua e lievito poi nel forno")
        assert chat.asked == []
    asyncio.run(scenario())


def test_never_mind_and_a_command_instead(ctx):
    async def scenario():
        chat = ctx.voice.chat = _Chat()
        hear(ctx, ["lascia stare"])
        await ctx.voice.handle("come si fa la pizza")
        assert ctx.said[-1] in [t for t, _ in V.THINK_DROP] and chat.asked == []
        hear(ctx, ["accendi la luce in cucina"])
        await ctx.voice.handle("come si fa la pizza")
        assert ctx.said[-1] == "Fatto." and chat.asked == []
    asyncio.run(scenario())


def test_who_are_you_also_as_heard_otherwise():
    from domotiq.voice.intents import parse
    for heard in ("chi sei", "ci sei", "chi se", "ci sei tu"):
        assert parse(heard, []).name == "who_are_you", heard


def test_a_free_answer_is_tidied_before_it_is_said():
    from domotiq.voice.llm import tidy
    cut = tidy("La pizza si fa con farina e acqua. Poi si cuoce. Dopo aver messo la base aggiungi gli ingredienti prima di")
    assert cut == "La pizza si fa con farina e acqua. Poi si cuoce."            # no sentence cut in the middle
    assert tidy("**Ecco** una curiosità 😊 sugli elefanti: sono grandi.") == "Ecco una curiosità sugli elefanti: sono grandi."
    assert tidy("<think>hmm</think>Parigi.") == "Parigi." and tidy("ciao") is None


# ------------------------------------------------------------------ what somebody tells wins
WRONG_PIZZA = "C'è un po' di tempo per preparare le uova."
RIGHT_PIZZA = "per fare la pizza ci vuole acqua farina lievito e sale"


def test_what_somebody_tells_takes_the_place_of_what_the_house_thought(tmp_path):
    k = knowledge.Knowledge(tmp_path / "k.json")
    k.learn("come si fa la pizza", WRONG_PIZZA, generated=True, now=1000.0)
    k.learn("come si fa la pizza", RIGHT_PIZZA, now=1001.0)
    assert [i["a"] for i in k.items] == [RIGHT_PIZZA]
    k.learn("come si fa la pizza", WRONG_PIZZA, generated=True, now=1002.0)   # thought again: it does not win
    assert k.find("la pizza come si fa", now=1003.0)["a"] == RIGHT_PIZZA
    assert k.find("dove si compra la pizza", now=1003.0) is None            # not the same question
    assert knowledge._stems("scusa ma rossellino", ["Rossellina"]) == {"scusa"}  # a name heard wrong is no subject


def test_a_word_or_two_do_not_repeat_what_the_house_thought(ctx):
    """After a question the free model answered, a word or two of it ("la pizza", "pizza") do not repeat that answer."""
    async def scenario():
        ctx.voice.chat = _Chat(WRONG_PIZZA)
        hear(ctx, ["aspetto"])
        await ctx.voice.handle("come si fa la pizza")
        for heard in ("la pizza", "pizza"):
            await ctx.voice.handle(heard)
            assert WRONG_PIZZA not in ctx.said[-1], heard
    asyncio.run(scenario())


def test_te_lo_dico_io_with_the_question_corrects_what_it_thought(ctx):
    """"Lo dico io" with the question corrects what the house thought: no new question, and one answer kept."""
    async def scenario():
        chat = ctx.voice.chat = _Chat(WRONG_PIZZA)
        hear(ctx, ["aspetto"])
        await ctx.voice.handle("come si fa la pizza")
        await ctx.voice.handle("accendi la luce in cucina")      # something else in between
        hear(ctx, [RIGHT_PIZZA])
        await ctx.voice.handle("lo dico io come si fa la pizza")
        assert ctx.said[-2] in [t for t, _ in V.TEACH_GO]
        assert said_back(ctx.said[-1], V.TEACH_FIXED, "come si fa la pizza", RIGHT_PIZZA)
        await ctx.voice.handle("come si fa la pizza")
        assert ctx.said[-1] == f"Mi hanno detto che {RIGHT_PIZZA}."
        assert len(ctx.voice.knowledge.items) == 1 and chat.asked == ["come si fa la pizza"]
    asyncio.run(scenario())


def test_wrong_right_after_an_answer_asks_for_the_right_one(ctx):
    async def scenario():
        ctx.voice.chat = _Chat(WRONG_PIZZA)
        hear(ctx, ["aspetto"])
        await ctx.voice.handle("come si fa la pizza")
        hear(ctx, [RIGHT_PIZZA])
        await ctx.voice.handle("sbagliato")
        assert ctx.said[-2] in [t for t, _ in V.TEACH_RIGHT]
        assert said_back(ctx.said[-1], V.TEACH_FIXED, "come si fa la pizza", RIGHT_PIZZA)
        # the right answer in the same sentence, a word heard wrong corrected at once
        await ctx.voice.handle("non è vero, ci vuole acqua farina lievito sale e olio")
        assert said_back(ctx.said[-1], V.TEACH_FIXED, "come si fa la pizza", "ci vuole acqua farina lievito sale e olio")
        await ctx.voice.handle("come si fa la pizza")
        assert ctx.said[-1] == "Mi hanno detto che ci vuole acqua farina lievito sale e olio."
    asyncio.run(scenario())


def test_a_lesson_with_nothing_to_correct(ctx):
    async def scenario():
        await ctx.voice.handle("sbagliato")                     # no answer to correct: no lesson
        assert not any(ctx.said[-1] == t for t, _ in V.TEACH_RIGHT + V.TEACH_WHICH)
        await ctx.voice.handle("te lo dico io")
        assert ctx.said[-1] in [t for t, _ in V.TEACH_WHICH]
        ctx.voice.chat = _Chat(WRONG_PIZZA)
        hear(ctx, ["aspetto"])
        await ctx.voice.handle("come si fa la pizza")
        ctx.voice._last_answer["at"] -= 600                     # minutes later "sbagliato" is about something else
        await ctx.voice.handle("sbagliato")
        assert not any(ctx.said[-1] == t for t, _ in V.TEACH_RIGHT)
    asyncio.run(scenario())
