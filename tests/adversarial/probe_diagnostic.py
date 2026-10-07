# -*- coding: utf-8 -*-
r"""Probe: the 'exported fields' set is built with the dict key/value swapped.

REQUIRED_COLUMNS maps EXCEL COLUMN -> ADIF FIELD.  build_rows() iterates
`for adif_name, column in REQUIRED_COLUMNS.items()` and then tests
`if adif_name in rec` / `exported.add(column)` - so it tests the COLUMN name
against the record and stores the ADIF name in `exported`.  Where the two names
differ (TIME_ON_UTC/TIME_ON, FREQ_MHZ/FREQ, TIME_OFF_UTC/TIME_OFF) the column
can never be matched again, so an unparseable value is never diagnosed.

Run: python verification\probe_diagnostic.py
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import adif2xlsx as A  # noqa: E402

CASES = {
    "invalid TIME_ON (256099), valid everything else": (
        "<ADIF_VER:5>3.1.4<EOH>"
        "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:6>256099<MODE:3>SSB"
        "<STATION_CALLSIGN:5>DL1AA<EOR>"),
    "invalid QSO_DATE (20241340) [names coincide]": (
        "<ADIF_VER:5>3.1.4<EOH>"
        "<CALL:4>W1AW<QSO_DATE:8>20241340<TIME_ON:4>1200<MODE:3>SSB"
        "<STATION_CALLSIGN:5>DL1AA<EOR>"),
    "unparseable FREQ (abc) with no BAND": (
        "<ADIF_VER:5>3.1.4<EOH>"
        "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB"
        "<STATION_CALLSIGN:5>DL1AA<FREQ:3>abc<EOR>"),
    "unparseable FREQ (abc) with an explicit BAND": (
        "<ADIF_VER:5>3.1.4<EOH>"
        "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB"
        "<STATION_CALLSIGN:5>DL1AA<BAND:3>20M<FREQ:3>abc<EOR>"),
}


def main() -> None:
    print("REQUIRED_COLUMNS =", dict(A.REQUIRED_COLUMNS))
    for title, text in CASES.items():
        path = os.path.join(HERE, "cases", "_diag.adi")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        res = A.parse_adif(path)
        out = A.build_rows([(path, res.records, res.header, res.unknown_tags)])
        row = out.rows[0] if out.rows else {}
        print(f"\n--- {title}")
        print(f"    incomplete = {out.incomplete}")
        print(f"    CALL={row.get('CALL')!r} QSO_DATE={row.get('QSO_DATE')!r} "
              f"TIME_ON_UTC={row.get('TIME_ON_UTC')!r} FREQ_MHZ={row.get('FREQ_MHZ')!r} "
              f"BAND={row.get('BAND')!r}")


if __name__ == "__main__":
    main()
