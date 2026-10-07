# -*- coding: utf-8 -*-
r"""G4 - FREQ/BAND derivation against the ADIF band plan.

ADIF 3.1.7 band edges used as ground truth (MHz, inclusive):
    40M 7.000-7.300   20M 14.000-14.350   10M 28.000-29.700
    2M 144.000-148.000  (also 6M 50-54, 15M 21-21.45, 80M 3.5-4.0)

Run: python verification\cases_band.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (adif, dump, header_map, load, out_path, qso_rows,  # noqa: E402
                    record, run, write_case)

HDR = "<ADIF_VER:5>3.1.4<PROGRAMID:4>TEST<EOH>\n"
CMD = "python adif2xlsx.py verification\\cases\\g4_freq_band.adi -o verification\\out\\g4.xlsx"

# (call, freq_or_None, band_or_None, expected_band, expected_freq)
TABLE = [
    ("T01", "14.074", None, "20M", 14.074),
    ("T02", None, "40M", "40M", None),
    ("T03", "14.000", None, "20M", 14.000),
    ("T04", "14.350", None, "20M", 14.350),
    ("T05", "7.000", None, "40M", 7.000),
    ("T06", "7.300", None, "40M", 7.300),
    ("T07", "144.000", None, "2M", 144.000),
    ("T08", "148.000", None, "2M", 148.000),
    ("T09", "29.700", None, "10M", 29.700),
    ("T10", "15.5", None, "", 15.5),
    ("T11", "14.351", None, "", 14.351),
    ("T12", "6.999", None, "", 6.999),
    ("T13", "28.000", None, "10M", 28.000),
    ("T14", "14.100", "20M", "20M", 14.100),
    ("T15", "50.000", None, "6M", 50.000),
    ("T16", "21.450", None, "15M", 21.450),
    ("T17", "54.000", None, "5M", 54.000),          # lead-stated: shared edge resolves to 5M
    ("T18", "119980", None, "2.5MM", 119980.0),     # corrected 2.5mm lower edge
    ("T19", "149000", None, "2MM", 149000.0),       # corrected 2mm upper edge
    ("T20", "300000", None, "SUBMM", 300000.0),     # new submm band lower edge
    ("T21", "54.001", None, "5M", 54.001),
    ("T22", "53.999", None, "6M", 53.999),
]


def main():
    text = HDR
    for call, freq, band, _eb, _ef in TABLE:
        fields = [("CALL", call), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
                  ("MODE", "SSB"), ("STATION_CALLSIGN", "DL1AA")]
        if freq is not None:
            fields.append(("FREQ", freq))
        if band is not None:
            fields.append(("BAND", band))
        text += adif(fields) + "\n"
    path = write_case("g4_freq_band.adi", text)
    out = out_path("g4.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    if len(rows) != len(TABLE):
        record("G4 FREQ/BAND table row count", f"{len(TABLE)} rows",
               f"rc={p.returncode} rows={len(rows)}", False, cmd=CMD)
        dump("g4_band")
        return
    by_call = {r.get("CALL"): r for r in rows}
    fmt_ok = True
    if os.path.exists(out):
        ws = load(out)["QSOs"]
        hdr = header_map(ws)
        for r in range(2, ws.max_row + 1):
            c = ws.cell(row=r, column=hdr["FREQ_MHZ"])
            if c.value is not None and not str(c.number_format).startswith("0.000"):
                fmt_ok = False
    bad = []
    for call, freq, band, eb, ef in TABLE:
        row = by_call.get(call, {})
        got_band = row.get("BAND") or ""          # empty cells read back as None
        got_freq = row.get("FREQ_MHZ")
        if got_band != eb or (got_freq != ef):
            bad.append((call, freq, band, f"band {got_band!r} (want {eb!r})",
                        f"freq {got_freq!r} (want {ef!r})"))
    record("G4 band derivation table (22 frequencies/edges incl. out-of-band)",
           "every FREQ-derived BAND matches the ADIF band plan incl. 54.000->5M, "
           "119980->2.5MM, 149000->2MM, 300000->SUBMM; explicit BAND preserved; "
           "out-of-band FREQ yields NO band; FREQ_MHZ numeric with a 0.000* format",
           f"rc={p.returncode} rows={len(rows)} mismatches={bad} freq_fmt_ok={fmt_ok}",
           not bad and fmt_ok and p.returncode == 0, cmd=CMD)

    # explicit BAND with no FREQ must leave the frequency empty
    t02 = by_call.get("T02", {})
    record("G4b BAND without FREQ keeps BAND and leaves FREQ_MHZ empty",
           "BAND == '40M', FREQ_MHZ is None",
           f"BAND={t02.get('BAND')!r} FREQ_MHZ={t02.get('FREQ_MHZ')!r}",
           t02.get("BAND") == "40M" and t02.get("FREQ_MHZ") is None, cmd=CMD)

    t10 = by_call.get("T10", {})
    record("G4c out-of-band 15.5 MHz must not get a bogus band",
           "BAND == '' (empty), FREQ_MHZ == 15.5",
           f"BAND={t10.get('BAND')!r} FREQ_MHZ={t10.get('FREQ_MHZ')!r}",
           t10.get("BAND") in ("", None) and t10.get("FREQ_MHZ") == 15.5, cmd=CMD)

    # the workbook must not invent a band for the out-of-band row in Summary
    if os.path.exists(out):
        wb = load(out)
        summary = wb["Summary"]
        body = " ".join(str(c.value) for row in summary.iter_rows() for c in row)
        record("G4d Summary shows a '(none)' band bucket for the out-of-band QSO",
               "'(none)' present in the BAND breakdown (no invented band)",
               f"'none' in summary: {'(none)' in body}",
               "(none)" in body, cmd=CMD)

    dump("g4_band")


if __name__ == "__main__":
    main()
