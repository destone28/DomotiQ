# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What an answer to "who is it?" means: the rules, and the forms of the language model checked against
the sentence."""

import pytest

from domotiq.voice import who

NAMES = ["Viola", "Rosaria", "Mister Braun", "Fido"]


def said(reply):
    return None if reply is None else " ".join(x for x in (reply.kind, reply.category, reply.name) if x)


@pytest.mark.parametrize("lang,text,meaning", [
    ("it", "Paolo", "name Paolo"), ("it", "si chiama Mario Rossi", "name Mario Rossi"),
    ("it", "il suo nome è Federico", "name Federico"), ("it", "ehm si chiama tipo Gianni", "name Gianni"),
    ("it", "è Viola", "name Viola"), ("it", "no non è Viola è Rosaria", "name Rosaria"),
    ("it", "è Mister Braun", "name Mister Braun"), ("it", "sì", "yes"), ("it", "no", "no"),
    ("it", "rosario", "name Rosaria"), ("it", "mister brown", "name Mister Braun"),   # heard a letter wrong
    ("it", "è un gatto", "kind cat"), ("it", "un coniglietto", "kind animal"), ("it", "è un pupazzo", "kind object"),
    ("it", "è un cane si chiama Rex", "kind dog Rex"), ("it", "si chiama Pallino ed è un cagnolino", "kind dog Pallino"),
    ("it", "è mio fratello Andrea", "kind person Andrea"), ("it", "guarda che è un gatto nero", "kind cat"),
    ("it", "non è un cane è un gatto", "kind cat"), ("it", "ma quale persona quello è un gatto", "kind cat"),
    ("it", "non c'è nessuno in giardino", "nobody"), ("it", "è la mia mano", "nobody"),
    ("it", "è il riflesso della lampada", "nobody"), ("it", "nessuna persona", "nobody"),
    ("it", "non saprei proprio", "unknown"), ("it", "lascia perdere", "unknown"), ("it", "aspetta un attimo", "wait"),
    ("it", "nessuno di questi", "none_of"), ("it", "sei bellissima", "other"), ("it", "perché me lo chiedi", "other"),
    ("it", "che ore sono", "other"), ("it", "raccontami una storia", "other"),
    ("en", "she's called Lucy", "name Lucy"), ("en", "it's a cat named Tom", "kind cat Tom"),
    ("en", "there is nothing in the kitchen", "nobody"), ("en", "nope", "no"), ("en", "my car", "kind car"),
    ("en", "what time is it", "other"),
])
def test_short_answers_are_understood_by_the_rules(lang, text, meaning):
    assert said(who.by_rules(text, lang, NAMES)) == meaning


def test_long_or_tangled_answers_are_left_to_the_language_model():
    assert who.by_rules("allora praticamente quello che vedi è il gatto del vicino", "it", NAMES) is None
    assert who.by_rules("macché persona, è il mio cane Fido", "it", NAMES) is None
    assert who.by_rules("", "it", NAMES).kind == "silence"


@pytest.mark.parametrize("form,text,meaning", [
    ("kind person Briciola", "veramente è un cagnolino, si chiama Briciola", "kind dog Briciola"),   # read again
    ("no", "no è un uccellino", "kind animal"),
    ("kind person Fido", "macché persona, è il mio cane Fido", "kind dog Fido"),
    ("name Viola", "no non è Viola è Rosaria", "name Rosaria"),     # the name it denies is not taken
    ("name Tommy", "come ti chiami tu", "other"),                    # a name that is not in the sentence
    ("name Gatto", "ma quale persona quello è un gatto", "kind cat"),
    ("nobody", "ma guarda che lì non c'è anima viva", "nobody"),
    ("name Bellissima", "sei bellissima", "other"),
    ("nobody", "allora praticamente quello che vedi è il gatto del vicino", "kind cat"),
])
def test_the_model_only_tells_the_kind_of_answer(form, text, meaning):
    assert said(who.parse(form, text, NAMES, 0.9)) == meaning


def test_a_guess_of_the_model_is_not_acted_upon():
    assert who.parse("name Marco", "marco forse", NAMES, 0.2).kind == "other"
    assert who.parse("nonsense", "marco", NAMES, 0.9) is None


def test_the_prompt_and_grammar_are_fixed():
    # the instructions must stay the same text, so llama-server keeps them in its cache
    assert who.messages("a") [:-1] == who.messages("b")[:-1]
    assert "root ::=" in who.GRAMMAR and '"nobody"' in who.GRAMMAR
