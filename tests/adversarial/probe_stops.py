# -*- coding: utf-8 -*-
r"""Characterise the two remaining candidate defects on the frozen revision.

A) which mid-file tags make the parser stop and silently drop the rest
B) the control-character crash: exact exception and stderr
C) P5 boundary: 1-data-field file

Run: python verification\probe_stops.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, out_path, qso_rows, run, write_case  # noqa: E402

HDR = "<ADIF_VER:5>3.1.4<EOH>\n"


def rec(call, day):
    return f"<CALL:{len(call)}>{call}<QSO_DATE:8>{day}<TIME_ON:4>1200<MODE:3>SSB<EOR>\n"


TAGS = [
    ("<zzz>", "bare unrecognised tag"),
    ("<NOTE>", "bare tag, common name"),
    ("<EOR/>", "XML-style self-closing EOR"),
    ("<EOR />", "XML-style self-closing EOR with space"),
    ("<CALL:4:NN>W1AW", "two-letter datatype"),
    ("<CALL:4:N>W1AW", "legal datatype form"),
    ("<zzz:0>", "unknown field, zero length"),
    ("<zzz:3>abc", "unknown length-prefixed field"),
    ("</EOR>", "closing-style tag"),
    ("<MYSTERY>", "bare unknown tag, no length"),
    ("<!-- note -->", "XML comment"),
]


def main() -> None:
    print("A) a stray tag BETWEEN two records (2 QSOs expected in every row)\n")
    print(f"{'tag':<20} {'rc':<4} {'rows':<5} {'calls':<22} {'warn':<5} note")
    print("-" * 100)
    for i, (tag, note) in enumerate(TAGS):
        text = HDR + rec("W1AW", "20240101") + tag + "\n" + rec("K2DEF", "20240102")
        path = write_case(f"_stop_{i}.adi", text)
        out = out_path(f"_stop_{i}.xlsx")
        if os.path.exists(out):
            os.remove(out)
        p = run([path, "-o", out])
        rows = qso_rows(out) if os.path.exists(out) else []
        calls = [r.get("CALL") for r in rows]
        warn = "yes" if "WARNING" in p.stdout else "no"
        print(f"{tag:<20} {p.returncode:<4} {len(rows):<5} {str(calls):<22} {warn:<5} {note}")
        if p.stderr.strip():
            print(f"    stderr: {p.stderr.strip().splitlines()[-1][:150]}")

    print("\nB) control character crash\n")
    body = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            "<COMMENT:5>a\x01bcd<STATION_CALLSIGN:5>DL1AA<EOR>\n").encode("utf-8")
    path = write_case("_ctrl.adi", body, binary=True)
    out = out_path("_ctrl.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    print(f"rc={p.returncode}  workbook_written={os.path.exists(out)}")
    print("stderr (full):")
    print(p.stderr.rstrip())
    print(f"stdout: {p.stdout.strip()!r}")

    print("\nC) single-data-field file\n")
    path = write_case("_one_field.adi", HDR + "<CALL:4>W1AW<EOR>\n")
    out = out_path("_one_field.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    print(f"rc={p.returncode} workbook={os.path.exists(out)} stderr={p.stderr.strip()!r}")


if __name__ == "__main__":
    main()
