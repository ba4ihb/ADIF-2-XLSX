#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read the ARRL DXCC list PDF into (code, name, continent, prefixes) rows.

The document has a fixed layout:

    Prefix                      Entity   Cont  ITU CQ Code
    K,W,N,  United States of America      NA         6,7,8    3,4,5 291
    AA-AK#

The prefix column is 20 characters wide, the entity name runs up to the
continent code, and the last token is the entity code.  A row is located by its
trailing code and the continent token before it; everything to the left of the
continent is split on the first run of two or more spaces, which separates the
prefix column from the name.

A line with no code continues the previous row: a line made of allocation
characters extends its prefix column (the AA-AK line above), and a line of plain
words extends its name (an entity whose name wrapped).

Usage:
    python tools/parse_arrl_pdf.py <DXCC_Current.pdf> [out.txt]
"""

from __future__ import annotations

import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

CONTINENTS = ("AF", "AN", "AS", "EU", "NA", "OC", "SA")
CONT_RE = re.compile(r"\b(?:" + "|".join(CONTINENTS) + r")(?:/(?:"
                     + "|".join(CONTINENTS) + r"))*\b")
TAIL_RE = re.compile(r"(?P<code>\d{3})\s*$")
#: The prefix column is about this wide; used only when no padding run exists.
PREFIX_COLUMN = 20
MARKERS = re.compile(r"[*#^]")
ALLOC_LINE_RE = re.compile(r"^[A-Z0-9][A-Z0-9,\-()\s]*[*#^]?$")
NAME_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z .,'()\-/]*$")
#: A footnote reference glued to the front of a name: "TX* Clipperton I.".
GLUED_NOTE_RE = re.compile(r"^[A-Z0-9]{1,4}[*#^]+\s+(?=[A-Za-z])")
SKIP_PREFIXES = ("ARRL DXCC", "CURRENT ENTITIES", "January", "Current Entities",
                 "Note:", "* Indicates", "# Indicates", "Prefix", "Entity")


def page_text(path: str) -> str:
    """Every page of the PDF as one string."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _clean_cell(cell: str) -> str:
    """Drop footnote markers and tidy a prefix cell.

    Runs of spaces inside the cell are collapsed: the list writes one long
    allocation as "ZC442         UK" because the prefix column keeps its padding
    even when a cell overflows it, and that padding must not become part of the
    token or the allocation reads as "ZC442UK".
    """
    return re.sub(r"\s{2,}", " ", MARKERS.sub("", cell)).strip().strip(",").strip()


#: An ITU allocation cell: letters and digits with ",", "-", "/", "(" and ")",
#: e.g. "3B6, 7", "4P-4S", "K,W,N,AA-AK", "CE9/KC4", "9M2,4".
PREFIX_CELL_RE = re.compile(r"^[A-Z0-9][A-Z0-9,\-/()_\s]*$")
#: The prefix column is padded to about this width when the columns are rigid,
#: which is the case only for a handful of long entities.
PREFIX_COLUMN = 20


def _is_upper_part(text: str) -> bool:
    """True when ``text`` contains no lower-case letter.

    ITU allocations are written entirely in upper case, and entity names always
    contain at least one lower-case letter, so the first lower-case letter marks
    the start of the name.  This is what separates a prefix from a name when the
    PDF collapses their separating spaces to one.
    """
    return not re.search(r"[a-z]", text)


def _split_prefix_and_name(left: str):
    """Split a row's left part into (prefix cell, entity name).

    The columns are space-padded, but the extent of the padding varies with the
    content: "    1A1  Sov. Mil. Order of Malta" separates the two halves with
    two spaces, "    SN-SR*  Poland" separates them with one, and a long name
    leaves "    UA-UI1-7 European Russia".  No single geometric rule covers all
    three, so candidates are generated and the first consistent one wins.

    A candidate is consistent when the left half is a valid allocation cell (once
    footnote markers are stripped) and the right half is a name that does not
    still contain allocation text.  Where a candidate boundary is only one space
    wide the upper/lower-case rule resolves it.
    """
    body = left.strip()
    if not body:
        return "", ""

    # 1. A rigid run of two or more spaces is the intended separator.
    runs = [m for m in re.finditer(r"\s{2,}", left)]
    for run in runs:
        candidate = _clean_cell(left[:run.start()])
        name = left[run.end():].strip()
        if not name or not re.search(r"[A-Za-z]", name):
            continue
        if not candidate or not PREFIX_CELL_RE.match(candidate):
            continue
        if _still_holds_allocation(name):
            continue
        return candidate, name

    # 2. The halves are separated by a single space, so the case boundary tells
    #    them apart: the prefix ends where the first lower-case letter begins.
    letters = [i for i, ch in enumerate(body) if ch.isalpha()]
    for index in range(len(letters) - 1, -1, -1):
        position = letters[index]
        if not body[position].islower():
            continue
        cut = body.rfind(" ", 0, position)
        if cut <= 0:
            continue
        candidate = _clean_cell(body[:cut])
        name = body[cut + 1:].strip()
        if not candidate or not PREFIX_CELL_RE.match(candidate):
            continue
        if not name or not re.search(r"[A-Za-z]", name):
            continue
        if _still_holds_allocation(name):
            continue
        return candidate, name

    # 3. Nothing separated a prefix from the name, so this row has no
    #    allocation of its own (Spratly Is., ITU HQ, Sov. Mil. Order of Malta).
    return "", body


