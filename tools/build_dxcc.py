#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build src/dxcc_tables.py from the official ARRL DXCC list.

Input: tools/data/arrl_dxcc_2026.txt, exported from the January 2026 edition of
the ARRL DXCC List (340 current entities) by tools/export_arrl_pdf.py.  Deleted
entities come from the 2018 edition's plain-text list, which the PDF edition does
not include; they are kept so an old log's DXCC number is recognised.

The entity CODE is what matters most: LoTW, Club Log and N1MM all write DXCC into
the ADIF record, and the resolver trusts it, so a wrong number reports a wrong
country and a wrong postage figure.

Usage: python tools/build_dxcc.py
"""

from __future__ import annotations

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CURRENT = os.path.join(HERE, "data", "arrl_dxcc_2026.txt")
DELETED = os.path.join(HERE, "data", "arrl_dxcc_2018.txt")
OUT = os.path.join(ROOT, "src", "dxcc_tables.py")

TOKEN_RE = re.compile(r"([A-Z]+)(\d*)")


def read_rows(path: str):
    rows = []
    if not os.path.isfile(path):
        return rows
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line or line.startswith("--") or "\t" not in line:
            continue
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        code, name, continent, prefix = parts
        rows.append({"code": str(int(code)), "name": name.strip(),
                     "continent": continent.strip(), "prefix": prefix.strip()})
    return rows


def expand_range(start: str, end: str):
    """Letter range (SN-SR), digit tail (9M2,4) or letter+digit (UA-UI)."""
    stem = ""
    while start and end and start[0] == end[0] and start[0].isalpha():
        stem += start[0]
        start, end = start[1:], end[1:]
    if not start or not end:
        return [stem] if stem else []
    if start.isdigit() and end.isdigit():
        return [f"{stem}{n}" for n in range(int(start), int(end) + 1)]
    if len(start) == 1 and len(end) == 1 and start.isalpha() and end.isalpha():
        return [f"{stem}{chr(c)}" for c in range(ord(start), ord(end) + 1)]
    return [f"{stem}{start}", f"{stem}{end}"]


def _digit_range(start: str, end: str):
    if not (start.isdigit() and end.isdigit()):
        return [start]
    low, high = int(start), int(end)
    if low <= high:
        values = list(range(low, high + 1))
    else:                                  # 8-0 means 8, 9, 0
        values = [n % 10 for n in range(low, high + 11)]
    return [str(v) for v in values]


def raw_prefix_tokens(column: str):
    """Every allocation a prefix cell names, before note-number stripping.

    "SN-SR"      -> SN..SR
    "9M2,4"      -> 9M2, 9M4
    "UA-UI1-7"   -> UA1..UI7
    "K,W,N"      -> K, W, N
    "BU-BX"      -> BU..BX
    """
    out = []
    # The published list pads a long allocation inside the cell ("ZC442 UK" is
    # the allocation ZC442UK with the column padding in the middle).
    text = column.replace(" ", "")
    for chunk in re.split(r"[,\s]+", text):
        if not chunk:
            continue
        pieces = chunk.split("-")
        if len(pieces) == 2:
            # The range end may carry a call area or a footnote number:
            # "DA-DR14" allocates DA..DR (14 is glossary note 14), while
            # "UA-UI1-7" arrives here as 3+ pieces and is handled below.
            tail = re.fullmatch(r"([A-Z]+)(\d*)", pieces[1])
            if tail:
                out.extend(expand_range(pieces[0], tail.group(1)))
                continue
            out.extend(expand_range(pieces[0], pieces[1]))
            continue
        if len(pieces) >= 3 and pieces[0].isalpha():
            head = re.fullmatch(r"([A-Z]+)(\d*)", pieces[1])
            if head:
                letters = expand_range(pieces[0], head.group(1))
                out.extend(letters)          # a letters range allocates them all
                # The trailing part is a call-area range only when the range's
                # end letter carries one ("UA-UI1-7"); a lone number after a
                # two-letter range is a footnote ("DA-DR14" is note 14).
                areas = head.group(2)
                if areas or len(pieces) > 3:
                    for letter in letters:
                        for digit in _digit_range(areas or pieces[2],
                                                  pieces[-1]):
                            out.append(letter + digit)
                continue
        out.append(chunk)
    # A chunk that is only digits replaces the last digit of the allocation
    # before it: "KP3,4" is KP3 and KP4, and "9M2,4" is 9M2 and 9M4.  (The list
    # writes a continuation as the last digit alone, not the whole call area.)
    expanded = []
    for token in out:
        if token.isdigit() and expanded:
            target = expanded[-1]
            if re.fullmatch(r"[A-Z]+\d", target):
                for digit in token:
                    expanded.append(target[:-1] + digit)
                continue
            if re.fullmatch(r"[A-Z]+", target):
                expanded.append(target + token)
                continue
        expanded.append(token)
    return [p for p in expanded if p and re.fullmatch(r"[A-Z0-9]+", p)]


def build_prefix_map(rows):
    """prefix -> code for every row, with the list's abbreviations undone.

    The tokens are resolved in two rounds:

      1. cells that are one plain alphanumeric token, plus every range expansion,
         give the allocation set outright -- this is where "E7" (Bosnia) and
         "KP3"/"KP4" (Puerto Rico via the "KP3,4" continuation) come from;
      2. the tokens that still carry a glued note number or a name suffix are
         resolved against that set, which is what turns "E729" into E7,
         "BS711" into BS7, "4O47" into 4O4..4O7 and "ZC442UK" into ZC4.

    The second round only ever accepts a stem that round 1 proved exists, so a
    real call area is never mistaken for a note number.
    """
    tokens = {row["code"]: raw_prefix_tokens(row["prefix"]) for row in rows}

    #: A cell that is ONE alphanumeric token states that allocation outright, so
    #: it is authoritative.  Kept apart from the general allocation set because a
    #: range expansion is weaker evidence: Portugal's row is the range "CQ-CU",
    #: which expands to include "CU", while the Azores row says "CU" on its own
    #: -- and the Azores must win that prefix.
    direct = {row["code"]: [t for t in tokens[row["code"]]]
              for row in rows
              if re.fullmatch(r"[A-Z0-9]+", row["prefix"].strip())}
    direct_tokens = {t for tokens_ in direct.values() for t in tokens_}

    #: The plausible allocation set, built from the tokens themselves.  The list
    #: writes an allocation with a call-area range, a glossary note number and
    #: sometimes part of the entity name glued on, so a token like "ZC442UK" has
    #: to be read back to "ZC4".
    allocations = set(direct_tokens)
    for row in rows:
        for token in tokens[row["code"]]:
            if token in allocations:
                continue
            head = _STEM_RE.match(token)
            if head and not head.group("rest"):
                allocations.add(token)

    def _stems() -> set:
        """Every leading sub-run of a known allocation."""
        out = set(allocations)
        for token in allocations:
            for cut in range(len(token), 1, -1):
                out.add(token[:cut])
        return out

    mapping = {}
    #: Direct statements first: they must beat anything derived from a range.
    for row in rows:
        for token in direct.get(row["code"], ()):
            mapping.setdefault(token, row["code"])

    #: The implicit allocations (Sicily is IT9 inside Italy's I block) are also
    #: direct statements, so they are placed before the derived ones.
    name_to_code = {}
    for row in rows:
        name_to_code.setdefault(row["name"], row["code"])
    for entity, prefixes in IMPLIED_PREFIXES.items():
        code = name_to_code.get(entity)
        if not code:
            continue
        for prefix in prefixes:
            mapping.setdefault(prefix, code)

    #: Then everything else, including the range expansions.
    for row in rows:
        for token in tokens[row["code"]]:
            if token in mapping:
                continue
            if token in allocations:
                mapping.setdefault(token, row["code"])
                continue
            for prefix in _decompose_allocation(token, allocations, _stems()):
                mapping.setdefault(prefix, row["code"])

    #: Anything the two passes produced is an allocation in its own right.
    allocations.update(mapping)
    allocations.update(prefix
                       for prefixes in IMPLIED_PREFIXES.values()
                       for prefix in prefixes)
    return mapping, allocations


#: An allocation with a trailing letter run belonging to the entity's name:
#: "ZC442UK" ends in the "UK" of "UK Sovereign Base Areas".
_SUFFIXED_RE = re.compile(r"^(?P<alloc>[A-Z]+[0-9]+)(?P<suffix>[A-Z]+)$")


#: The published list's token for an allocation that also carries a call area
#: and/or a glued glossary note: "ZC442UK" is ZC4 + note 42 + the "UK" of the
#: entity's name, "KP522" is KP5 + note 22, "E729" is E7 + note 29, "4O47" is 4O
#: with call areas 4 to 7.  The target allocation is the leading letters followed
#: by one digit (or two letters and a digit), which is what this captures.
_STEM_RE = re.compile(r"^(?P<target>[A-Z]+\d?)(?P<rest>\d*)(?P<tail>[A-Z]*)$")
#: The stem an allocation is built on: its leading letters plus a call-area digit.
_CALL_AREA_RE = re.compile(r"^(?P<letters>[A-Z]+)(?P<area>\d?)$")

#: Allocations the published list leaves implicit.  Its Italy row is just "I"
#: (a footnote spells out I1-I9, IK, IN, IO, IQ, IR, IS, IT, IU, IW, IZ), so
#: without these ordinary Italian calls such as IK1AAA resolve to UNKNOWN.
#: Note there is no Sicily entity in the DXCC list -- IT9 is Italy -- but the
#: earlier hand-built table had invented one.
IMPLIED_PREFIXES = {
    # Prefixes the published list leaves implicit, and the owner of each
    # prefix it shares between entities.  Applied with setdefault before
    # anything derived from a range, so a specific allocation always wins.
    # One entry per line, deliberately: a multi-line entry is easy to lose
    # and the reason each prefix is here is part of the data.
    # the list writes England as G, GX, M; GB and 2E are what licensees hold
    "England": ['GB', '2E', 'GX'],
    # the list gives Japan JA-JS and 7J-7N
    "Japan": ['7J', '7K', '7L', '7M', '7N'],
    # the list gives Korea HL and 6K-6N
    "Republic of Korea": ['DS', '6K', '6L', '6M', '6N'],
    # the list writes China as B plus a call area; BM-BQ, BU-BW and BX are TAIWAN and must not appear here
    "China": ['3H', 'BA', 'BD', 'BE', 'BF', 'BG', 'BH', 'BI', 'BJ', 'BK', 'BL'],
    # the list writes Italy as I with a footnote spelling out the blocks
    "Italy": ['IK', 'IN', 'IO', 'IQ', 'IR', 'IS', 'IT', 'IU', 'IW', 'IZ', 'IA', 'IB', 'IC', 'ID', 'IE', 'IF', 'IG', 'IH', 'IJ', 'IL', 'IM'],
    # the list gives 9V
    "Singapore (Republic of)": ['9V'],
    # the list gives AP-AS
    "Pakistan (Islamic Rep of)": ['AP'],
    # the list gives HS and E2
    "Thailand": ['E2'],
    # France's overseas departments share TO
    "Guadeloupe": ['TO'],
    # the Austral and Marquesas islands are FO sub-entities
    "French Polynesia": ['FO'],
    # the main Chilean Pacific territory
    "Easter I.": ['CE0'],
    # the main Brazilian island group
    "Fernando de Noronha": ['PP0'],
    # the main Colombian island group
    "San Andres & Providencia": ['HK0'],
    # Chesterfield is an FK dependency
    "New Caledonia": ['FK'],
    # South Georgia and friends are VP8 sub-entities
    "Falkland Is.": ['VP8'],
    # Ducie is a Pitcairn dependency
    "Pitcairn I.": ['VP6'],
    # Swains is administered with American Samoa
    "American Samoa": ['KH8'],
    # the main Japanese island group
    "Ogasawara": ['JD1'],
    # the more populous Cook group
    "S. Cook Is.": ['E5'],
    # the older North Cook allocation
    "N. Cook Is.": ['ZK1'],
    # the older Niue allocation
    "Niue": ['ZK2'],
    # the older Tokelau allocation
    "Tokelau Is.": ['ZK3'],
    # Conway Reef and Rotuma are 3D2 sub-entities
    "Fiji": ['3D2'],
    # Peter 1 is the other 3Y entity
    "Bouvet": ['3Y'],
    # Kure is its own entity
    "Kure I.": ['KH7K'],
    # both VK0 entities are Antarctic; KC4 was the US Antarctic block
    "Antarctica": ['VK0', 'CE9', 'KC4'],
    # Wake is its own entity
    "Wake I.": ['KH9'],
    # the Northern Marianas
    "Mariana Is.": ['KH0'],
    # Guam is its own entity
    "Guam": ['KH2'],
    # Tonga is its own entity
    "Tonga": ['A3'],
    # the US Virgin Islands
    "Virgin Is.": ['KP2'],
    # Navassa is its own entity
    "Navassa I.": ['KP1'],
    # Desecheo is its own entity
    "Desecheo I.": ['KP5'],
    # KP3 and KP4 are Puerto Rico
    "Puerto Rico": ['KP4'],
    # the list gives D4
    "Cabo Verde (Repub of)": ['D4'],
    # the list gives 7X
    "Algeria (People’s Dem Republic of)": ['7X'],
    # Portugal's range CQ-CU would otherwise claim it
    "Azores": ['CU'],
}
def _decompose_allocation(token: str, known: set, stems: set):
    """Every allocation a prefix token names, undoing the list's abbreviations.

    The published list glues a call-area range and a glossary note number onto an
    allocation:

        4O47     -> 4O with call areas 4-7
        ZC442UK  -> ZC4  (note 42, then the "UK" of the entity name)
        KP522    -> KP5  (note 22)
        E729     -> E7   (note 29)
        9M2      -> 9M2  (there is no "9M", so nothing is removed)

    Everything after the target allocation is a call-area range, a note number or
    a name suffix, so the target is simply the leading letters plus one digit --
    "ZC442UK" -> "ZC4", "KP522" -> "KP5", "E729" -> "E7".  A target is only
    accepted when the list corroborates it: the stem (letters + call area) must
    be listed somewhere, which is what stops "9M2" losing its digit.
    """
    # Form A: a letters range with a digit range: "4O47" -> 4O4..4O7.  The stem
    # must be an allocation in its own right.
    tail = re.fullmatch(r"([A-Z][A-Z0-9]*[A-Z])(\d)(\d)", token)
    if tail and tail.group(1) in known:
        return [tail.group(1) + area
                for area in _digit_range(tail.group(2), tail.group(3))]

    match = _STEM_RE.match(token)
    if match:
        target = match.group("target")
        rest = match.group("rest")
        stem = _CALL_AREA_RE.match(target)
        # "ZC442UK": target ZC4, rest "42", a name suffix after it.
        if rest and stem and stem.group("letters") in known:
            return [target]
        # "KP522": target KP5, rest "22".  The stem is KP, already a prefix.
        if rest and target in known:
            return [target]
        # "E729": target E7, rest "29" -- same shape, so the same rule.
        if rest and target in stems:
            return [target]
        # "DA-DR14" style leftovers and plain allocations.
        if not rest:
            return [strip_glossary_number(token, known)] if target != token \
                else [token]

    # A trailing letter run is part of the entity's name: "ZC442UK" -> "ZC442".
    suffixed = _SUFFIXED_RE.match(token)
    if suffixed:
        inner = _decompose_allocation(suffixed.group("alloc"), known, stems)
        if inner and inner != [suffixed.group("alloc")]:
            return inner

    return [strip_glossary_number(token, known)]


def _code_for_name(entities: dict, name: str) -> str:
    """The code of the entity with this name, or "" when there is none."""
    for code, row in entities.items():
        if row["name"] == name:
            return code
    return ""


#: A glossary footnote number glued to a prefix cell by the PDF: "BS711" is the
#: prefix BS7 with note 11, "E729" is E7 with note 29, "KP522" is KP5 with note
#: 22.  The number is only removed when what remains is itself an allocation
#: that appears bare elsewhere in the list, so a real call area survives: "9M2"
#: stays whole because "9M" is never listed on its own.
#: The published list's glossary has this many numbered notes, so a glued note
#: number is never larger than this.
MAX_GLOSSARY_NOTE = 60


def strip_glossary_number(prefix: str, known: set) -> str:
    """Remove a glued glossary note number from a prefix, when present.

    ``known`` holds plausible allocation heads (see build_prefix_map).  A head is
    accepted when everything after it is a plausible note number -- at least two
    digits and no more than the glossary has.  The ambiguity that remains is a
    head with exactly one digit after it ("KP3" and "KP4" are real allocations,
    but "BS7" plus note 11 is written "BS711"), and there the LONGEST known head
    wins, because a note number is at least two digits:

        BS711 -> BS7   (note 11; "BS" is also a block but leaves "711")
        E729  -> E7    (note 29; "E" is too short and "E72" is not a head)
        KP522 -> KP5   (note 22)
        KP3   -> KP3   (a real allocation; "KP" would leave a single digit)
        4O47  -> 4O47  (neither "4O" nor "4O4" is a head)
    """
    if not known or prefix in known:
        return prefix
    best = ""
    for cut in range(2, len(prefix)):
        head = prefix[:cut]
        suffix = prefix[cut:]
        if head not in known or not suffix.isdigit():
            continue
        if len(suffix) < 2 or int(suffix) > MAX_GLOSSARY_NOTE:
            continue
        if len(head) > len(best):
            best = head
    return best or prefix


def parse_deleted(path: str):
    """Deleted entities from the 2018 plain-text list."""
    out = {}
    if not os.path.isfile(path):
        return out
    text = open(path, encoding="utf-8", errors="replace").read()
    cut = text.find("DELETED ENTITIES")
    if cut < 0:
        return out
    for line in text[cut:].splitlines():
        match = re.match(r"^\s*(\S.*?)\s{2,}.*?\s+"
                         r"(AF|AN|AS|EU|NA|OC|SA)\s+\S+\s+\S+\s+(\d{3})\s*$",
                         line)
        if match:
            out[str(int(match.group(3)))] = match.group(1).strip()
    return out


def main() -> int:
    current = read_rows(CURRENT)
    if not current:
        print(f"no rows in {CURRENT}; run tools/export_arrl_pdf.py first")
        return 2

    entities = {}
    for row in current:
        entities.setdefault(row["code"], row)
    print(f"current entities: {len(current)} rows, {len(entities)} codes")

    prefix_to_code, bare_allocations = build_prefix_map(current)

    #: Prefixes the list hands to more than one entity.  The mapping must pick
    #: one owner (a lookup cannot return several), so record the others here and
    #: let the resolver say so instead of pretending the answer is certain.
    shared_codes: dict = {}
    for row in current:
        for token in raw_prefix_tokens(row["prefix"]):
            shared_codes.setdefault(token, set()).add(row["code"])
    shared_prefixes = {prefix: sorted(codes)
                       for prefix, codes in shared_codes.items()
                       if len(codes) > 1}

    # Names that share a code with another name are separate DXCC entities.
    extra_names = []
    seen_codes = set()
    for row in current:
        if row["code"] in seen_codes:
            extra_names.append(row)
        else:
            seen_codes.add(row["code"])

    # The list gives E5 to both Cook Islands groups and does not say which
    # call areas belong to which, so E5 goes to the more populous South Cook
    # Islands.  A log's own COUNTRY or DXCC field, when present, still wins.
    prefix_to_code.setdefault("E5", _code_for_name(entities, "S. Cook Is."))

    deleted = parse_deleted(DELETED)
    print(f"prefixes: {len(prefix_to_code)}   extra names: {len(extra_names)}"
          f"   deleted: {len(deleted)}"
          f"   shared prefixes: {len(shared_prefixes)}")

    for code, want in (("269", "Poland"), ("501", "Bosnia-Herzegovina"),
                       ("386", "Taiwan"), ("318", "China"),
                       ("506", "Scarborough Reef"), ("54", "European Russia"),
                       ("15", "Asiatic Russia"), ("126", "Kaliningrad"),
                       ("291", "United States of America")):
        got = entities.get(code)
        ok = got and want.lower() in got["name"].lower()
        print(f"  {code:5} -> {got['name'] if got else '(absent)':38} "
              f"{'OK' if ok else 'MISMATCH'}")

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('"""DXCC entities and prefixes from the official ARRL DXCC '
                 'list.\n\n'
                 'DO NOT EDIT BY HAND.  Regenerate with\n'
                 '    python tools/export_arrl_pdf.py <DXCC_Current.pdf>\n'
                 '    python tools/build_dxcc.py\n'
                 'Source: ARRL DXCC List, January 2026 edition (340 current\n'
                 'entities), plus the 2018 edition for deleted entities.\n'
                 'The numbers are the real ARRL entity codes, which matter\n'
                 'because a log\'s own DXCC field is authoritative.\n"""\n\n')
        fh.write("from __future__ import annotations\n\n")
        fh.write("#: entity code -> (name, continent)\nENTITIES: dict = {\n")
        for code in sorted(entities, key=int):
            row = entities[code]
            fh.write(f'    "{code}": ("{row["name"]}", "{row["continent"]}"),\n')
        fh.write("}\n\n")

        fh.write("#: every allocated prefix -> entity code\n")
        fh.write("PREFIX_TO_CODE: dict = {\n")
        for prefix in sorted(prefix_to_code):
            fh.write(f'    "{prefix}": "{prefix_to_code[prefix]}",\n')
        fh.write("}\n\n")

        fh.write("#: entities that share a code with another name (E5 is North\n"
                 "#: and South Cook, CE0 covers three Chilean islands, VK0\n"
                 "#: covers Heard and Macquarie).  Separate entities for awards.\n")
        fh.write("ALIASES: list = [\n")
        for row in extra_names:
            fh.write(f'    ("{row["code"]}", "{row["name"]}", '
                     f'"{row["continent"]}", '
                     f'{raw_prefix_tokens(row["prefix"])!r}),\n')
        fh.write("]\n\n")

        fh.write("#: prefix -> every entity code the published list gives it.\n"
                 "#: Only prefixes with more than one owner appear.  The list\n"
                 "#: does not say which call area belongs to which entity --\n"
                 "#: \"CE0\" is Easter I., Juan Fernandez Is. and San Felix &\n"
                 "#: San Ambrosio, \"TO\" covers seven French territories -- so a\n"
                 "#: prefix lookup has to choose one.  These entries let the\n"
                 "#: resolver name the alternatives rather than hide them.\n")
        fh.write("SHARED_PREFIXES: dict = {\n")
        for prefix in sorted(shared_prefixes):
            codes = ", ".join(f'"{code}"' for code in shared_prefixes[prefix])
            fh.write(f'    "{prefix}": [{codes}],\n')
        fh.write("}\n\n")

        fh.write("#: deleted entity code -> name\nDELETED: dict = {\n")
        for code in sorted(deleted, key=int):
            fh.write(f'    "{code}": "{deleted[code]}",\n')
        fh.write("}\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
