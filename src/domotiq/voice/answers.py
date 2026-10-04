# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Answers composed from the real state of the house, in Italian and English."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..model import ANIMALS, CAR, CATEGORY_NAMES, PERSON, category_matches

if TYPE_CHECKING:
    from ..app import Context

IN = {"it": "in", "en": "in the"}


def join(items: list[str], lang: str) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    word = " e " if lang == "it" else " and "
    return ", ".join(items[:-1]) + word + items[-1]


def room(ctx: "Context", room_id: str | None, lang: str) -> str:
    if not room_id or room_id == "outside":
        return "fuori casa" if lang == "it" else "outside"
    label = ctx.layout.room_label(room_id, lang)
    if lang == "it":
        return {"garage": "in garage", "garden": "in giardino", "driveway": "sul vialetto",
                "utility": "nel locale tecnico", "living": "in soggiorno", "bedroom": "in camera",
                "kitchen": "in cucina", "bathroom": "in bagno"}.get(room_id, f"in {label.lower()}")
    return {"driveway": "on the driveway", "garden": "in the garden"}.get(room_id, f"in the {label.lower()}")


def describe(ctx: "Context", track, lang: str) -> str:
    ident = ctx.identities.get(track.identity)
    if ident:
        return ident.name
    cat = track.category or "object"
    if cat == PERSON:
        return "un ospite" if lang == "it" else "a guest"
    noun = CATEGORY_NAMES.get(cat, {}).get(lang, cat)
    art = ("un" if cat in ("dog", "cat", "animal", "object") else "un'") if lang == "it" else "a"
    if lang == "it" and cat == "car":
        return "un'auto"
    return f"{art} {noun}"


def furniture(ctx: "Context", fid: str | None) -> dict[str, Any] | None:
    """The piece of furniture of the layout with this id (with its phrases "on" and "off"), or None."""
    if not fid:
        return None
    return next((f for f in ctx.layout.raw.get("furniture", []) if f.get("id") == fid and "on" in f), None)


def where_is(ctx: "Context", name: str, lang: str) -> str:
    ident = ctx.identities.by_name(name)
    if not ident:
        return (f"Non conosco nessuno che si chiama {name}." if lang == "it"
                else f"I don't know anyone called {name}.")
    track = ctx.house.where_is(ident.id)
    if not track:
        return f"Non vedo {ident.name}." if lang == "it" else f"I can't see {ident.name}."
    unsure = track.uncertain
    item = furniture(ctx, getattr(track, "on", None))
    where = item["on"][lang] if item else room(ctx, track.room, lang)
    if lang == "it":
        return f"{ident.name} è {where}." + (" Almeno credo." if unsure else "")
    return f"{ident.name} is {where}." + (" I think." if unsure else "")


def who_in(ctx: "Context", room_id: str | None, lang: str) -> str:
    if not room_id:
        return summary(ctx, lang)
    tracks = ctx.house.in_room(room_id)
    where = room(ctx, room_id, lang)
    if not tracks:
        return f"{where.capitalize()} non c'è nessuno." if lang == "it" else f"There's nobody {where}."
    names = [describe(ctx, t, lang) for t in tracks]
    if lang == "it":
        verb = "c'è" if len(names) == 1 else "ci sono"
        return f"{where.capitalize()} {verb} {join(names, lang)}."
    return f"{join(names, lang).capitalize()} {'is' if len(names) == 1 else 'are'} {where}."


def count(ctx: "Context", room_id: str | None, what: str, lang: str) -> str:
    category = "animal" if what == "animals" else PERSON
    n = ctx.house.count(room_id or "house", category)
    where = room(ctx, room_id, lang) if room_id else ("in casa" if lang == "it" else "in the house")
    if lang == "it":
        noun = ("animale" if n == 1 else "animali") if category == "animal" else ("persona" if n == 1 else "persone")
        if n == 0:
            return f"{where.capitalize()} non c'è nessun{'o' if category == PERSON else ' animale'}."
        return f"{where.capitalize()} {'c è' if n == 1 else 'ci sono'} {n} {noun}.".replace("c è", "c'è")
    noun = ("pet" if n == 1 else "pets") if category == "animal" else ("person" if n == 1 else "people")
    return f"There {'is' if n == 1 else 'are'} {n} {noun} {where}."


def temperature(ctx: "Context", room_id: str | None, lang: str) -> str:
    s = ctx.house.sensors
    if room_id == "bathroom" and s["bathroom"]["t"] is not None:
        t = s["bathroom"]["t"]
        return f"In bagno ci sono {t:.1f} gradi." if lang == "it" else f"It's {t:.1f} degrees in the bathroom."
    t = s["thermostat"]["t"]
    if t is None:
        return "Il termostato non risponde." if lang == "it" else "The thermostat is not answering."
    extra = ""
    if ctx.house.climate == "hot":
        extra = " Il climatizzatore è acceso." if lang == "it" else " The air conditioning is on."
    return (f"In soggiorno ci sono {t:.1f} gradi.{extra}" if lang == "it"
            else f"It's {t:.1f} degrees in the living room.{extra}")


def humidity(ctx: "Context", room_id: str | None, lang: str) -> str:
    s = ctx.house.sensors
    key = "thermostat" if room_id == "living" else "bathroom"
    rh = s[key]["rh"]
    if rh is None:
        return "Il sensore non risponde." if lang == "it" else "The sensor is not answering."
    where = "in soggiorno" if key == "thermostat" else "in bagno"
    if lang == "en":
        where = "in the living room" if key == "thermostat" else "in the bathroom"
    shower = ""
    if key == "bathroom" and ctx.house.shower:
        shower = " Qualcuno sta facendo la doccia!" if lang == "it" else " Someone is having a shower!"
    return (f"L'umidità {where} è al {rh:.0f} per cento.{shower}" if lang == "it"
            else f"Humidity {where} is {rh:.0f} percent.{shower}")