def _still_holds_allocation(name: str) -> bool:
    """True when ``name`` looks like "<allocation> <real name>" (or worse)."""
    if re.match(r"^[A-Z0-9][A-Z0-9,\-/()]*\s+[A-Za-z]", name):
        return True
    # Trailing footnote markers on the name mean the split landed too far right.
    return bool(name.endswith(("*", "#", "^")))


def _row_from(line: str):
    """Parse one data line, or return None when it is not one."""
    tail = TAIL_RE.search(line)
    if not tail:
        return None
    body = line[:tail.start()].rstrip()
    matches = list(CONT_RE.finditer(body))
    if not matches:
        return None
    cont = matches[-1]
    left = body[:cont.start()].rstrip()
    if not left.strip():
        return None
    prefix_cell, name = _split_prefix_and_name(left)
    name = GLUED_NOTE_RE.sub("", name.strip()).strip()
    if not name or not re.search(r"[A-Za-z]", name):
        return None
    return {
        "prefix_cell": _clean_cell(prefix_cell),
        "name": re.sub(r"\s{2,}", " ", name),
        "continent": cont.group(0).split("/")[0],
        "code": str(int(tail.group("code"))),
    }


def parse(text: str):
    """Return (current_rows, deleted_rows)."""
    current: list = []
    deleted: list = []
    section = "current"

    def target() -> list:
        return current if section == "current" else deleted

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) <= set("_- "):
            continue
        if "DELETED ENTITIES" in stripped.upper():
            section = "deleted"
            continue
        if stripped.startswith(SKIP_PREFIXES):
            continue
        row = _row_from(line)
        if row is not None:
            target().append(row)
            continue
        if not target():
            continue
        # A continuation line belongs to the previous row.  Two shapes occur and
        # they overlap for a single lower-case word ("on Cyprus"), so the
        # allocation shape is only taken when it is a single token: a line of
        # several words is a wrapped name.
        looks_alloc = bool(ALLOC_LINE_RE.match(stripped))
        single_token = len(stripped.split()) == 1
        if looks_alloc and single_token and re.search(r"[A-Z0-9]", stripped):
            target()[-1]["prefix_cell"] += "," + _clean_cell(stripped)
        elif NAME_LINE_RE.match(stripped) and _plausible_name_continuation(
                target()[-1]["name"], stripped):
            target()[-1]["name"] = (target()[-1]["name"] + " "
                                    + stripped).strip()
    return current, deleted


#: A wrapped entity name is at most this long in the list ("New Zealand
#: Subantarctic Islands" is 31 characters).
MAX_ENTITY_NAME = 45
#: Words that only ever appear in the document's prose, never in an entity name.
PROSE_WORDS = re.compile(
    r"\b(entity|station|contacts?|operat\w*|agreement|availability|bureau|"
    r"auspices|particular|notes?|found|references?|effective|valid|counts?|"
    r"made|before|after|only)\b", re.I)


def _plausible_name_continuation(current: str, candidate: str) -> bool:
    """True when ``candidate`` reads as the tail of an entity name.

    The document's footers and prose lines also look like plain words, so a
    continuation is rejected when it would push the name past any real entity
    name, when it is a sentence rather than a name fragment, or when it carries
    the vocabulary of the notes text.
    """
    if len(current) + 1 + len(candidate) > MAX_ENTITY_NAME:
        return False
    if PROSE_WORDS.search(candidate):
        return False
    # A sentence has its own full stop in the middle.
    return not re.search(r"\.\s+[a-z]", candidate)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    current, deleted = parse(page_text(sys.argv[1]))
    out = sys.stdout
    out.write(f"current rows: {len(current)}   deleted rows: {len(deleted)}\n")
    bycode = {row["code"]: row for row in current}
    for code, want in (("269", "Poland"), ("501", "Bosnia"),
                       ("291", "United States"), ("202", "Puerto Rico"),
                       ("386", "Taiwan"), ("318", "China"),
                       ("506", "Scarborough"), ("230", "Germany"),
                       ("54", "European Russia"), ("15", "Asiatic Russia")):
        row = bycode.get(code)
        ok = row and want.lower() in row["name"].lower()
        out.write(f"  {code:5} -> {row['name'] if row else '(absent)':38} "
                  f"prefix={(row['prefix_cell'] if row else ''):18} "
                  f"{'OK' if ok else 'CHECK'}\n")
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as fh:
            for row in current:
                fh.write(f"{row['code']}\t{row['name']}\t{row['continent']}"
                         f"\t{row['prefix_cell']}\n")
            fh.write("--DELETED--\n")
            for row in deleted:
                fh.write(f"{row['code']}\t{row['name']}\t{row['continent']}"
                         f"\t{row['prefix_cell']}\n")
        out.write(f"wrote {sys.argv[2]}\n")
    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
