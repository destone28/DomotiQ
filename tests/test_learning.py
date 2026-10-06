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
    """"Cosa ama Rossellina?" got "di Rossellina questo non lo so ancora", and that was all."""
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
    """"Cosa ama Rossellina" was heard "cosa ma rossellino": the second likeliest sentence had the subject."""
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
