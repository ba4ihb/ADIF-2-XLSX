# -*- coding: utf-8 -*-
r"""G2 - header vs QSO classification (HEADER_FIELDS = ADIF_VER / PROGRAMID /
PROGRAMVERSION / CREATED_TIMESTAMP).

Run: python verification\cases_hdr.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (adif, dump, header_map, load, out_path, qso_rows,  # noqa: E402
                    record, run, write_case)

Q1 = adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
           ("BAND", "20M"), ("MODE", "SSB")])
Q2 = adif([("CALL", "K2DEF"), ("QSO_DATE", "20240102"), ("TIME_ON", "1300"),
           ("BAND", "40M"), ("MODE", "CW")])
HDRFIELDS = "<ADIF_VER:5>3.2.1<PROGRAMID:4>TEST<PROGRAMVERSION:5>1.2.3<CREATED_TIMESTAMP:15>20240101 120000"

CMD = "python adif2xlsx.py verification\\cases\\{f} -o verification\\out\\{o}"


def one(name, outname):
    path = write_case(name, CASE_TEXT[name]) if name in CASE_TEXT else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "cases", name)
    out = out_path(outname)
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    summary = ""
    if os.path.exists(out):
        wb = load(out)
        ws = wb["Summary"]
        for row in ws.iter_rows():
            if row[0].value == "ADIF version":
                summary = row[1].value
    return p, rows, summary


CASE_TEXT: dict[str, str] = {}


def g2a():
    CASE_TEXT["g2a_header_record.adi"] = HDRFIELDS + "<EOH>\n" + Q1 + "\n"
    p, rows, ver = one("g2a_header_record.adi", "g2a.xlsx")
    ok = (p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
          and "ADIF_VER" not in rows[0] and ver == "3.2.1")
    record("G2a header in its own record before <EOH>",
           "1 QSO; no ADIF_VER column; Summary ADIF version == 3.2.1",
           f"rc={p.returncode} rows={len(rows)} cols={sorted(rows[0]) if rows else []} summary_ver={ver!r}",
           ok, cmd=CMD.format(f="g2a_header_record.adi", o="g2a.xlsx"))


def g2b():
    CASE_TEXT["g2b_no_header.adi"] = Q1 + "\n" + Q2 + "\n"
    p, rows, ver = one("g2b_no_header.adi", "g2b.xlsx")
    ok = p.returncode == 0 and len(rows) == 2 and [r.get("CALL") for r in rows] == ["W1AW", "K2DEF"]
    record("G2b no header at all (records only)",
           "2 QSOs (W1AW, K2DEF)",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, cmd=CMD.format(f="g2b_no_header.adi", o="g2b.xlsx"))


def g2c():
    CASE_TEXT["g2c_no_eoh.adi"] = HDRFIELDS + "<EOR>\n" + Q1 + "\n" + Q2 + "\n"
    p, rows, ver = one("g2c_no_eoh.adi", "g2c.xlsx")
    ok = p.returncode == 0 and len(rows) == 2
    record("G2c no <EOH> (header record terminated by <EOR>)",
           "2 QSOs; header not counted",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, cmd=CMD.format(f="g2c_no_eoh.adi", o="g2c.xlsx"))


def g2d():
    CASE_TEXT["g2d_header_plus_qso.adi"] = HDRFIELDS + Q1 + "<EOR>\n" + Q2 + "\n"
    p, rows, ver = one("g2d_header_plus_qso.adi", "g2d.xlsx")
    ok = p.returncode == 0 and len(rows) == 2 and rows[0].get("CALL") == "W1AW"
    record("G2d header and first QSO share one record",
           "2 QSOs (the shared record's QSO survives)",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, note=f"summary ADIF version={ver!r} (header fields of a mixed record are dropped)",
           cmd=CMD.format(f="g2d_header_plus_qso.adi", o="g2d.xlsx"))


def g2e():
    CASE_TEXT["g2e_second_header.adi"] = (HDRFIELDS + "<EOH>\n" + Q1 + "\n"
                                          + HDRFIELDS + "<EOR>\n" + Q2 + "\n")
    p, rows, ver = one("g2e_second_header.adi", "g2e.xlsx")
    ok = p.returncode == 0 and len(rows) == 2 and all(r.get("CALL") for r in rows)
    record("G2e <EOH> then a second header-looking record later",
           "2 QSOs (W1AW, K2DEF); a header-only record is never a QSO",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, note="a record whose fields are ALL header fields is still emitted as a QSO row after the first header",
           cmd=CMD.format(f="g2e_second_header.adi", o="g2e.xlsx"))


def g2f():
    CASE_TEXT["g2f_header_eor_each.adi"] = ("<ADIF_VER:5>3.1.4<EOR>\n<PROGRAMID:4>LoTW<EOR>\n"
                                            "<EOH>\n" + Q1 + "\n")
    p, rows, ver = one("g2f_header_eor_each.adi", "g2f.xlsx")
    ok = p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
    record("G2f header fields each terminated by <EOR> before <EOH>",
           "1 QSO (W1AW)",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, note="the 2nd header field becomes a blank QSO row",
           cmd=CMD.format(f="g2f_header_eor_each.adi", o="g2f.xlsx"))


def g2g():
    """Header-only file: must be an error, not an empty workbook."""
    CASE_TEXT["g2g_header_only.adi"] = HDRFIELDS + "<EOH>\n"
    p, rows, ver = one("g2g_header_only.adi", "g2g.xlsx")
    ok = p.returncode != 0 and not os.path.exists(out_path("g2g.xlsx"))
    record("G2g header only, no QSOs",
           "non-zero exit + clear error, no workbook",
           f"rc={p.returncode} stderr={p.stderr.strip()!r} workbook={os.path.exists(out_path('g2g.xlsx'))}",
           ok, cmd=CMD.format(f="g2g_header_only.adi", o="g2g.xlsx"))


def g2h():
    """<EOH> present, no trailing <EOR> on the last record."""
    CASE_TEXT["g2h_eoh_no_eor.adi"] = HDRFIELDS + "<EOH>\n" + Q1   # no trailing EOR
    p, rows, ver = one("g2h_eoh_no_eor.adi", "g2h.xlsx")
    ok = p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
    record("G2h <EOH> then one QSO with no trailing <EOR>",
           "1 QSO (W1AW)", f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, cmd=CMD.format(f="g2h_eoh_no_eor.adi", o="g2h.xlsx"))


def main():
    for fn in (g2a, g2b, g2c, g2d, g2e, g2f, g2g, g2h):
        fn()
    dump("g2_header")


if __name__ == "__main__":
    main()
