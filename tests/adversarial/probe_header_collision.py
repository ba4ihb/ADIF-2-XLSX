# -*- coding: utf-8 -*-
r"""Blast radius of the content-aware header rule (revision FC0F332B).

A pre-<EOH> record is header content only when it carries no QSO_FIELDS name.
This probe answers: which header-ish field names would collide and turn a header
block into a QSO row?

Run: python verification\probe_header_collision.py
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import adif2xlsx as A  # noqa: E402

QSO = ("<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB"
       "<STATION_CALLSIGN:5>DL1AA<EOR>")

# (field name, sample value, would a producer plausibly put this in a header?)
CANDIDATES = [
    ("ADIF_VER", "3.1.4", "defined header field"),
    ("PROGRAMID", "TEST", "defined header field"),
    ("PROGRAMVERSION", "1.0", "defined header field"),
    ("CREATED_TIMESTAMP", "20240101 120000", "defined header field"),
    ("APP_LOTW_NUMREC", "199", "real LoTW header field"),
    ("APP_LOTW_LASTQSL", "2026-10-05 12:19:35", "real LoTW header field"),
    ("OPERATOR", "BA4IHB", "operator name in a header block"),
    ("NAME", "John", "operator name in a header block"),
    ("QTH", "Shanghai", "station info in a header block"),
    ("EMAIL", "a@b.com", "station info in a header block"),
    ("COMMENT", "Exported for award", "free-text note in a header block"),
    ("NOTES", "See attached", "free-text note in a header block"),
    ("GRIDSQUARE", "PM95", "station info in a header block"),
    ("MY_CALL", "BA4IHB", "station info in a header block"),
    ("MY_GRIDSQUARE", "OM86", "station info in a header block"),
    ("STATION_CALLSIGN", "BA4IHB", "station callsign in a header block"),
    ("CONTEST_ID", "WAPC", "contest info in a header block"),
    ("QSL_SENT", "Y", "QSL policy in a header block"),
]


def one(field: str, value: str) -> tuple:
    text = (f"<ADIF_VER:5>3.1.4<{field}:{len(value)}>{value}<EOH>\r\n" + QSO + "\r\n")
    path = os.path.join(HERE, "cases", "_collide.adi")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    res = A.parse_adif(path)
    out = A.build_rows([(path, res.records, res.header, res.unknown_tags)])
    calls = [r.get("CALL") or "" for r in out.rows]
    # rows == 1 (the W1AW QSO) means the header block was recognised as a header;
    # rows == 2 means the header block itself became a QSO row.
    classified = "header (OK)" if len(out.rows) == 1 else "BECAME A QSO ROW"
    return len(out.rows), calls, classified


def main() -> None:
    print(f"QSO_FIELDS has {len(A.QSO_FIELDS)} names\n")
    print("A header block '<ADIF_VER:5>3.1.4 + <FIELD> + <EOH>' followed by one QSO.")
    print("Correct output is 1 row (the QSO). 2 rows = the header became a bogus QSO.\n")
    print(f"{'header field':<20} {'rows':<5} {'CALLs':<16} {'classification':<22} note")
    print("-" * 108)
    collided = []
    for field, value, note in CANDIDATES:
        rows, calls, classified = one(field, value)
        if rows != 1:
            collided.append(field)
        print(f"{field:<20} {rows:<5} {str(calls):<16} {classified:<22} {note}")
    print(f"\nnames that turn a header block into a QSO row: {len(collided)}/{len(CANDIDATES)}")
    print(f"   {collided}")


if __name__ == "__main__":
    main()
