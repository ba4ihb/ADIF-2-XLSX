#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Correct prefix cells using the ARRL list's own glossary.

The list glues a footnote reference onto many prefix cells: "BS711" is the
allocation BS7 with note 11, "JD119" is JD1 with note 19, "9M2,4" is 9M2 and 9M4
sharing note 8.  Splitting those by rule alone means guessing which digit run is
the note and which is a call area, and a wrong guess is a wrong DXCC entity.

The glossary removes the guesswork.  Each numbered note names the allocation it
discusses, in the same notation as the prefix column:

    19   (JD1) Only contacts made ...      <- the allocation is JD1
    8    (9M2,4,6,8) Only contacts ...      <- 9M2, 9M4, 9M6, 9M8
    14   (DA-DR) Only contacts ...          <- the range DA-DR

so a cell is corrected by finding, inside it, one of the allocations the note
names.  The text used for the correction comes from the document; nothing is
invented.

Usage: python tools/strip_glossary_notes.py <pdf> <rows.txt>
"""

from __future__ import annotations

import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

GLOSSARY_LINE_RE = re.compile(r"^\s*(\d{1,2})\s+\(([^)]*)\)")


def _expand_range(start: str, end: str) -> list:
    """A letters range (DA-DR) or a digit tail ("9M2" + "4" -> 9M4)."""
    if start.isdigit() and end.isdigit():
        return [str(n) for n in range(int(start), int(end) + 1)]
    stem = ""
    left, right = start, end
    while left and right and left[0] == right[0] and left[0].isalpha():
        stem += left[0]
        left, right = left[1:], right[1:]
    if not left or not right:
        return [stem] if stem else []
    if len(left) == 1 and len(right) == 1 and left.isalpha() and right.isalpha():
        return [f"{stem}{chr(c)}" for c in range(ord(left), ord(right) + 1)]
    return [start, end]


def parse_glossary(body: str) -> list:
    """Every allocation a note's parenthetical names.

    "9M2,4,6,8" is 9M2, 9M4, 9M6, 9M8 -- a digit tail continues the allocation
    before it -- while "DA-DR" is the whole range and "JD1" is one allocation.
    """
    text = re.sub(r"[^A-Za-z0-9,\-\s]", " ", body)
    out: list = []
    for chunk in re.split(r"[,\s]+", text.strip()):
        if not chunk:
            continue
        if "-" in chunk:
            start, _, end = chunk.partition("-")
            out.extend(_expand_range(start, end))
            continue
        if chunk.isdigit() and out:
            # A continuation: replace the last digit of the previous allocation.
            previous = out[-1]
            if re.fullmatch(r"[A-Z]+\d+", previous):
                out.append(previous[:-1] + chunk)
                continue
        out.append(chunk)
    return [a for a in out if re.fullmatch(r"[A-Z0-9]+", a)]


def load_notes(pdf: str) -> dict:
    """note number -> (raw notation, [expanded allocations]).

    The raw notation is kept because it is what the list uses in the prefix
    column too: note 14 reads "(DA-DR)", which is the DA-DR range, and expanding
    it into eighteen two-letter allocations loses that.  "DA-DR14" is therefore
    corrected to "DA-DR" rather than to "DA".
    """
    from pypdf import PdfReader
    text = "\n".join((p.extract_text() or "") for p in PdfReader(pdf).pages)
    notes = {}
    for line in text.splitlines():
        match = GLOSSARY_LINE_RE.match(line.strip())
        if not match:
            continue
        raw = re.sub(r"\s+", "", re.sub(r"[^A-Za-z0-9,\-\s]", "", match.group(2)))
        allocs = parse_glossary(match.group(2))
        if allocs:
            notes[match.group(1)] = (raw, allocs)
    return notes


def correct_cell(cell: str, notes: dict) -> tuple:
    """Return (corrected cell, allocation) when the glossary explains the cell.

    The cell is looked up in the glossary twice: once as written, and once with a
    trailing letter run removed, because the list runs the entity's own name into
    some cells ("ZC442UK" is ZC4 + note 42 + the "UK" of "UK Sovereign Base
    Areas").  For whichever form ends with a note number, the allocation is the
    part before that number, taking the glossary's notation when it is longer
    (a range such as "DA-DR") and the head when the head carries a call area the
    notation leaves off ("JD1", "VP2E").
    """
    compact = cell.replace(" ", "").strip()
    if not compact:
        return cell, []

    # "ZC442UK" -> also try "ZC442"; but only when letters really are trailing.
    bases = [compact]
    stripped = re.sub(r"[A-Z]+$", "", compact)
    if stripped and stripped != compact and stripped[-1].isdigit():
        bases.append(stripped)

    best = ""
    for base in bases:
        for number, (raw, allocs) in notes.items():
            if not base.endswith(number):
                continue
            head = base[:-len(number)]
            candidates = []
            # The notation as written, so a range stays a range ("DA-DR").
            if head == raw:
                candidates.append(raw)
            elif head.startswith(raw):
                # Only extend the notation by one character -- the call-area
                # digit -- so a range or a longer notation is never truncated.
                if len(head) - len(raw) <= 1:
                    candidates.append(head)
                candidates.append(raw)
            # Or an allocation the note names that the head extends ("VP2E").
            for alloc in allocs:
                if head.startswith(alloc):
                    candidates.append(head if head != alloc else alloc)
            for candidate in candidates:
                if len(candidate) > len(best):
                    best = candidate
    if best and best != compact:
        return best, best
    return cell, []


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    pdf, rows_path = sys.argv[1], sys.argv[2]
    notes = load_notes(pdf)
    print(f"glossary notes: {len(notes)}")
    for number in sorted(notes, key=int):
        print(f"  note {number:>3}: {notes[number]}")

    lines = open(rows_path, encoding="utf-8").read().splitlines()
    out_lines, corrections = [], []
    for line in lines:
        if not line or line.startswith("--") or "\t" not in line:
            out_lines.append(line)
            continue
        code, name, continent, cell = line.split("\t", 3)
        fixed, used = correct_cell(cell, notes)
        if fixed != cell:
            corrections.append((code, name, cell, fixed))
        out_lines.append(f"{code}\t{name}\t{continent}\t{fixed}")

    open(rows_path, "w", encoding="utf-8", newline="\n").write(
        "\n".join(out_lines) + "\n")
    print(f"\ncells corrected: {len(corrections)}")
    for code, name, before, after in corrections:
        print(f"  code {code:5} {name:36} {before!r:16} -> {after!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
