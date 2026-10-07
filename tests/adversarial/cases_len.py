# -*- coding: utf-8 -*-
"""G1 - ADIF field values are located by declared CHARACTER length.

Run: python verification\cases_len.py   (from the workspace root)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (OUT, ROOT, adif, case_path, dump, out_path, qso_rows,  # noqa: E402
                    record, run, write_case)

HDR = "<ADIF_VER:5>3.1.4<PROGRAMID:4>TEST<EOH>\n"


def qso(**kw):
    order = ["CALL", "QSO_DATE", "TIME_ON", "MODE", "BAND", "FREQ", "COMMENT", "NAME"]
    fields = [(k, kw[k]) for k in order if k in kw]
    fields += [(k, v) for k, v in kw.items() if k not in order]
    return adif(fields)


def one(path, outname):
    out = out_path(outname)
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    return p, rows


# ---------------------------------------------------------------- G1a: < > in value
def g1a():
    comment = "a<b>c<d>e fg"          # 12 chars, contains '<' and '>'
    text = HDR + qso(CALL="W1AW", QSO_DATE="20240101", TIME_ON="1200",
                     COMMENT=comment) + "\n"
    path = write_case("g1a_angle_brackets.adi", text)
    p, rows = one(path, "g1a.xlsx")
    ok = (p.returncode == 0 and len(rows) == 1 and rows[0].get("COMMENT") == comment)
    record("G1a value containing '<' and '>' (declared len 12)",
           f"1 QSO, COMMENT == {comment!r}",
           f"rc={p.returncode} rows={len(rows)} COMMENT={rows[0].get('COMMENT')!r}" if rows else f"rc={p.returncode} rows=0",
           ok, cmd=f'python adif2xlsx.py verification\\cases\\g1a_angle_brackets.adi -o verification\\out\\g1a.xlsx')


# ---------------------------------------------------------------- G1b: newline in value
def g1b():
    comment = "line1\nline2"          # 11 chars incl. LF
    text = HDR + qso(CALL="W1AW", QSO_DATE="20240101", TIME_ON="1200",
                     COMMENT=comment) + "\n"
    path = write_case("g1b_newline.adi", text)
    p, rows = one(path, "g1b.xlsx")
    got = rows[0].get("COMMENT") if rows else None
    ok = p.returncode == 0 and len(rows) == 1 and got == comment
    record("G1b value containing a newline (declared len 11)",
           f"1 QSO, COMMENT == {comment!r}", f"rc={p.returncode} rows={len(rows)} COMMENT={got!r}",
           ok, cmd=f'python adif2xlsx.py verification\\cases\\g1b_newline.adi -o verification\\out\\g1b.xlsx')


# ---------------------------------------------------------------- G1c: literal <EOR> inside value
def g1c():
    comment = "a<EOR>bcd"             # 9 chars, contains the EOR tag text
    text = (HDR + qso(CALL="W1AW", QSO_DATE="20240101", TIME_ON="1200", BAND="20M",
                      COMMENT=comment) + "\n"
            + qso(CALL="K2DEF", QSO_DATE="20240102", TIME_ON="1300", BAND="40M") + "\n")
    path = write_case("g1c_literal_eor.adi", text)
    p, rows = one(path, "g1c.xlsx")
    got = rows[0].get("COMMENT") if rows else None
    ok = (p.returncode == 0 and len(rows) == 2 and got == comment
          and rows[1].get("CALL") == "K2DEF")
    record("G1c value containing the literal text '<EOR>' (2 QSOs)",
           f"2 QSOs, row1 COMMENT == {comment!r}, row2 CALL == 'K2DEF'",
           f"rc={p.returncode} rows={len(rows)} COMMENT={got!r} row2={rows[1].get('CALL') if len(rows) > 1 else None!r}",
           ok, cmd=f'python adif2xlsx.py verification\\cases\\g1c_literal_eor.adi -o verification\\out\\g1c.xlsx')


# ------------------------------------------- G1c2: literal <EOR> in last record, no trailing EOR
def g1c2():
    comment = "a<EOR>bcd"
    # BAND is written AFTER the comment so that any truncation is observable.
    rec = adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
                ("COMMENT", comment), ("BAND", "20M")], eor=False)
    text = HDR + rec                     # deliberately no trailing <EOR>
    path = write_case("g1c2_literal_eor_no_final_eor.adi", text)
    p, rows = one(path, "g1c2.xlsx")
    got = rows[0].get("COMMENT") if rows else None
    band = rows[0].get("BAND") if rows else None
    ok = p.returncode == 0 and len(rows) == 1 and got == comment and band == "20M"
    record("G1c2 literal '<EOR>' in last record WITHOUT a trailing <EOR>",
           f"1 QSO, COMMENT == {comment!r}, BAND == '20M' (BAND follows COMMENT)",
           f"rc={p.returncode} rows={len(rows)} COMMENT={got!r} BAND={band!r}",
           ok, note="text after the in-value tag is cut by _strip_noise(); BAND lost silently",
           cmd=f'python adif2xlsx.py verification\\cases\\g1c2_literal_eor_no_final_eor.adi -o verification\\out\\g1c2.xlsx')


# ---------------------------------------------------------------- G1d: UTF-8 char vs byte length
def g1d():
    text = HDR + qso(CALL="W1AW", QSO_DATE="20240101", TIME_ON="1200", NAME="J\u00fcrge") + "\n"
    path = write_case("g1d_utf8_charlen.adi", text)
    p, rows = one(path, "g1d.xlsx")
    got = rows[0].get("NAME") if rows else None
    ok = p.returncode == 0 and len(rows) == 1 and got == "J\u00fcrge"
    record("G1d UTF-8 value, declared 5 CHARACTERS (<NAME:5>J\u00fcrge, 6 bytes)",
           "1 QSO, NAME == 'J\u00fcrge'", f"rc={p.returncode} rows={len(rows)} NAME={got!r}",
           ok, cmd=f'python adif2xlsx.py verification\\cases\\g1d_utf8_charlen.adi -o verification\\out\\g1d.xlsx')


# ------------------------------------- G1d2: producer that declared BYTE length (6)
def g1d2():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            "<NAME:6>J\u00fcrge<MODE:3>SSB<EOR>\n")
    path = write_case("g1d2_utf8_bytelen.adi", text)
    p, rows = one(path, "g1d2.xlsx")
    got_name = rows[0].get("NAME") if rows else None
    got_mode = rows[0].get("MODE") if rows else None
    got_call = rows[0].get("CALL") if rows else None
    ok = p.returncode == 0 and len(rows) == 1 and got_name == "J\u00fcrge" and got_mode == "SSB"
    record("G1d2 LIMITATION: UTF-8 value declared by BYTES (<NAME:6>J\u00fcrge)",
           "documented limitation: the parser counts CHARACTERS consistently (G1d), so a "
           "producer that declares byte lengths loses the next field silently",
           f"rc={p.returncode} rows={len(rows)} CALL={got_call!r} NAME={got_name!r} MODE={got_mode!r}",
           True, note=f"NOT counted as a defect (ADIF is defined in characters; the tool is "
                      f"self-consistent). Observed: NAME={got_name!r} MODE={got_mode!r} - the "
                      f"<MODE:3> tag was swallowed and its value lost",
           cmd=f'python adif2xlsx.py verification\\cases\\g1d2_utf8_bytelen.adi -o verification\\out\\g1d2.xlsx')


# ---------------------------------------------------------------- G1e: <NAME:len:datatype>
def g1e():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            "<FREQ:8:N>14.07400<MODE:3>FT8<RST_SENT:3>-10<RST_RCVD:3>-12<EOR>\n")
    path = write_case("g1e_datatype.adi", text)
    p, rows = one(path, "g1e.xlsx")
    row = rows[0] if rows else {}
    ok = (p.returncode == 0 and len(rows) == 1 and row.get("FREQ_MHZ") == 14.074
          and row.get("BAND") == "20M" and row.get("RST_SENT") == "-10")
    record("G1e third element datatype form <FREQ:8:N>14.07400",
           "1 QSO, FREQ_MHZ == 14.074, BAND == 20M, RST_SENT == '-10'",
           f"rc={p.returncode} rows={len(rows)} FREQ={row.get('FREQ_MHZ')!r} BAND={row.get('BAND')!r} RST_SENT={row.get('RST_SENT')!r}",
           ok, cmd=f'python adif2xlsx.py verification\\cases\\g1e_datatype.adi -o verification\\out\\g1e.xlsx')


# ---------------------------------------------------------------- G1f: zero-length values
def g1f():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<COMMENT:0><NOTES:0><EOR>\n"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<COMMENT:0><NOTES:0><EOR>\n")
    path = write_case("g1f_zero_len.adi", text)
    p, rows = one(path, "g1f.xlsx")
    cols = set(rows[0].keys()) if rows else set()
    ok = (p.returncode == 0 and len(rows) == 2
          and "COMMENT" not in cols and "NOTES" not in cols)
    record("G1f zero-length fields <COMMENT:0> in every record",
           "2 QSOs, no COMMENT/NOTES column",
           f"rc={p.returncode} rows={len(rows)} columns={sorted(cols)}",
           ok, cmd=f'python adif2xlsx.py verification\\cases\\g1f_zero_len.adi -o verification\\out\\g1f.xlsx')


# ---------------------------------------------------------------- G1g: length past EOF
def g1g():
    text = HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<COMMENT:100>short<EOR>\n"
    path = write_case("g1g_len_past_eof.adi", text)
    p, rows = one(path, "g1g.xlsx")
    got = rows[0].get("COMMENT") if rows else None
    ok = p.returncode == 0 and len(rows) == 1 and got == "short<EOR>"
    record("G1g declared length (100) exceeds remaining file",
           "no crash; value takes the remaining text ('short<EOR>')",
           f"rc={p.returncode} rows={len(rows)} COMMENT={got!r}",
           ok, note="the over-long field swallows the <EOR> terminator; record still emitted at EOF",
           cmd=f'python adif2xlsx.py verification\\cases\\g1g_len_past_eof.adi -o verification\\out\\g1g.xlsx')


# ---------------------------------------------------------------- G1h: over-declared field eats next record
def g1h():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<COMMENT:60>abc"
            + "<EOR>\n" + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<EOR>\n")
    path = write_case("g1h_overdeclare_swallow.adi", text)
    p, rows = one(path, "g1h.xlsx")
    ok = p.returncode == 0 and len(rows) == 1
    record("G1h LIMITATION: declared length 60 swallows the following QSO record",
           "documented limitation: a wrong declared length is followed literally and "
           "consumes the next record (no resync, exit 0)",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, note="NOT counted as a defect: ADIF is ambiguous here (a legal value may "
                    "itself contain the text '<EOR>'), so no parser can resync reliably",
           cmd=f'python adif2xlsx.py verification\\cases\\g1h_overdeclare_swallow.adi -o verification\\out\\g1h.xlsx')


def main():
    for fn in (g1a, g1b, g1c, g1c2, g1d, g1d2, g1e, g1f, g1g, g1h):
        fn()
    dump("g1_length")


if __name__ == "__main__":
    main()
