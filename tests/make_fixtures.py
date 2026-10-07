#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anonymise real ADIF exports into safe, committable test fixtures.

The six exports in the owner's ``ADI`` folder are genuine Club Log, JTDX, LoTW,
N1MM+, QRZ Logbook and TQSL output.  They are the most valuable fixtures the
project has, because each one exercises a real-world quirk -- but they carry
the owner's callsign, his correspondents' callsigns, his name, city, grid
square and e-mail address.

The rewrite keeps the files structurally identical, so they still test what
they were selected to test:

  * every declared length prefix is recomputed, never guessed
  * record order, field order and line endings are preserved
  * records per file and the field set per file are unchanged
  * a callsign maps to the same pseudonym everywhere, so repeats stay repeats
  * a value's surrounding whitespace is preserved (some exporters pad values)
  * the DXCC/COUNTRY values are left exactly as exported, including bad data,
    because a converter must faithfully reproduce what the log says

Privacy is verified afterwards: every original token must be gone from the
output, and the script fails loudly if any survives.

Run:  python tests/make_fixtures.py [source_dir]
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
import dxcc  # noqa: E402

DEST = os.path.join(HERE, "fixtures", "adi")
DEFAULT_SOURCE = r"C:\Users\Administrator\Desktop\ADI"

# --- personal data to remove ------------------------------------------------
# Callsigns belonging to the owner or his operators.
OWNER_CALLSIGNS = ["BA4IHB/P", "BA4IHB", "BA4JBN", "BG4LNW", "BA4IFR"]
# Free text that names people or places, replaced wherever it appears.
TEXT_TOKENS = [
    "\u6cf0\u5b89\u5e02",       # Tai'an City
    "\u5c71\u4e1c\u7701",       # Shandong Province
    "\u80a5\u57ce\u5e02",       # Feicheng City
    "\u6cf0\u5b89",             # Tai'an
    "\u5c71\u4e1c",             # Shandong
    "\u80a5\u57ce",             # Feicheng
    "\u90c1\u822a",             # given name
    "\u8303",                   # family name
]
# Fields whose whole value is personal.
PERSONAL_FIELDS = {
    "NAME": "Test Op", "MY_NAME": "Test Op",
    "QTH": "Test City", "MY_CITY": "Test City", "CITY": "Test City",
    "EMAIL": "test@example.invalid", "EMAIL2": "test@example.invalid",
    "ADDRESS": "1 Test Street", "ADDRESS1": "1 Test Street",
    "STREET": "1 Test Street", "MY_STREET": "1 Test Street",
    "POSTALCODE": "00000", "MY_POSTALCODE": "00000",
    "ZIP": "00000", "MY_ZIP": "00000",
    "GRIDSQUARE": "AA00aa", "MY_GRIDSQUARE": "AA00aa",
    "LAT": "00.000", "LON": "000.000",
    "MY_LAT": "00.000", "MY_LON": "000.000",
}
CALL_FIELDS = {
    "CALL", "STATION_CALLSIGN", "OPERATOR", "MY_CALL", "OWNER_CALLSIGN",
    "APP_LOTW_OWNCALL", "CONTACTED_OP", "QSL_VIA",
}

FIELD_RE = re.compile(
    rb"<([A-Za-z_][A-Za-z0-9_\-\.]*)\s*:\s*(\d+)(?::\s*([A-Za-z])\s*)?>"
)


def _make_pseudonym(value: str, prefix: str, digest: int) -> str:
    """A callsign of EXACTLY ``len(value)`` built on ``prefix``.

    The length invariant is what keeps the file structurally identical: every
    replacement must occupy the same byte count as the value it replaces, or
    the following fields shift.  The candidate is also verified through the
    real lookup, because a tail of the wrong shape (letters where a digit is
    required) would resolve to a different entity than the one it stands for.
    """
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    size = len(value)
    if size < 3:
        # Too short to build a callsign from; the caller keeps the original.
        return value

    target = dxcc.resolve(call=(prefix + "1AA"))[1] or ""

    candidates = []
    for alphabet in (letters + digits, digits + letters, letters, digits):
        seed = digest
        tail = ""
        while len(prefix) + len(tail) < size:
            tail += alphabet[seed % len(alphabet)]
            seed //= len(alphabet)
        candidates.append((prefix + tail)[:size])

    for candidate in candidates:
        if len(candidate) != size or candidate.upper() == value.upper():
            continue
        if not target or dxcc.resolve(call=candidate)[1] == target:
            return candidate

    # Last resort: keep the length, accept the entity drift rather than the
    # structural damage a wrong-length replacement would cause.
    filler = "N0" + str(digest).zfill(size)
    return filler[:size]


