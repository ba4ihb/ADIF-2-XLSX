#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DXCC entity lookup for amateur-radio callsigns.

The DXCC (DX Century Club) award divides the world into entities -- countries
and separate territories such as Hawaii, Alaska, Sicily and the Canary
Islands.  This module answers "which entity does this callsign belong to?".

Resolution order
----------------
1. An explicit ``DXCC`` code in the ADIF record.  Values written by the logging
   program or by the ARRL are authoritative, so they win.
2. A ``COUNTRY`` field value that names a known entity.
3. The callsign prefix, matched longest-first.

The prefix table is a curated subset of the ITU callsign allocations covering
the DXCC entities a logger realistically meets.  It is data-only: no network
access and no heuristics beyond prefix matching.  ``source`` reports which rule
matched, so a prefix guess is never presented as authoritative -- and an
unresolvable callsign yields ``UNKNOWN`` rather than a wrong country.

Where the callsign alone is genuinely ambiguous the table records the ARRL's
own primary list, and an ADIF ``DXCC`` or ``COUNTRY`` value overrides it.
"""

from __future__ import annotations

import re

import dxcc_tables as _tables
from typing import Dict, List, NamedTuple, Optional, Tuple

__all__ = ["DxccEntity", "lookup", "resolve", "ENTITY_COUNT", "UNKNOWN"]

UNKNOWN = "UNKNOWN"


class DxccEntity(NamedTuple):
    """One DXCC entity."""

    code: str
    name: str
    continent: str


def _e(code: str, name: str, continent: str) -> Tuple[str, DxccEntity]:
    return code, DxccEntity(code, name, continent)


#: Entities that are resolved from their prefix but whose ARRL DXCC number this
#: project could not verify against an official list.  They are keyed by their
#: ITU prefix so a number is never invented, and the DXCC_ENTITY column shows the
#: name, which is what the report is about.  The column's own log-supplied DXCC
#: number, when present, always wins and is reported unchanged.
PREFIX_ONLY_ENTITIES: Dict[str, DxccEntity] = {
    "FO0": DxccEntity("FO0", "Clipperton Island", "NA"),

    "CE0": DxccEntity("CE0", "Easter Island", "SA"),
    "CE0X": DxccEntity("CE0X", "Juan Fernandez Islands", "SA"),
    "EA6": DxccEntity("EA6", "Balearic Islands", "EU"),

    "HQ": DxccEntity("HQ", "Honduras", "NA"),
    "HT": DxccEntity("HT", "Nicaragua", "NA"),
    "HU": DxccEntity("HU", "El Salvador", "NA"),
    "YS": DxccEntity("YS", "El Salvador", "NA"),

    # Prefix-only entities: the name is reported and the postage is derived
    # from it, but the ARRL DXCC number could not be verified against an
    # official list while building this, so none is invented.  A log that
    # supplies DXCC itself still wins.
    "3B6": DxccEntity("3B6", "Agalega and St Brandon", "OC"),
    "3B9": DxccEntity("3B9", "Rodrigues", "OC"),
    "3C0": DxccEntity("3C0", "Annobon Island", "OC"),
    "3D2R": DxccEntity("3D2R", "Rotuma", "OC"),
    "3Y": DxccEntity("3Y", "Bouvet", "OC"),
    "3Y0": DxccEntity("3Y0", "Bouvet", "OC"),
    "E5": DxccEntity("E5", "South Cook Islands", "OC"),
    "E6": DxccEntity("E6", "Niue", "OC"),
    "FG": DxccEntity("FG", "Guadeloupe", "OC"),
    "FJ": DxccEntity("FJ", "Saint Barthelemy", "OC"),
    "FM": DxccEntity("FM", "Martinique", "OC"),
    "FS": DxccEntity("FS", "Saint Martin", "OC"),
    "FT5W": DxccEntity("FT5W", "Crozet Island", "OC"),
    "FT5X": DxccEntity("FT5X", "Kerguelen Islands", "OC"),
    "FT5Z": DxccEntity("FT5Z", "Amsterdam and St Paul Islands", "OC"),
    "FT8W": DxccEntity("FT8W", "Crozet Island", "OC"),
    "FT8X": DxccEntity("FT8X", "Kerguelen Islands", "OC"),
    "FT8Z": DxccEntity("FT8Z", "Amsterdam and St Paul Islands", "OC"),
    "JD1": DxccEntity("JD1", "Ogasawara", "OC"),
    "JD1M": DxccEntity("JD1M", "Minami Torishima", "OC"),
    "T31": DxccEntity("T31", "Central Kiribati", "OC"),
    "T32": DxccEntity("T32", "Eastern Kiribati", "OC"),
    "T33": DxccEntity("T33", "Banaba Island", "OC"),
    "VK9C": DxccEntity("VK9C", "Cocos (Keeling) Islands", "OC"),
    "VK9M": DxccEntity("VK9M", "Mellish Reef", "OC"),
    "VK9W": DxccEntity("VK9W", "Willis Island", "OC"),
    "VK9X": DxccEntity("VK9X", "Christmas Island", "OC"),
    "ZK1": DxccEntity("ZK1", "South Cook Islands", "OC"),
    "ZK2": DxccEntity("ZK2", "Niue", "OC"),
    "ZK3": DxccEntity("ZK3", "Tokelau", "OC"),
    "ZL9": DxccEntity("ZL9", "New Zealand Subantarctic Islands", "OC"),

    # Huangyan Dao / Scarborough Reef.  A DXCC entity in its own right, separate
    # from mainland China, and BS7 is its allocation; BS7H is reserved for it by
    # the Chinese national band plan.  Activated in 1994, 1995, 1997 and 2007.
    "BS7": DxccEntity("BS7", "Scarborough Reef", "AS"),
}


# ---------------------------------------------------------------------------
# Entity table: ARRL DXCC number -> (name, continent)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Entity and prefix tables.
#
# Generated from the published ARRL DXCC list by tools/build_dxcc_from_arrl.py
# and committed as src/dxcc_tables.py.  The numbers are the real ARRL entity
# numbers, which matters because a log's own DXCC field is authoritative: it is
# read straight out of ENTITIES, so a wrong number reports a wrong country and a
# wrong postage figure.
# ---------------------------------------------------------------------------
ENTITIES: Dict[str, DxccEntity] = {
    code: DxccEntity(code, name, continent)
    for code, (name, continent) in _tables.ENTITIES.items()
}

#: Entity name -> ARRL code.  Rules in this module name the entity they want
#: rather than hardcoding a number, so a renumbered table cannot silently point
#: a rule at the wrong country -- which is exactly what happened when Poland
#: turned out to be 269 and the old table had 269 = Togo.
_NAME_TO_CODE: Dict[str, str] = {
    name: code for code, (name, _continent) in _tables.ENTITIES.items()
}


def _code_of(name: str) -> str:
    """ARRL entity code for a name, or "" when the name is not in the table."""
    return _NAME_TO_CODE.get(name, "")


#: DXCC entities that share an ARRL code in the list but are separate entities
#: for award purposes -- E5 is both North and South Cook Islands, CE0 covers
#: three Chilean islands, VK0 covers Heard and Macquarie.  Each is keyed by its
#: own prefix, so the name is reported without inventing a number.
PREFIX_ONLY_ENTITIES: Dict[str, DxccEntity] = {}


def _register_alias_entities() -> None:
    for _code, name, continent, prefixes in _tables.ALIASES:
        key = prefixes[0] if prefixes else f"{_code}:{name}"
        PREFIX_ONLY_ENTITIES[key] = DxccEntity(key, name, continent)


_register_alias_entities()

#: Deleted entities: an old log's number is recognised rather than unknown.
DELETED_ENTITIES: Dict[str, str] = dict(_tables.DELETED)

#: prefix -> entity code, every allocation the ARRL list gives.
_PREFIX_ROWS: Tuple[Tuple[str, str], ...] = tuple(_tables.PREFIX_TO_CODE.items())

#: The two Russian entities and Kaliningrad, resolved by name once and reused.
_RUSSIA_EUROPE = _code_of("European Russia")
_RUSSIA_ASIA = _code_of("Asiatic Russia")
_KALININGRAD = _code_of("Kaliningrad")

#: Prefixes the resolver needs but the list does not spell out as its own row.
#: The R and U series are the reason: the list writes "UA-UI1-7,RA-RZ" for
#: European Russia and "UA-UI8-0,RA-RZ" for Asiatic, which the generator expands
#: into UA1..UI7 and UA8..UI0, so the letter pairs themselves (and the bare
#: R/U form) are added here as a fallback for a call with no call-area digit.
_EXTRA_PREFIX_ROWS: Tuple[Tuple[str, str], ...] = (
    *((pair, _RUSSIA_EUROPE) for pair in (
        "RA", "RB", "RC", "RD", "RE", "RF", "RG", "RH", "RI", "RJ", "RK",
        "RL", "RM", "RN", "RO", "RP", "RQ", "RR", "RS", "RT", "RU", "RV",
        "RW", "RX", "RY", "RZ")),
    *((pair, _RUSSIA_EUROPE) for pair in (
        "UA", "UB", "UC", "UD", "UE", "UF", "UG", "UH", "UI")),
    ("R", _RUSSIA_EUROPE), ("U", _RUSSIA_EUROPE),
    # Mainland China is B plus a call-area digit; the list writes the block as
    # "B", so the digit forms are added and Taiwan keeps the letter blocks.
    *((f"B{n}", "318") for n in "0123456789"),
    *((pair, "386") for pair in (
        "BM", "BN", "BO", "BP", "BQ", "BU", "BW", "BX")),
    # The list writes Hawaii as "KH6,7" and Alaska as "KL,AL,NL,WL", so the
    # letter-plus-area forms that callsigns actually use are added.
    *((f"{prefix}6", _code_of("Hawaii")) for prefix in ("KH", "AH", "WH", "NH")),
    *((f"{prefix}7", _code_of("Hawaii")) for prefix in ("KH", "AH", "WH", "NH")),
    *((prefix, _code_of("Alaska")) for prefix in ("KL", "AL", "WL", "NL")),
)

#: How many entities the table holds, used by the tests.
ENTITY_COUNT = len(ENTITIES)

PREFIX_TABLE: Tuple[Tuple[str, str], ...] = tuple(
    sorted(_PREFIX_ROWS, key=lambda row: (-len(row[0]), row[0]))
)

_PREFIX_INDEX: Dict[str, str] = {}
for _prefix, _code in PREFIX_TABLE:
    _PREFIX_INDEX.setdefault(_prefix, _code)

# A single leading letter is a last resort, used only when no letter-based
# prefix matched -- so "S50AAA" resolves through "S5" (Slovenia) rather than a
# stray "S".
#
# Only unambiguous single letters belong here.  "B" does not: Taiwan holds the
# BM-BQ and BU-BW blocks, so a bare "B" would send a Taiwanese call to the
# mainland.  For the same reason the single-letter form of an "R"/"U" call is
# resolved by its call-area digit (see _RUSSIA_CALL_AREA) rather than here, and
# "V" and "A" are left out because several entities share them.
#: Single leading letters, keyed by the entity NAME so the number can never go
#: stale again.  Consulted last, after every letter-based prefix has been tried,
#: so "S50AAA" resolves through "S5" (Slovenia) rather than a bare "S".
SINGLE_LETTER_NAMES: Dict[str, str] = {
    "K": "United States of America", "W": "United States of America",
    "N": "United States of America",
    "G": "England", "M": "England",
    "I": "Italy", "F": "France", "T": "Turkey", "D": "Federal Republic of Germany",
    "H": "Hungary", "J": "Japan", "L": "Argentina", "O": "Austria",
    "P": "Netherlands", "S": "Sweden", "Y": "Venezuela", "Z": "South Africa",
}

_NAME_TO_CODE: Dict[str, str] = {}
for _code, _row in _tables.ENTITIES.items():
    _NAME_TO_CODE.setdefault(_row[0], _code)

SINGLE_LETTER: Dict[str, str] = {
    letter: _NAME_TO_CODE[name]
    for letter, name in SINGLE_LETTER_NAMES.items()
    if name in _NAME_TO_CODE
}

# A callsign whose second character is a digit has no letter-only prefix to
# consult, so a single leading letter may decide it; "K1ABC" is United States.
# Longer prefixes are always tried first, so "V51AA" resolves through "V5"
# (Namibia) rather than the bare "V".
_SINGLE_LETTER_RE = re.compile(r"^([A-Z])\d")

# One lookup table: the curated prefix rows plus the single-letter fallbacks,
# sorted longest-first so the most specific allocation always wins.  A prefix
# that names its own entity (BS7) points at that entity's own key, which is not
# a number: see PREFIX_ONLY_ENTITIES.
PREFIX_LOOKUP: Dict[str, str] = {}
for _prefix, _code in sorted(
    tuple(_PREFIX_ROWS) + tuple(_EXTRA_PREFIX_ROWS)
    + tuple(SINGLE_LETTER.items()),
    key=lambda row: (-len(row[0]), row[0]),
):
    # The generated rows win: setdefault keeps the first, and they come first.
    PREFIX_LOOKUP.setdefault(_prefix, _code)
for _prefix, _entity in PREFIX_ONLY_ENTITIES.items():
    PREFIX_LOOKUP[_prefix] = _entity.code


def _entity_for(code: str) -> Optional[DxccEntity]:
    """Look up an entity by DXCC number or by a prefix-only key."""
    entity = ENTITIES.get(code)
    if entity is not None:
        return entity
    return PREFIX_ONLY_ENTITIES.get(code)


def prefixes_for_entity(code: str, limit: int = 8) -> List[str]:
    """Prefixes allocated to one DXCC entity, longest first.

    Used by the fixture anonymiser so that a pseudonym stays inside the same
    DXCC entity as the real callsign it replaces.
    """
    found = [p for p, c in PREFIX_LOOKUP.items() if c == str(code)]
    found.sort(key=lambda p: (-len(p), p))
    return found[:limit]


# ---------------------------------------------------------------------------
# Callsign normalisation
# ---------------------------------------------------------------------------
# Portable/qualifier suffixes that do not change the DXCC entity.
_QUALIFIERS = frozenset(
    {"P", "M", "MM", "AM", "QRP", "QRO", "A", "LH", "R", "T", "J", "V", "B",
     "N", "Y", "S", "DG", "PM", "KT", "NEW", "QRPP"}
)
# "F/DL1ABC" and "KH6/KH7K" put a location prefix first.
_LOCATION_FIRST_RE = re.compile(r"^[A-Z]{1,3}\d?/")
#: ITU blocks are 2-4 characters in practice; slices up to this length are
#: offered and the lookup table rejects the rest.
_MAX_PREFIX_LEN = 4
_ALNUM_RUN_RE = re.compile(r"^[A-Z0-9]+")
_LETTERS_FIRST_RE = re.compile(r"^([A-Z]+)(\d*)")
_DIGITS_FIRST_RE = re.compile(r"^\d+([A-Z]+)")
_DIGITS_RUN_RE = re.compile(r"^\d+")
# Two letters, a call-area digit, then the suffix: "BG5ABC" -> B(1) G(2) 5(3).
_SPLIT_BLOCK_RE = re.compile(r"^([A-Z])([A-Z])(\d)")
# A digit-led block: "3B9AA" -> "3"(1) "B"(2) "9"(3).  The letters+digit form
# ("3B9") is a genuine allocation -- Rodrigues, Annobon -- and must be built.
_DIGIT_LETTER_DIGIT_RE = re.compile(r"^(\d+)([A-Z])(\d)")


def _prefixes_of(base: str) -> List[str]:
    """Every plausible ITU prefix inside one callsign component.

    An allocation is a block of letters and digits at the start of the call -- a
    two, three or four character unit such as "DL", "KH6", "3B9", "VK9X" or
    "BG5" -- followed by the suffix.  Rather than enumerate the shapes (which
    kept missing one: "3B9" for Rodrigues, "FT5W" for Crozet, "VK9X" for
    Christmas Island), every leading slice of length 1 to 4 is offered and the
    lookup table decides which slices are actually allocated.

    Extra forms are added for the two shapes where the call area sits apart from
    the block: "BG5ABC" belongs to block "B" with call area 5, so "B5" is
    offered, and "KH6BB" resolves through "KH6".
    """
    alnum = _ALNUM_RUN_RE.match(base)
    if not alnum:
        return []
    run = alnum.group(0)

    out: List[str] = []

    def offer(candidate: str) -> None:
        if candidate and candidate not in out:
            out.append(candidate)

    # Every leading slice, longest first.
    for size in range(min(_MAX_PREFIX_LEN, len(run)), 0, -1):
        offer(run[:size])

    # "BG5ABC" -> "B5": first letter plus the call-area digit.
    split_block = _SPLIT_BLOCK_RE.match(base)
    if split_block:
        offer(split_block.group(1) + split_block.group(3))
    # "3B9AA" -> "3B9": digits, letter, digit.  Covered by the slices above, but
    # kept explicit so the intent survives a change to the slice length.
    digit_letter_digit = _DIGIT_LETTER_DIGIT_RE.match(base)
    if digit_letter_digit:
        offer(digit_letter_digit.group(1) + digit_letter_digit.group(2)
              + digit_letter_digit.group(3))
    # "VK9XAA" -> "VK9X" is a slice; "FT5WAA" -> "FT5W" is a slice too.

    return out


def candidate_prefixes(callsign: str) -> List[str]:
    """Prefixes to try for a callsign, most specific first.

    ``KH6BB``    -> ['KH6BB', 'KH6', 'KH']
    ``DL1ABC/P`` -> ['DL1ABC', 'DL1', 'DL']
    ``F/DL1ABC`` -> ['F', 'DL1ABC', 'DL1', 'DL']
    ``7K1AA``    -> ['7K1AA', '7K1', '7K']
    ``S50AAA``   -> ['S50AAA', 'S50', 'S5']
    """
    call = (callsign or "").upper().strip()
    if not call:
        return []

    bases: List[str] = []
    location_hint = ""
    if "/" in call:
        parts = [p for p in call.split("/") if p]
        # "F/DL1ABC" means the station is operating FROM France, so a leading
        # location prefix decides the entity and outranks the home call.
        if len(parts) >= 2 and _LOCATION_FIRST_RE.match(call):
            location_hint = parts[0]
        for part in parts:
            if part not in _QUALIFIERS:
                bases.append(part)
    else:
        bases.append(call)

    # A location prefix is tested on its own: for "F/DL1ABC" the answer is
    # France, and only the leading "F" may be used to say so.
    if location_hint:
        for prefix in _prefixes_of(location_hint):
            if len(prefix) >= 2 and prefix in PREFIX_LOOKUP:
                return [prefix]
        if location_hint in PREFIX_LOOKUP:
            return [location_hint]
    seen: List[str] = []
    for base in bases:
        for prefix in _prefixes_of(base):
            if prefix not in seen:
                seen.append(prefix)

    # Most specific (longest) first; original order breaks ties.
    ranked: List[str] = []
    for size in sorted({len(p) for p in seen}, reverse=True):
        for prefix in seen:
            if len(prefix) == size and prefix not in ranked:
                ranked.append(prefix)
    return ranked


#: Russia is split into two DXCC entities by call area: 1-7 are European Russia
#: and 8, 9 and 0 are Asiatic Russia.  Kaliningrad (UA2/RA2) is a third entity.
#: ARRL made one exception on 2011-12-01: a call in area 8 or 9 whose suffix
#: begins with F, G or X (Perm and Komi) counts as European Russia.
_ASIA_CALL_AREAS = {"8", "9", "0"}
_EUROPE_EXCEPTION_RE = re.compile(r"^(?:R[A-Z]?|U[A-Z]?)[890][FGX]")

# Only Russia allocates R followed by a call-area digit (R1AAA, RA3AA, RZ9AA).
# The U form is narrower: Russia holds UA-UI, whereas Ukraine (UR, US, UT, UU,
# UV, UW, UX, UY) and Kazakhstan (UN) begin with U plus a letter outside A-I, so
# they must not be swallowed by the Russian rule.
_CALL_AREA_RE = re.compile(r"^(?:R[A-Z]?|U[ABCDEFGHI]?)([0-9])")

#: Russia is split into two DXCC entities by call area: 1-7 are European Russia
#: and 8, 9 and 0 are Asiatic Russia.  Kaliningrad (UA2/RA2) is a third entity.
#: ARRL made one exception on 2011-12-01: a call in area 8 or 9 whose suffix
#: begins with F, G or X (Perm and Komi) counts as European Russia.
_ASIA_CALL_AREAS = {"8", "9", "0"}
_EUROPE_EXCEPTION_RE = re.compile(r"^(?:R|U)[A-Z]?[890][FGX]")


def russian_entity(head: str) -> str:
    """DXCC code for a Russian callsign, or "" when it is not one."""
    match = _CALL_AREA_RE.match(head)
    if not match:
        return ""
    area = match.group(1)
    if area == "2":
        return _KALININGRAD
    if area in _ASIA_CALL_AREAS:
        if _EUROPE_EXCEPTION_RE.match(head):
            return _RUSSIA_EUROPE           # Perm / Komi, per ARRL
        return _RUSSIA_ASIA
    return _RUSSIA_EUROPE


def lookup_number(
    dxcc_field: str = "", country: str = "", call: str = ""
) -> Tuple[str, str, str]:
    """Resolve a DXCC entity, most authoritative source first.

    Returns ``(code, name, source)`` where source is one of ``"ADIF_DXCC"``,
    ``"ADIF_COUNTRY"``, ``"PREFIX"`` or ``"NONE"``.
    """
    # 1. An explicit DXCC code written by the logging program is authoritative.
    digits = re.sub(r"[^0-9]", "", dxcc_field or "")
    if digits and digits in ENTITIES:
        entity = ENTITIES[digits]
        return entity.code, entity.name, "ADIF_DXCC"

    # 2. A COUNTRY value naming a known entity.
    wanted = (country or "").strip().lower()
    if wanted:
        for entity in ENTITIES.values():
            if entity.name.lower() == wanted:
                return entity.code, entity.name, "ADIF_COUNTRY"

    # 3a. An operating-location prefix on its own, e.g. "F/DL1ABC" is France and
    #     "KH8/KL7AA" is American Samoa.  A single letter is allowed here because
    #     the operator chose it deliberately, unlike a stray "S" in "S50AAA".
    head_part = (call or "").upper().strip().split("/")[0]
    if "/" in (call or "") and head_part in PREFIX_LOOKUP:
        entity = _entity_for(PREFIX_LOOKUP[head_part])
        if entity is not None:
            return entity.code, entity.name, "PREFIX"

    # 3b. Russia first: its two-letter blocks (RA, UA, ...) span BOTH entities,
    #     so the call-area digit decides and it must outrank the prefix rows.
    #     "RZ9AA" is Asiatic Russia even though "RZ" is listed as European.
    head = (call or "").upper().strip().split("/")[0]
    code = russian_entity(head)
    if code:
        entity = _entity_for(code)
        if entity is not None:
            return entity.code, entity.name, "PREFIX"

    # 3c. The callsign prefix, longest match first.  Every candidate of two or
    #     more characters is tried before any single letter, because ITU
    #     allocations such as "V5" or "S5" must beat a stray "V" or "S".
    for prefix in candidate_prefixes(call):
        if len(prefix) < 2:
            continue
        code = PREFIX_LOOKUP.get(prefix)
        if code:
            entity = _entity_for(code)
            if entity is not None:
                return entity.code, entity.name, "PREFIX"

    # 4. A genuine ITU "1x1" allocation (a single letter plus a single digit),
    #    used only when no longer prefix matched: K1ABC, W1AW, G3ABC.
    single = _SINGLE_LETTER_RE.match(head)
    if single:
        code = PREFIX_LOOKUP.get(single.group(1))
        if code:
            entity = _entity_for(code)
            if entity is not None:
                return entity.code, entity.name, "PREFIX"

    return "", UNKNOWN, "NONE"


def resolve(call: str = "", dxcc_field: str = "", country: str = "") -> Tuple[str, str, str]:
    """Return ``(entity_name, entity_code, source)`` for a callsign/record."""
    code, name, source = lookup_number(dxcc_field, country, call)
    return name, code, source


def lookup(call: str = "", dxcc_field: str = "", country: str = "") -> Tuple[str, str, str]:
    """Alias of :func:`resolve`, kept for readability at call sites."""
    return resolve(call, dxcc_field, country)
