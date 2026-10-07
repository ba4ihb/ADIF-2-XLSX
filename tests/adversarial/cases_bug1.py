# -*- coding: utf-8 -*-
r"""Bug-1 quantification (lead request): the length-unaware terminator scan.

Cases:
  b1a  LAST record, no trailing <EOR>, a value contains the literal "<EOR>"
       -> which fields are lost?
  b1b  same record WITH a trailing <EOR>                      (control: must be fine)
  b1c  "<EOR>" inside a value of a NON-last record             (control: must be fine)
  b1d  "<EOH>" in prose inside the last value, no trailing EOR
  b1e  "<EOD>" inside the last value, no trailing EOR
  b1f  preamble prose containing "<EOH>" before the real header/QSOs
  b1g  preamble prose containing "<EOR>" before the real header/QSOs
  b1h  single record, no terminator of any kind anywhere
  b1i  two records, only the LAST lacks a trailing <EOR>       (must be fine)

Run: python verification\cases_bug1.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import dump, out_path, qso_rows, record, run, write_case  # noqa: E402

HDR = "<ADIF_VER:5>3.1.4<EOH>\n"
CALL1 = "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>\n"

# Records are built with real declared lengths (a 5-char call must be <CALL:5>).
CALL2_HEAD = "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300"
CALL3_HEAD = "<CALL:5>N3XYZ<QSO_DATE:8>20240103<TIME_ON:4>1400"
# Fields deliberately ordered so that everything after COMMENT is only
# reachable if the parser survives the in-value terminator text.
TAIL = "<BAND:3>20M<MODE:3>SSB<RST_SENT:2>59<STATION_CALLSIGN:5>DL1AA<FREQ:6>14.074"

CMD = "python adif2xlsx.py verification\\cases\\{f} -o verification\\out\\{o}"


def one(name, text, outname, binary=False):
    path = write_case(name, text, binary=binary)
    out = out_path(outname)
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    return p, rows


def expect_fields(row, expected: dict) -> list:
    return [f"{k}={v!r} but got {row.get(k)!r}" for k, v in expected.items()
            if row.get(k) != v]


def b1a():
    text = (HDR + CALL1
            + CALL2_HEAD + "<COMMENT:9>a<EOR>bcd"
            + TAIL)                                   # no trailing <EOR>
    p, rows = one("b1a_last_record_no_eor.adi", text, "b1a.xlsx")
    r = rows[-1] if rows else {}
    exp = {"CALL": "K2DEF", "COMMENT": "a<EOR>bcd", "BAND": "20M", "MODE": "SSB",
           "RST_SENT": "59", "STATION_CALLSIGN": "DL1AA", "FREQ_MHZ": 14.074}
    bad = expect_fields(r, exp)
    ok = p.returncode == 0 and len(rows) == 2 and not bad
    record("B1a LAST record, no trailing <EOR>, value contains '<EOR>'",
           f"2 QSOs; record 2 complete: {sorted(exp)}",
           f"rc={p.returncode} rows={len(rows)} record2={ {k: r.get(k) for k in ('CALL','COMMENT','BAND','MODE','RST_SENT','STATION_CALLSIGN','FREQ_MHZ')} } "
           f"lost_fields={bad}",
           ok, note="every field written after the value is discarded; COMMENT itself is "
                    "truncated to the text before the in-value tag",
           cmd=CMD.format(f="b1a_last_record_no_eor.adi", o="b1a.xlsx"))


def b1b():
    text = (HDR + CALL1
            + CALL2_HEAD + "<COMMENT:9>a<EOR>bcd"
            + TAIL + "<EOR>\n")                        # trailing <EOR> present
    p, rows = one("b1b_last_record_with_eor.adi", text, "b1b.xlsx")
    r = rows[-1] if rows else {}
    exp = {"CALL": "K2DEF", "COMMENT": "a<EOR>bcd", "BAND": "20M", "MODE": "SSB",
           "RST_SENT": "59", "STATION_CALLSIGN": "DL1AA", "FREQ_MHZ": 14.074}
    bad = expect_fields(r, exp)
    ok = p.returncode == 0 and len(rows) == 2 and not bad
    record("B1b control: same value, LAST record WITH a trailing <EOR>",
           "2 QSOs; record 2 complete (value keeps its '<EOR>' text)",
           f"rc={p.returncode} rows={len(rows)} mismatches={bad}", ok,
           cmd=CMD.format(f="b1b_last_record_with_eor.adi", o="b1b.xlsx"))


def b1c():
    text = (HDR
            + CALL2_HEAD + "<COMMENT:9>a<EOR>bcd"
            + TAIL + "<EOR>\n" + CALL1)                # offending record is NOT last
    p, rows = one("b1c_mid_record_eor.adi", text, "b1c.xlsx")
    r = rows[0] if rows else {}
    exp = {"CALL": "K2DEF", "COMMENT": "a<EOR>bcd", "BAND": "20M", "MODE": "SSB",
           "RST_SENT": "59", "STATION_CALLSIGN": "DL1AA", "FREQ_MHZ": 14.074}
    bad = expect_fields(r, exp)
    ok = p.returncode == 0 and len(rows) == 2 and not bad
    record("B1c control: '<EOR>' inside a value of a NON-last record",
           "2 QSOs; record 1 complete",
           f"rc={p.returncode} rows={len(rows)} mismatches={bad}", ok,
           cmd=CMD.format(f="b1c_mid_record_eor.adi", o="b1c.xlsx"))


def b1d():
    text = (HDR + CALL1
            + CALL2_HEAD
            + "<COMMENT:20>see <EOH> in point 3" + TAIL)
    p, rows = one("b1d_eoh_in_value.adi", text, "b1d.xlsx")
    r = rows[-1] if rows else {}
    exp = {"CALL": "K2DEF", "COMMENT": "see <EOH> in point 3", "BAND": "20M",
           "RST_SENT": "59", "FREQ_MHZ": 14.074}
    bad = expect_fields(r, exp)
    ok = p.returncode == 0 and len(rows) == 2 and not bad
    record("B1d LAST record, no trailing <EOR>, value contains '<EOH>' in prose",
           "2 QSOs; record 2 complete", f"rc={p.returncode} rows={len(rows)} lost={bad}",
           ok, note="same root cause, different tag",
           cmd=CMD.format(f="b1d_eoh_in_value.adi", o="b1d.xlsx"))


def b1e():
    text = (HDR + CALL1
            + CALL2_HEAD
            + "<COMMENT:15>stop <EOD> stop" + TAIL)
    p, rows = one("b1e_eod_in_value.adi", text, "b1e.xlsx")
    r = rows[-1] if rows else {}
    exp = {"CALL": "K2DEF", "COMMENT": "stop <EOD> stop", "BAND": "20M",
           "RST_SENT": "59", "FREQ_MHZ": 14.074}
    bad = expect_fields(r, exp)
    ok = p.returncode == 0 and len(rows) == 2 and not bad
    record("B1e LAST record, no trailing <EOR>, value contains '<EOD>'",
           "2 QSOs; record 2 complete", f"rc={p.returncode} rows={len(rows)} lost={bad}",
           ok, cmd=CMD.format(f="b1e_eod_in_value.adi", o="b1e.xlsx"))


def b1f():
    text = ("Exported by MyLogger -- see the <EOH> section of the manual.\n"
            + HDR + CALL1)
    p, rows = one("b1f_preamble_eoh.adi", text, "b1f.xlsx")
    r = rows[0] if rows else {}
    ok = p.returncode == 0 and len(rows) == 1 and r.get("CALL") == "W1AW" and r.get("MODE") == "SSB"
    record("B1f preamble prose containing '<EOH>' before the real header",
           "1 QSO (W1AW, MODE SSB)",
           f"rc={p.returncode} rows={len(rows)} row={ {k: r.get(k) for k in ('CALL','MODE','QSO_DATE')} }",
           ok, note="probe for the new preamble-skip logic",
           cmd=CMD.format(f="b1f_preamble_eoh.adi", o="b1f.xlsx"))


def b1g():
    text = ("Note: previous export ended here <EOR> ignore this line.\n"
            + HDR + CALL1)
    p, rows = one("b1g_preamble_eor.adi", text, "b1g.xlsx")
    r = rows[0] if rows else {}
    ok = p.returncode == 0 and len(rows) == 1 and r.get("CALL") == "W1AW"
    record("B1g preamble prose containing '<EOR>' before the real header",
           "1 QSO (W1AW)", f"rc={p.returncode} rows={len(rows)} calls={[x.get('CALL') for x in rows]}",
           ok, cmd=CMD.format(f="b1g_preamble_eor.adi", o="b1g.xlsx"))


def b1h():
    text = HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB"
    p, rows = one("b1h_single_no_terminator.adi", text, "b1h.xlsx")
    r = rows[0] if rows else {}
    ok = p.returncode == 0 and len(rows) == 1 and r.get("CALL") == "W1AW" and r.get("MODE") == "SSB"
    record("B1h single QSO, no <EOR>/<EOD> anywhere in the file",
           "1 QSO complete (lenient producer: omitted final terminator)",
           f"rc={p.returncode} rows={len(rows)} row={ {k: r.get(k) for k in ('CALL','MODE')} }",
           ok, cmd=CMD.format(f="b1h_single_no_terminator.adi", o="b1h.xlsx"))


def b1i():
    text = (HDR + CALL1
            + CALL2_HEAD + "<MODE:2>CW<EOR>\n"
            + CALL3_HEAD + "<MODE:3>FT8")
    p, rows = one("b1i_only_last_lacks_eor.adi", text, "b1i.xlsx")
    ok = (p.returncode == 0 and len(rows) == 3
          and [r.get("CALL") for r in rows] == ["W1AW", "K2DEF", "N3XYZ"]
          and rows[2].get("MODE") == "FT8")
    record("B1i three records, only the last lacks a trailing <EOR>",
           "3 QSOs, last one complete",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]} last_mode={rows[-1].get('MODE') if rows else None!r}",
           ok, cmd=CMD.format(f="b1i_only_last_lacks_eor.adi", o="b1i.xlsx"))


def main():
    for fn in (b1a, b1b, b1c, b1d, b1e, b1f, b1g, b1h, b1i):
        fn()
    dump("b1_terminator")


if __name__ == "__main__":
    main()
