# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The registry of characters, pets, cars and objects the house knows.

Names are unique in the whole house, whatever the case, so that "where is
Marco?" always has one answer. A deleted identity goes to the bin for a day
before it is forgotten.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from .bus import Bus
from .model import CATEGORIES, PERSON, Identity, new_id
from .settings import Paths, read_json, write_json_atomic
from .store import Store


class NameTaken(ValueError):
    def __init__(self, name: str, existing: Identity) -> None:
        super().__init__(f"the name {name!r} is already used")
        self.name = name
        self.existing = existing


def clean_name(name: str, limit: int = 40) -> str:
    """One line of plain text: no control characters, no braces (names end up in spoken sentences)."""
    name = re.sub(r"[\x00-\x1f\x7f{}]", " ", name or "")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:limit]


MAX_FACTS = 8


def clean_facts(facts: Any) -> list[str]:
    """Up to eight short lines of plain text about a character, for its stories."""
    if isinstance(facts, str):
        facts = facts.splitlines()
    out: list[str] = []
    for f in facts or []:
        f = clean_name(str(f), 120).strip(" .;,-")
        if f and f.casefold() not in (x.casefold() for x in out):
            out.append(f)
    return out[-MAX_FACTS:]


def name_key(name: str) -> str:
    return clean_name(name).casefold()


class Identities:
    def __init__(self, paths: Paths, store: Store, bus: Bus) -> None:
        self.paths = paths
        self.store = store
        self.bus = bus
        self.path = paths.config / "identities.json"
        self._lock = threading.RLock()
        self._items: dict[str, Identity] = {}
        for d in read_json(self.path, []):
            try:
                ident = Identity.from_dict(d)
                self._items[ident.id] = ident
            except TypeError:
                continue

    # ------------------------------------------------------------ queries
    def all(self) -> list[Identity]:
        with self._lock:
            return sorted(self._items.values(), key=lambda i: i.created_at)

    def get(self, identity_id: str | None) -> Identity | None:
        if not identity_id:
            return None
        with self._lock:
            return self._items.get(identity_id)

    def by_name(self, name: str) -> Identity | None:
        key = name_key(name)
        with self._lock:
            for ident in self._items.values():
                if name_key(ident.name) == key or (ident.alias_en and name_key(ident.alias_en) == key):
                    return ident
        return None

    def name_of(self, identity_id: str | None, default: str = "") -> str:
        ident = self.get(identity_id)
        return ident.name if ident else default

    def names(self) -> list[str]:
        return [i.name for i in self.all()]

    # ------------------------------------------------------------ changes
    def _check_name(self, name: str, exclude: str | None = None) -> None:
        existing = self.by_name(name)
        if existing and existing.id != exclude:
            raise NameTaken(name, existing)

    def add(self, name: str, category: str = PERSON, *, color: str = "#888888",
            signature: list[float] | None = None, photo: str | None = None,
            alias_en: str | None = None, device: str | None = None,
            nickname: str | None = None) -> Identity:
        name = clean_name(name)
        if not name:
            raise ValueError("the name is empty")
        if category not in CATEGORIES:
            raise ValueError(f"unknown category {category!r}")
        with self._lock:
            self._check_name(name)
            ident = Identity(id=new_id("id"), name=name, category=category, color=color,
                             signature=list(signature or []), photo=photo,
                             alias_en=clean_name(alias_en) if alias_en else None,
                             created_by=nickname or device)
            self._items[ident.id] = ident
            self._save()
        self.store.add_audit("identity", ident.id, "create", None, ident.to_dict(), device, nickname)
        self.bus.publish("identities_changed", action="create", identity=ident.id)
        return ident

    def add_fact(self, identity_id: str, fact: str) -> Identity:
        ident = self._items[identity_id]
        return self.update(identity_id, facts=ident.facts + [fact])

    def update(self, identity_id: str, *, device: str | None = None,
               nickname: str | None = None, **fields: Any) -> Identity:
        with self._lock:
            ident = self._items[identity_id]
            before = ident.to_dict()
            if "name" in fields and fields["name"] is not None:
                name = clean_name(fields["name"])
                if not name:
                    raise ValueError("the name is empty")
                self._check_name(name, exclude=identity_id)
                ident.name = name
            if "category" in fields and fields["category"]:
                if fields["category"] not in CATEGORIES:
                    raise ValueError("unknown category")
                ident.category = fields["category"]
            for key in ("alias_en", "color", "photo"):
                if key in fields:
                    setattr(ident, key, fields[key])
            if "facts" in fields and fields["facts"] is not None:
                ident.facts = clean_facts(fields["facts"])
            if "signature" in fields and fields["signature"] is not None:
                ident.signature = list(fields["signature"])
            if "size" in fields and fields["size"] is not None:
                ident.size = float(fields["size"])
            if "poses" in fields and fields["poses"] is not None:
                ident.poses = [dict(p) for p in fields["poses"]][:8]
            self._save()
        if set(fields) - {"signature", "size", "poses"}:
            self.store.add_audit("identity", identity_id, "update", before, ident.to_dict(),
                                 device, nickname)
        self.bus.publish("identities_changed", action="update", identity=identity_id)
        return ident

    def delete(self, identity_id: str, *, device: str | None = None,
               nickname: str | None = None) -> Identity:
        with self._lock:
            ident = self._items.pop(identity_id)
            self._save()
        self.store.trash_put("identity", identity_id, ident.to_dict(), device, nickname)
        self.store.add_audit("identity", identity_id, "delete", ident.to_dict(), None, device, nickname)
        self.bus.publish("identities_changed", action="delete", identity=identity_id)
        return ident

    def restore(self, data: dict[str, Any]) -> Identity:
        ident = Identity.from_dict(data)
        with self._lock:
            if self.by_name(ident.name):
                ident.name = f"{ident.name} 2"
            self._items[ident.id] = ident
            self._save()
        self.store.add_audit("identity", ident.id, "restore", None, ident.to_dict())
        self.bus.publish("identities_changed", action="restore", identity=ident.id)
        return ident

    def replace_all(self, items: list[dict[str, Any]]) -> None:
        """Used by the configuration import."""
        with self._lock:
            self._items = {}
            for d in items:
                ident = Identity.from_dict(d)
                self._items[ident.id] = ident
            self._save()
        self.bus.publish("identities_changed", action="import")

    def _save(self) -> None:
        write_json_atomic(self.path, [i.to_dict() for i in self._items.values()])

    def to_list(self) -> list[dict[str, Any]]:
        out = []
        for i in self.all():
            d = i.to_dict()
            d.pop("signature", None)
            d.pop("poses", None)              # what the vision learned: for the board only
            out.append(d)
        return out