def time_now(ctx: "Context", lang: str) -> str:
    if not ctx.clock.known:
        return ("Non so che ore sono: me lo dici tu? Per esempio: sono le tre e mezza."
                if lang == "it" else "I don't know the time: will you tell me? For example: it's half past three.")
    lt = time.localtime()
    if lang == "it":
        if lt.tm_hour == 1:
            return f"È l'una e {lt.tm_min}." if lt.tm_min else "È l'una."
        return f"Sono le {lt.tm_hour} e {lt.tm_min}." if lt.tm_min else f"Sono le {lt.tm_hour}."
    return f"It's {lt.tm_hour}:{lt.tm_min:02d}."


def car_where(ctx: "Context", lang: str) -> str:
    cars = [t for t in ctx.house.tracks.values() if t.category == CAR]
    if not cars:
        return "L'auto non c'è." if lang == "it" else "The car is not here."
    t = cars[0]
    state = ctx.house.cars.get(t.id)
    where = room(ctx, t.room, lang)
    if state and state.state == "parked":
        return "L'auto è parcheggiata in garage." if lang == "it" else "The car is parked in the garage."
    return f"L'auto è {where}." if lang == "it" else f"The car is {where}."


def summary(ctx: "Context", lang: str) -> str:
    h = ctx.house
    people = [t for t in h.tracks.values() if t.category == PERSON and t.room not in ("outside", None)]
    pets = [t for t in h.tracks.values() if category_matches(t.category, "animal")]
    parts = []
    if people:
        where = [f"{describe(ctx, t, lang)} {room(ctx, t.room, lang)}" for t in people[:5]]
        if lang == "it":
            parts.append(f"In casa ci {'è' if len(people) == 1 else 'sono'} {len(people)} "
                         f"{'persona' if len(people) == 1 else 'persone'}: {join(where, lang)}.")
        else:
            parts.append(f"There {'is' if len(people) == 1 else 'are'} {len(people)} "
                         f"{'person' if len(people) == 1 else 'people'}: {join(where, lang)}.")
    else:
        parts.append("In casa non c'è nessuno." if lang == "it" else "Nobody is home.")
    if pets:
        names = [describe(ctx, t, lang) for t in pets[:3]]
        parts.append(f"Ci sono anche {join(names, lang)}." if lang == "it" else f"There's also {join(names, lang)}.")
    t = h.sensors["thermostat"]["t"]
    if t is not None:
        parts.append(f"Ci sono {t:.0f} gradi." if lang == "it" else f"It's {t:.0f} degrees.")
    car = h.car_state()
    if car == "parked":
        parts.append("L'auto è in garage." if lang == "it" else "The car is in the garage.")
    if h.party_on:
        parts.append("E c'è una festa!" if lang == "it" else "And there's a party!")
    if h.grill_on:
        parts.append("Il barbecue è acceso." if lang == "it" else "The barbecue is on.")
    return " ".join(parts)


def help_text(lang: str) -> str:
    if lang == "it":
        return ("Puoi chiedermi dov'è qualcuno, chi c'è in una stanza, che temperatura fa, e che ore sono. "
                "Posso accendere le luci, cambiare scenario, fare festa e accendere il barbecue.")
    return ("You can ask me where someone is, who's in a room, the temperature and the time. "
            "I can turn on the lights, change the scene, throw a party and light the barbecue.")


def who_are_you(lang: str) -> str:
    if lang == "it":
        return ("Sono DomotiQ, una casa intelligente che vive tutta dentro una Arduino UNO Q. "
                "Vedo chi c'è, accendo le luci e rispondo al citofono.")
    return ("I'm DomotiQ, a smart home that lives entirely inside an Arduino UNO Q. "
            "I see who's here, turn on the lights and answer the doorbell.")


def not_understood(lang: str) -> str:
    return ("Non ho capito. Prova a chiedermi: dov'è Marco? Oppure: fai festa!" if lang == "it"
            else "I didn't get that. Try asking: where is Marco? Or: let's party!")


JOKES = {
    "it": [
        "Sai perché la casa è sempre calma? Perché ha un ottimo termostato emotivo.",
        "Cosa dice una lampadina all'altra? Stasera mi sento particolarmente accesa!",
        "Perché il garage è sempre felice? Perché ogni sera qualcuno torna a casa.",
        "Il mio barbecue ha chiesto un aumento: dice che lavora sempre sotto pressione e a fuoco vivo.",
        "Perché il locale tecnico è vietato? Perché lì dentro le luci fanno le prove del party.",
        "Sai qual è lo sport preferito delle case intelligenti? Il salto... di stanza in stanza!",
    ],
    "en": [
        "Why is this house always calm? It has an excellent emotional thermostat.",
        "What did one light bulb say to the other? I'm feeling really bright tonight!",
        "Why is the garage always happy? Because every evening someone comes home.",
        "My barbecue asked for a raise: it says it always works under pressure and on a high flame.",
        "Why is the utility room off limits? That's where the lights rehearse for the party.",
        "What's a smart house's favourite sport? Room hopping!",
    ],
}


def joke(lang: str, n: int) -> str:
    lines = JOKES.get(lang, JOKES["en"])
    return lines[n % len(lines)]


def off_topic(lang: str) -> str:
    return ("Sono la casa: posso dirti chi c'è e dove, che temperatura fa, e posso accendere luci, "
            "fare festa o grigliare." if lang == "it"
            else "I'm the house: I can tell you who's here and where, the temperature, and I can turn on "
            "lights, throw a party or light the barbecue.")


_ = ANIMALS
