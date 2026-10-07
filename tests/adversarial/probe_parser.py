# -*- coding: utf-8 -*-
r"""Direct probe of the frozen parser: find exactly where records are lost.

Imports adif2xlsx (read-only) and prints iter_records()/parse_adif() results for
minimal inputs. No files are written outside verification\.

Run: python verification\probe_parser.py
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True          # never leave a __pycache__ in the workspace root

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import adif2xlsx as A  # noqa: E402

HDR = "<ADIF_VER:5>3.1.4<EOH>"
R1 = "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>"
R2 = "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW<EOR>"
R3 = "<CALL:5>N3XYZ<QSO_DATE:8>20240103<TIME_ON:4>1400<MODE:3>FT8"

CASES = [
    ("1 record, EOR, trailing NL", HDR + "\n" + R1 + "\n"),
    ("2 records, both EOR", HDR + "\n" + R1 + "\n" + R2 + "\n"),
    ("2 records, last without EOR", HDR + "\n" + R1 + "\n" + R3),
    ("3 records, all EOR", HDR + "\n" + R1 + "\n" + R2 + "\n" + R3 + "\n"),
    ("3 records, last without EOR", HDR + "\n" + R1 + "\n" + R2 + "\n" + R3),
    ("3 records, no newlines at all", HDR + R1 + R2 + R3),
    ("3 records, EOR without NL separators", HDR + R1 + R2 + R3),
    ("2 records, CRLF", HDR + "\r\n" + R1 + "\r\n" + R2 + "\r\n"),
    ("3 records, CRLF, last no EOR", HDR + "\r\n" + R1 + "\r\n" + R2 + "\r\n" + R3),
    # revision 73443B15: markup handling
    ("2 records, '</EOR>' terminators", HDR + R1.replace("<EOR>", "</EOR>")
     + R2.replace("<EOR>", "</EOR>")),
    ("2 records, '<EOR/>' terminators", HDR + R1.replace("<EOR>", "<EOR/>")
     + R2.replace("<EOR>", "<EOR/>")),
    ("2 records, '</zzz>' between them", HDR + R1 + "</zzz>" + R2),
    ("2 records, '<zzz>' between them", HDR + R1 + "<zzz>" + R2),
    ("header + unknown-only record", HDR + R1 + "<ZZZ:3>abc<EOR>"),
    ("headerless unknown-only record", "<ZZZ:3>abc<OTHER:2>xy<EOR>"),
]


def main() -> None:
    print(f"module: {A.__file__}")
    for title, text in CASES:
        unknown: list = []
        recs = list(A.iter_records(text, unknown))
        qsos = [r for r in recs if r.get("CALL")]
        print(f"\n--- {title}")
        print(f"    records  : {recs}")
        print(f"    CALLs    : {[r.get('CALL') for r in qsos]}")
        if unknown:
            print(f"    unknown  : {unknown}")

    # write one file and run the real CLI path (ParseResult: records/header/unknown_tags)
    path = os.path.join(HERE, "cases", "_probe_parse_adif.adi")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(CASES[4][1])
    res = A.parse_adif(path)
    print(f"\nparse_adif -> records={len(res.records)} header={res.header} "
          f"unknown_tags={res.unknown_tags}")
    for r in res.records:
        print("   ", r)
    records, header, unknown_tags = A.parse_adif(path)      # tuple unpacking
    print(f"tuple unpack OK: {len(records)} records, {header}, {unknown_tags}")


if __name__ == "__main__":
    main()
