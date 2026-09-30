# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the house remembers of the day, from what it has really seen.

"Cosa ha fatto Marco oggi?", "Chi è stato in cucina oggi?", "Quante feste
abbiamo fatto oggi?": the answers come from the positions (one a second,
kept for a day) and from the events (kept for a week), never from the
language model, so they are true. "Today" starts at midnight when the house
knows the time, otherwise when it was switched on.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from . import answers

if TYPE_CHECKING:
    from ..app import Context

SKIP = ("outside", "driveway")


def since(ctx: "Context", now: float | None = None) -> tuple[float, bool]:
    """The start of "today", and True if it is really midnight (the clock is known)."""
    now = now or time.time()
    if ctx.clock.known:
        lt = time.localtime(now)
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)), True
    return float(getattr(ctx, "started", 0.0) or now - 3600), False


def _clock(ts: float, lang: str) -> str:
    lt = time.localtime(ts)
    if lang == "it":
        if lt.tm_hour == 1:
            return f"all'una e {lt.tm_min}" if lt.tm_min else "all'una"
        return f"alle {lt.tm_hour} e {lt.tm_min}" if lt.tm_min else f"alle {lt.tm_hour}"
    return f"at {lt.tm_hour}:{lt.tm_min:02d}"


def _ago(seconds: float, lang: str) -> str:
    m = int(seconds // 60)
    if m < 1:
        return "poco fa" if lang == "it" else "just now"
    if m < 60:
        return (f"{m} minut{'o' if m == 1 else 'i'} fa" if lang == "it" else f"{m} minute{'' if m == 1 else 's'} ago")
    h = m // 60
    return (f"{h} or{'a' if h == 1 else 'e'} fa" if lang == "it" else f"{h} hour{'' if h == 1 else 's'} ago")


def _times(n: int, lang: str) -> str:
    if lang == "it":
        return {1: "una volta", 2: "due volte", 3: "tre volte"}.get(n, f"{n} volte")
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _events(ctx: "Context", kind: str, start: float, state: str = "started") -> list[float]:
    return [e["ts"] for e in ctx.store.events(limit=500, types=[kind]) if e["ts"] >= start and e["data"].get("state") == state]


def day_of(ctx: "Context", name: str, lang: str, now: float | None = None) -> str:
    """What a character did today."""
    now = now or time.time()
    ident = ctx.identities.by_name(name)
    if not ident:
        return (f"Non conosco nessuno che si chiama {name}." if lang == "it"
                else f"I don't know anyone called {name}.")
    start, midnight = since(ctx, now)
    when_it, when_en = ("oggi", "today") if midnight else ("da quando mi sono accesa", "since I was switched on")
    changes = [c for c in ctx.store.room_changes(ident.id, start) if c["room"]]
    if not changes:
        return (f"{when_it.capitalize()} non ho visto {ident.name}." if lang == "it"
                else f"I haven't seen {ident.name} {when_en}.")
    # time spent in each room, from one change to the next
    spent: dict[str, float] = {}
    visits: dict[str, int] = {}
    for i, c in enumerate(changes):
        end = changes[i + 1]["ts"] if i + 1 < len(changes) else now
        if c["room"] in SKIP:
            continue
        spent[c["room"]] = spent.get(c["room"], 0.0) + max(0.0, end - c["ts"])
        visits[c["room"]] = visits.get(c["room"], 0) + 1
    parts = []
    first = changes[0]["ts"]
    # neutral forms: the house does not know if Giulia or Marco is a she or a he
    parts.append(f"{when_it.capitalize()} ho visto {ident.name} per la prima volta {_clock(first, lang)}." if lang == "it"
                 else f"{when_en.capitalize()} I first saw {ident.name} {_clock(first, lang)}.")
    if spent:
        order = sorted(spent, key=lambda r: -spent[r])
        top = order[0]
        mins = max(1, int(spent[top] // 60))
        top_it = f"{answers.room(ctx, top, 'it')} ({mins} minut{'o' if mins == 1 else 'i'}, {_times(visits[top], 'it')})"
        top_en = f"{answers.room(ctx, top, 'en')} ({mins} minute{'' if mins == 1 else 's'}, {_times(visits[top], 'en')})"
        others = [answers.room(ctx, r, lang) for r in order[1:4]]
        if lang == "it":
            parts.append(f"Ha passato più tempo {top_it}" + (f", poi {answers.join(others, lang)}." if others else "."))
        else:
            parts.append(f"{ident.name} spent most of the time {top_en}" + (f", then {answers.join(others, lang)}." if others else "."))
    track = ctx.house.where_is(ident.id)
    if track and track.room not in (None, "outside"):
        where = answers.room(ctx, track.room, lang)
        parts.append(f"Adesso è {where}." if lang == "it" else f"{ident.name} is now {where}.")
    else:
        last = changes[-1]["ts"]
        parts.append(f"Ho visto {ident.name} l'ultima volta {_ago(now - last, lang)}." if lang == "it"
                     else f"I last saw {ident.name} {_ago(now - last, lang)}.")
    parties = len(_events(ctx, "party", first))
    grills = len(_events(ctx, "grill", first))
    extra = []
    if parties:
        extra.append({1: "una festa", 2: "due feste"}.get(parties, f"{parties} feste") if lang == "it"
                     else {1: "a party", 2: "two parties"}.get(parties, f"{parties} parties"))
    if grills:
        extra.append({1: "una grigliata"}.get(grills, f"{grills} grigliate") if lang == "it"
                     else {1: "a barbecue"}.get(grills, f"{grills} barbecues"))
    if extra:
        parts.append(f"Mentre c'era abbiamo fatto {answers.join(extra, lang)}." if lang == "it"
                     else f"While {ident.name} was here we had {answers.join(extra, lang)}.")
    return " ".join(parts)


def room_day(ctx: "Context", room: str | None, lang: str, now: float | None = None) -> str:
    """Who has been in a room today."""
    if not room:
        return ("In quale stanza?" if lang == "it" else "Which room?")
    start, midnight = since(ctx, now)
    when = ("oggi" if midnight else "da quando mi sono accesa") if lang == "it" else ("today" if midnight else "since I was switched on")
    names = [ctx.identities.name_of(i) for i in ctx.store.identities_in_room(room, start)]
    names = [n for n in names if n]
    strangers = ctx.store.strangers_in_room(room, start)
    where = answers.room(ctx, room, lang)
    if not names and not strangers:
        return (f"{when.capitalize()} {where} non è entrato nessuno." if lang == "it" else f"Nobody has been {where} {when}.")
    who = list(names)
    if strangers:
        who.append(({1: "un ospite"}.get(strangers, f"{strangers} ospiti") if lang == "it"
                    else {1: "a guest"}.get(strangers, f"{strangers} guests")))
    return (f"{when.capitalize()} {where} sono passati {answers.join(who, lang)}." if lang == "it" and len(who) > 1
            else f"{when.capitalize()} {where} è passato {who[0]}." if lang == "it"
            else f"{when.capitalize()} {answers.join(who, lang)} {'have' if len(who) > 1 else 'has'} been {where}.")


def parties_today(ctx: "Context", lang: str, now: float | None = None) -> str:
    start, midnight = since(ctx, now)
    n = len(_events(ctx, "party", start))
    g = len(_events(ctx, "grill", start))
    when = ("oggi" if midnight else "da quando mi sono accesa") if lang == "it" else ("today" if midnight else "since I was switched on")
    if lang == "it":
        feste = {0: "nessuna festa", 1: "una festa", 2: "due feste"}.get(n, f"{n} feste")
        griglie = {0: "nessuna grigliata", 1: "una grigliata"}.get(g, f"{g} grigliate")
        return f"{when.capitalize()} abbiamo fatto {feste} e {griglie}."
    parties = {0: "no parties", 1: "one party", 2: "two parties"}.get(n, f"{n} parties")
    grills = {0: "no barbecues", 1: "one barbecue"}.get(g, f"{g} barbecues")
    return f"{when.capitalize()} we had {parties} and {grills}."