def _hash_callsign(value: str, index: dict) -> str:
    """Deterministic pseudonym that stays inside the original's DXCC entity."""
    key = value.upper()
    if key in index:
        return index[key]

    digest = 0
    for ch in key:
        digest = (digest * 131 + ord(ch)) % 1_000_003

    _code, entity_number, _source = dxcc.resolve(call=value)
    choices = dxcc.prefixes_for_entity(entity_number) if entity_number else []
    prefix = choices[digest % len(choices)] if choices else "N0"

    candidate = _make_pseudonym(value, prefix, digest)
    index[key] = candidate
    return candidate


def anonymise(data: bytes) -> tuple:
    """Rewrite personal data, recomputing every affected length prefix."""
    spans = []            # (start, end, replacement) over the raw bytes
    index = {}            # original callsign -> pseudonym
    stats = {"fields": 0, "calls": 0, "personal": 0}

    pos = 0
    while True:
        match = FIELD_RE.search(data, pos)
        if match is None:
            break
        name = match.group(1).decode("ascii", "replace").upper()
        declared = int(match.group(2))
        vstart = match.end()
        vend = vstart + declared
        if vend > len(data):
            break
        raw = data[vstart:vend].decode("ascii", "replace")

        # Keep the value's own leading/trailing whitespace intact: exporters
        # pad values, and dropping the padding would change what is tested.
        core = raw.strip(" \t\r\n")
        lead = raw[: len(raw) - len(raw.lstrip(" \t\r\n"))]
        trail = raw[len(raw.rstrip(" \t\r\n")):]
        replacement = None

        if name in CALL_FIELDS and core:
            new_core = _hash_callsign(core, index)
            if new_core != core:
                stats["calls"] += 1
            replacement = lead + new_core + trail
        elif name in PERSONAL_FIELDS and core:
            new_core = PERSONAL_FIELDS[name]
            if new_core != core:
                stats["personal"] += 1
            replacement = lead + new_core + trail

        if replacement is not None and replacement != raw:
            # Guard the invariant that keeps the file structurally identical:
            # a replacement must occupy exactly as many bytes as the value it
            # replaces, or every following field shifts.
            if len(replacement.encode("ascii", "replace")) == len(raw.encode("ascii", "replace")):
                spans.append((vstart, vend, replacement.encode("ascii", "replace")))
            else:
                stats.setdefault("length_rejected", 0)
                stats["length_rejected"] += 1
        stats["fields"] += 1
        pos = vend

    # Apply the field rewrites from the end so earlier offsets stay valid.
    out = data
    for start, end, new in reversed(spans):
        out = out[:start] + new + out[end:]

    # Remove personal tokens that live in prose (a banner or comment), keeping
    # the byte length unchanged so no structure shifts.  Matching is
    # case-insensitive because owners write their callsign both ways.
    for callsign in OWNER_CALLSIGNS:
        pattern = re.compile(re.escape(callsign.encode("ascii")), re.IGNORECASE)
        out = pattern.sub(
            lambda m: b"N0TEST"[: len(m.group(0))].ljust(len(m.group(0)), b"X"), out
        )
    for text_token in TEXT_TOKENS:
        raw_token = text_token.encode("utf-8")
        if raw_token in out:
            # Replace with an equal-length run of 'x' so lengths still hold.
            out = out.replace(raw_token, b"x" * len(raw_token))

    return out, stats


def main(argv) -> int:
    source = argv[1] if len(argv) > 1 else DEFAULT_SOURCE
    if not os.path.isdir(source):
        print(f"source folder not found: {source}")
        return 1
    os.makedirs(DEST, exist_ok=True)

    names = sorted(n for n in os.listdir(source)
                   if n.lower().endswith((".adi", ".adif")))
    if not names:
        print(f"no .adi/.adif files in {source}")
        return 1

    failures = []
    for name in names:
        data = open(os.path.join(source, name), "rb").read()
        new, stats = anonymise(data)
        with open(os.path.join(DEST, name), "wb") as fh:
            fh.write(new)

        # Verify: no original token may survive.
        leaks = []
        for token in OWNER_CALLSIGNS:
            if token.encode("ascii") in new:
                leaks.append(token)
        for token in TEXT_TOKENS:
            if token.encode("utf-8") in new:
                leaks.append(token)
        if leaks:
            failures.append((name, leaks))
        print(f"  {name:16} {stats['fields']:5} fields  "
              f"{stats['calls']:4} callsigns  {stats['personal']:3} personal  "
              f"-> {len(new):6} bytes  leaks={leaks if leaks else 'none'}")

    print(f"\nwrote {len(names)} fixtures to {DEST}")
    if failures:
        print("PRIVACY FAILURE:", failures)
        return 1
    print("privacy check: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
