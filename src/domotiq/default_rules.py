# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The rules a new house starts with. Everyone can change or delete them."""

from __future__ import annotations

from typing import Any


def default_rules() -> list[dict[str, Any]]:
    return [
        {
            "id": "r-utility-forbidden",
            "name": {"it": "Locale tecnico vietato", "en": "Utility room off limits"},
            "priority": 95, "alert": True, "cooldown_s": 0,
            "when": {"type": "dwell", "room": "utility", "seconds": 5, "repeat_s": 10,
                     "who": {"category": "person"}},
            "then": [
                {"type": "light", "room": "living", "effect": "alarm", "color": "#ff2010", "brightness": 80},
                {"type": "light", "room": "garage", "effect": "alarm", "color": "#ff2010", "brightness": 80},
                {"type": "sound", "name": "alarm"},
                {"type": "say", "text": {"it": "Attenzione: il locale tecnico è riservato!",
                                         "en": "Warning: the utility room is off limits!"}},
                {"type": "notify", "level": "alarm",
                 "text": {"it": "{name} è nel locale tecnico", "en": "{name} is in the utility room"}},
            ],
        },
        {
            "id": "r-bathroom-max",
            "name": {"it": "Bagno al massimo 1", "en": "Bathroom for one"},
            "priority": 95, "alert": True, "cooldown_s": 0,
            "when": {"type": "count_above", "room": "bathroom", "value": 1, "grace_s": 2,
                     "repeat_s": 15, "who": {"category": "person"}},
            "then": [
                {"type": "light", "room": "bathroom", "effect": "blink", "color": "#ff8000", "brightness": 80},
                {"type": "say", "text": {"it": "Il bagno è occupato! Aspetta il tuo turno.",
                                         "en": "The bathroom is taken! Please wait your turn."}},
                {"type": "notify", "level": "warning",
                 "text": {"it": "{count} persone in bagno", "en": "{count} people in the bathroom"}},
            ],
        },
        {
            "id": "r-shower",
            "name": {"it": "Doccia", "en": "Shower"},
            "priority": 60, "cooldown_s": 30,
            "when": {"type": "shower", "state": "start"},
            "then": [
                {"type": "light", "room": "bathroom", "effect": "cool", "color": "#20d0ff",
                 "brightness": 60, "duration_s": 180},
                {"type": "say", "text": {"it": "Accendo l'aspiratore del bagno.",
                                         "en": "Turning on the bathroom fan."}},
                {"type": "notify", "level": "info", "text": {"it": "Doccia in corso", "en": "Shower running"}},
            ],
        },
        {
            "id": "r-shower-end",
            "name": {"it": "Doccia finita", "en": "Shower over"},
            "priority": 60, "cooldown_s": 5,
            "when": {"type": "shower", "state": "stop"},
            "then": [{"type": "light_off", "rule": "r-shower"}],
        },
        {
            "id": "r-climate-hot",
            "name": {"it": "Termostato: caldo", "en": "Thermostat: hot"},
            "priority": 60, "cooldown_s": 20,
            "when": {"type": "climate", "state": "hot"},
            "then": [
                {"type": "light", "room": "all", "effect": "cool", "color": "#20d0ff",
                 "brightness": 60, "duration_s": 120},
                {"type": "say", "text": {"it": "Fa caldo! Accendo il climatizzatore.",
                                         "en": "It's hot! Turning on the air conditioning."}},
                {"type": "notify", "level": "info",
                 "text": {"it": "Climatizzatore acceso ({temp} °C)", "en": "Air conditioning on ({temp} °C)"}},
            ],
        },
        {
            "id": "r-climate-cold",
            "name": {"it": "Termostato: freddo", "en": "Thermostat: cold"},
            "priority": 60, "cooldown_s": 20,
            "when": {"type": "climate", "state": "cold"},
            "then": [
                {"type": "light", "room": "all", "effect": "warm", "color": "#ff7a20",
                 "brightness": 60, "duration_s": 120},
                {"type": "say", "text": {"it": "Fa freddo: accendo il riscaldamento.",
                                         "en": "It's cold: turning on the heating."}},
            ],
        },
        {
            "id": "r-climate-normal",
            "name": {"it": "Termostato: normale", "en": "Thermostat: back to normal"},
            "priority": 60, "cooldown_s": 5,
            "when": {"type": "climate", "state": "normal"},
            "then": [
                {"type": "light_off", "rule": "r-climate-hot"},
                {"type": "light_off", "rule": "r-climate-cold"},
                {"type": "say", "verbosity": "chatty",
                 "text": {"it": "La temperatura è tornata normale.", "en": "The temperature is back to normal."}},
            ],
        },
        {
            "id": "r-car-arrived",
            "name": {"it": "Auto arrivata", "en": "Car arrived"},
            "priority": 50, "cooldown_s": 20,
            "when": {"type": "car", "state": "arrived"},
            "then": [
                {"type": "say", "text": {"it": "Bentornato a casa!", "en": "Welcome home!"}},
                {"type": "notify", "level": "info", "text": {"it": "L'auto è in garage", "en": "The car is in the garage"}},
            ],
        },
        {
            "id": "r-car-departed",
            "name": {"it": "Auto partita", "en": "Car left"},
            "priority": 50, "cooldown_s": 20,
            "when": {"type": "car", "state": "departed"},
            "then": [
                {"type": "say", "text": {"it": "Buon viaggio!", "en": "Have a good trip!"}},
                {"type": "notify", "level": "info", "text": {"it": "L'auto è uscita dal garage", "en": "The car left the garage"}},
            ],
        },
        {
            "id": "r-grill-ready",
            "name": {"it": "Grigliata pronta", "en": "Barbecue ready"},
            "priority": 50, "cooldown_s": 10,
            "when": {"type": "grill", "state": "ready"},
            "then": [
                {"type": "say", "text": {"it": "La grigliata è pronta, tutti in giardino!",
                                         "en": "The barbecue is ready, everyone to the garden!"}},
                {"type": "notify", "level": "success",
                 "text": {"it": "La grigliata è pronta!", "en": "The barbecue is ready!"}},
            ],
        },
        {
            "id": "r-away-intruder",
            "name": {"it": "Intruso con la casa in modalità Via", "en": "Intruder while Away"},
            "priority": 90, "cooldown_s": 20,
            "when": {"type": "enter_room", "room": "indoor", "who": {"category": "person"}},
            "if": [{"type": "scene_is", "scene": "away"}],
            "then": [
                {"type": "light", "room": "all", "effect": "alarm", "color": "#ff2010", "brightness": 80,
                 "duration_s": 10},
                {"type": "sound", "name": "alarm"},
                {"type": "say", "text": {"it": "Intruso in casa! {name} è {room_in}.",
                                         "en": "Intruder in the house! {name} is {room_in}."}},
                {"type": "notify", "level": "alarm",
                 "text": {"it": "Intruso: {name}, {room}", "en": "Intruder: {name}, {room}"}},
            ],
        },
        {
            "id": "r-crowded-party",
            "name": {"it": "Festa in soggiorno", "en": "Living room party"},
            "enabled": False, "priority": 50, "cooldown_s": 120,
            "when": {"type": "count_above", "room": "living", "value": 3, "grace_s": 3,
                     "who": {"category": "person"}},
            "then": [{"type": "party"}],
        },
        {
            "id": "r-crowded-garden",
            "name": {"it": "Grigliata in compagnia", "en": "Barbecue with friends"},
            "enabled": False, "priority": 50, "cooldown_s": 120,
            "when": {"type": "count_above", "room": "garden", "value": 1, "grace_s": 10,
                     "who": {"category": "person"}},
            "then": [{"type": "grill"}],
        },
    ]
