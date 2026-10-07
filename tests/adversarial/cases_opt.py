# -*- coding: utf-8 -*-
r"""G5 - optional-field auto-detection and SOURCE_FILE provenance.

Run: python verification\cases_opt.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (adif, dump, header_map, load, out_path, qso_rows,  # noqa: E402
                    record, run, write_case)

HDR = "<ADIF_VER:5>3.1.4<PROGRAMID:4>TEST<EOH>\n"
CMD = "python adif2xlsx.py verification\\cases\\{f} -o verification\\out\\{o}"


def one(name, text, outname):
    path = write_case(name, text)
    out = out_path(outname)
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    hdr = header_map(load(out)["QSOs"]) if os.path.exists(out) else {}
    return p, rows, hdr


def g5a_single_record_field():
    """A field present in exactly ONE record must still become a column."""
    text = (HDR
            + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
                    ("MY_ANTENNA", "Yagi"), ("APP_MYLOG_SCORE", "17"),
                    ("COMMENT", "only here")]) + "\n"
            + adif([("CALL", "K2DEF"), ("QSO_DATE", "20240102"), ("TIME_ON", "1300")]) + "\n")
    p, rows, hdr = one("g5a_rare_field.adi", text, "g5a.xlsx")
    missing = [c for c in ("MY_ANTENNA", "APP_MYLOG_SCORE", "COMMENT") if c not in hdr]
    got = rows[0] if rows else {}
    empty2 = {c: rows[1].get(c) for c in ("MY_ANTENNA", "APP_MYLOG_SCORE", "COMMENT")} if len(rows) > 1 else {}
    ok = (p.returncode == 0 and not missing
          and got.get("MY_ANTENNA") == "Yagi" and got.get("APP_MYLOG_SCORE") == "17"
          and got.get("COMMENT") == "only here"
          and all(v is None for v in empty2.values()))
    record("G5a field present in only ONE record becomes a column (others empty)",
           "MY_ANTENNA / APP_MYLOG_SCORE / COMMENT columns exist; row1 populated; row2 empty",
           f"rc={p.returncode} missing_columns={missing} row1={got.get('MY_ANTENNA')!r}/{got.get('APP_MYLOG_SCORE')!r}/{got.get('COMMENT')!r} row2={empty2}",
           ok, cmd=CMD.format(f="g5a_rare_field.adi", o="g5a.xlsx"))


def g5b_all_empty_field():
    """A field that is empty in EVERY record must produce no column."""
    text = (HDR
            + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<COMMENT:0><SRX:0><NOTES:0><EOR>\n"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<COMMENT:0><SRX:0><NOTES:0><EOR>\n")
    p, rows, hdr = one("g5b_empty_field.adi", text, "g5b.xlsx")
    bad = [c for c in ("COMMENT", "SRX", "NOTES") if c in hdr]
    ok = p.returncode == 0 and len(rows) == 2 and not bad
    record("G5b field empty in EVERY record produces NO column",
           "no COMMENT / SRX / NOTES column; 2 QSOs",
           f"rc={p.returncode} rows={len(rows)} columns={sorted(hdr)}",
           ok, cmd=CMD.format(f="g5b_empty_field.adi", o="g5b.xlsx"))


def g5c_source_file_merge():
    """SOURCE_FILE must name the origin file when several files are merged."""
    a = write_case("g5c_alpha.adi", HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"),
                                                ("TIME_ON", "1200")]) + "\n")
    b = write_case("g5c_beta.adi", HDR + adif([("CALL", "K2DEF"), ("QSO_DATE", "20240102"),
                                               ("TIME_ON", "1300")]) + "\n")
    out = out_path("g5c.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([a, b, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    per = [(r.get("CALL"), r.get("SOURCE_FILE")) for r in rows]
    ok = (p.returncode == 0 and per == [("W1AW", "g5c_alpha.adi"), ("K2DEF", "g5c_beta.adi")])
    record("G5c SOURCE_FILE identifies the origin file when merging two files",
           "[('W1AW', 'g5c_alpha.adi'), ('K2DEF', 'g5c_beta.adi')]", f"rc={p.returncode} got={per}",
           ok, cmd="python adif2xlsx.py verification\\cases\\g5c_alpha.adi verification\\cases\\g5c_beta.adi -o verification\\out\\g5c.xlsx")


def g5d_duplicate_basenames():
    """Same basename in two folders must stay distinguishable in SOURCE_FILE."""
    d1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases", "g5d_one")
    d2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases", "g5d_two")
    os.makedirs(d1, exist_ok=True)
    os.makedirs(d2, exist_ok=True)
    for d, call, day in ((d1, "W1AW", "20240101"), (d2, "K2DEF", "20240102")):
        with open(os.path.join(d, "log.adi"), "w", encoding="utf-8", newline="") as fh:
            fh.write(HDR + adif([("CALL", call), ("QSO_DATE", day), ("TIME_ON", "1200")]) + "\n")
    out = out_path("g5d.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([d1, d2, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    labels = [r.get("SOURCE_FILE") for r in rows]
    ok = p.returncode == 0 and len(rows) == 2 and len(set(labels)) == 2
    record("G5d two different folders each containing log.adi",
           "2 QSOs with two DISTINCT SOURCE_FILE labels",
           f"rc={p.returncode} rows={len(rows)} labels={labels}",
           ok, cmd="python adif2xlsx.py verification\\cases\\g5d_one verification\\cases\\g5d_two -o verification\\out\\g5d.xlsx")


def g5e_mixed_empty_and_full():
    """Field empty in one record, populated in the other -> column kept."""
    text = (HDR
            + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<COMMENT:0><EOR>\n"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<COMMENT:5>hello<EOR>\n")
    p, rows, hdr = one("g5e_mixed_empty.adi", text, "g5e.xlsx")
    ok = (p.returncode == 0 and "COMMENT" in hdr and len(rows) == 2
          and rows[0].get("COMMENT") is None and rows[1].get("COMMENT") == "hello")
    record("G5e field empty in one record, populated in the other",
           "COMMENT column kept; row1 empty, row2 'hello'",
           f"rc={p.returncode} columns={sorted(hdr)} values={[r.get('COMMENT') for r in rows]}",
           ok, cmd=CMD.format(f="g5e_mixed_empty.adi", o="g5e.xlsx"))


def main():
    for fn in (g5a_single_record_field, g5b_all_empty_field, g5c_source_file_merge,
               g5d_duplicate_basenames, g5e_mixed_empty_and_full):
        fn()
    dump("g5_optional")


if __name__ == "__main__":
    main()
