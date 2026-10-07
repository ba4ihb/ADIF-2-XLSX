# -*- coding: utf-8 -*-
r"""P-group - probes for defects introduced by the frozen parser rewrite.

The frozen revision (369026D8...) deleted `_strip_noise()` and rewrote the
control flow: "preamble is skipped positionally ... parsing stops at the first
unrecognised tag after real data has been seen", and parse_adif() now rejects a
file with no QSO record or fewer than 2 data fields.

These cases attack exactly those new rules.

Run: python verification\cases_parser.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, dump, out_path, qso_rows, record, run, write_case  # noqa: E402

HDR = "<ADIF_VER:5>3.1.4<EOH>\n"


def q(call, day, extra=""):
    return (f"<CALL:{len(call)}>{call}<QSO_DATE:8>{day}<TIME_ON:4>1200"
            f"<MODE:3>SSB{extra}<EOR>\n")


def one(name, text, outname, binary=False):
    path = write_case(name, text, binary=binary)
    out = out_path(outname)
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    return p, rows, out, path


def cmd_for(path, out):
    rp = os.path.relpath(path, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ro = os.path.relpath(out, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return f"python adif2xlsx.py {rp} -o {ro}"


def p1_unknown_tag_midfile():
    """An unrecognised tag between two records must not eat the rest of the file."""
    text = (HDR + q("W1AW", "20240101") + "<MYSTERY:3>abc\n" + q("K2DEF", "20240102")
            + q("N3XYZ", "20240103"))
    p, rows, out, path = one("p1_unknown_tag_midfile.adi", text, "p1.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF", "N3XYZ"]
    record("P1 unrecognised tag '<MYSTERY:3>abc' between records",
           "3 QSOs (unknown fields are auto-detected, nothing after them is dropped)",
           f"rc={p.returncode} rows={len(rows)} calls={calls} stderr={p.stderr.strip()[:120]!r}",
           ok, note="'parsing stops at the first unrecognised tag' would silently truncate here",
           cmd=cmd_for(path, out))


def p2_bare_tag_midfile():
    """A tag with no length ('<NOTE>') between records."""
    text = (HDR + q("W1AW", "20240101") + "<NOTE>\n" + q("K2DEF", "20240102"))
    p, rows, out, path = one("p2_bare_tag_midfile.adi", text, "p2.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("P2 bare tag '<NOTE>' (no length) between records",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}",
           ok, cmd=cmd_for(path, out))


def p3_free_text_midfile():
    """Free text (no tag at all) between records."""
    text = (HDR + q("W1AW", "20240101") + "--- end of first batch ---\n"
            + q("K2DEF", "20240102"))
    p, rows, out, path = one("p3_freetext_midfile.adi", text, "p3.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("P3 free text line between two records",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}",
           ok, cmd=cmd_for(path, out))


def p4_trailing_junk_after_records():
    text = (HDR + q("W1AW", "20240101") + "\n<EOF> thanks for using MyLogger\n")
    p, rows, out, path = one("p4_trailing_junk.adi", text, "p4.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW"]
    record("P4 trailing junk/tag after the last record",
           "1 QSO", f"rc={p.returncode} rows={len(rows)} calls={calls}",
           ok, cmd=cmd_for(path, out))


def p5_one_data_field():
    text = HDR + "<CALL:4>W1AW<EOR>\n"
    p, rows, out, path = one("p5_one_field.adi", text, "p5.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and len(rows) == 1 and calls == ["W1AW"]
    record("P5 file with a single data field (<CALL:4>W1AW<EOR>)",
           "1 QSO accepted (73443B15 vocabulary rule: CALL is a known field name)",
           f"rc={p.returncode} workbook={os.path.exists(out)} rows={len(rows)} calls={calls} "
           f"stderr={p.stderr.strip()[:120]!r}",
           ok, note="changed from rc=1 'no ADIF QSO records' in revision 369026D8",
           cmd=cmd_for(path, out))


def p6_two_data_fields():
    text = HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<EOR>\n"
    p, rows, out, path = one("p6_two_fields.adi", text, "p6.xlsx")
    ok = p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
    record("P6 file with exactly 2 data fields (boundary of the new rule)",
           "1 QSO accepted", f"rc={p.returncode} rows={len(rows)}", ok,
           cmd=cmd_for(path, out))


def p7_second_eoh_midfile():
    """A second <EOH> in the middle (concatenated multi-part export)."""
    text = (HDR + q("W1AW", "20240101")
            + "<ADIF_VER:5>3.1.4<PROGRAMID:5>LoTW2<EOH>\n"
            + q("K2DEF", "20240102"))
    p, rows, out, path = one("p7_second_eoh.adi", text, "p7.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("P7 second header block + <EOH> in the middle of the file",
           "2 QSOs (nothing after the second <EOH> is lost; header tags not QSO rows)",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


def p8_eod_terminator():
    text = HDR + q("W1AW", "20240101") + "<EOD>\n"
    p, rows, out, path = one("p8_eod.adi", text, "p8.xlsx")
    ok = p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
    record("P8 <EOD> as the final terminator instead of <EOR>",
           "1 QSO", f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, cmd=cmd_for(path, out))


def p9_header_only_midfile():
    """Header-only record in the middle: must be a header, never a QSO row."""
    text = (HDR + q("W1AW", "20240101")
            + "<CREATED_TIMESTAMP:15>20240102 000000<EOR>\n" + q("K2DEF", "20240102"))
    p, rows, out, path = one("p9_header_midfile.adi", text, "p9.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("P9 header-only record in the middle of the file",
           "2 QSOs, no blank row", f"rc={p.returncode} rows={len(rows)} calls={calls}",
           ok, cmd=cmd_for(path, out))


def p10_trailing_header_record():
    text = HDR + q("W1AW", "20240101") + "<ADIF_VER:5>3.1.4<PROGRAMID:4>LoTW<EOR>\n"
    p, rows, out, path = one("p10_trailing_header.adi", text, "p10.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW"]
    record("P10 header-only record at the END of the file",
           "1 QSO, no blank row", f"rc={p.returncode} rows={len(rows)} calls={calls}",
           ok, cmd=cmd_for(path, out))


def p11_value_contains_eor_mid():
    text = HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<COMMENT:9>a<EOR>bcd<EOR>\n" + q("K2DEF", "20240102")
    p, rows, out, path = one("p11_value_eor_mid.adi", text, "p11.xlsx")
    got = rows[0].get("COMMENT") if rows else None
    ok = (p.returncode == 0 and len(rows) == 2 and got == "a<EOR>bcd"
          and rows[1].get("CALL") == "K2DEF")
    record("P11 value containing '<EOR>' in a record followed by another record",
           "2 QSOs; COMMENT == 'a<EOR>bcd'", f"rc={p.returncode} rows={len(rows)} COMMENT={got!r}",
           ok, cmd=cmd_for(path, out))


def p12_unknown_tag_after_eor():
    """Unrecognised tag BETWEEN records but directly after <EOR>."""
    text = (HDR + q("W1AW", "20240101") + "<zzz>\n" + q("K2DEF", "20240102")
            + q("N3XYZ", "20240103"))
    p, rows, out, path = one("p12_unknown_bare_tag.adi", text, "p12.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF", "N3XYZ"]
    record("P12 bare unrecognised tag '<zzz>' between records",
           "3 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}",
           ok, note="'stop at the first unrecognised tag' is the risk here",
           cmd=cmd_for(path, out))


def p13_banner_with_eoh_prose():
    text = ("ADIF export from MyLogger v2.1 -- see the <EOH> section for details.\n"
            "Generated 2024-01-01 <EOR> do not edit.\n"
            + HDR + q("W1AW", "20240101"))
    p, rows, out, path = one("p13_banner_prose.adi", text, "p13.xlsx")
    ok = p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
    record("P13 banner preamble containing <EOH> and <EOR> in prose",
           "1 QSO (W1AW), preamble ignored", f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           ok, cmd=cmd_for(path, out))


def p14_value_at_eof_no_eor():
    """The exact case from finding 1, plus every field type after the value."""
    tail = ("<BAND:3>20M<MODE:3>SSB<RST_SENT:2>59<STATION_CALLSIGN:5>DL1AA"
            "<FREQ:8>14.07400<RST_RCVD:2>59")
    text = (HDR + q("W1AW", "20240101")
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<COMMENT:9>a<EOR>bcd"
            + tail)   # no trailing <EOR>
    p, rows, out, path = one("p14_last_value_eor.adi", text, "p14.xlsx")
    r = rows[-1] if rows else {}
    exp = {"CALL": "K2DEF", "COMMENT": "a<EOR>bcd", "BAND": "20M", "MODE": "SSB",
           "RST_SENT": "59", "STATION_CALLSIGN": "DL1AA", "FREQ_MHZ": 14.074,
           "RST_RCVD": "59"}
    bad = {k: (v, r.get(k)) for k, v in exp.items() if r.get(k) != v}
    ok = p.returncode == 0 and len(rows) == 2 and not bad
    record("P14 FINDING 1: last record, no trailing <EOR>, value contains '<EOR>'",
           "2 QSOs; every field after the value survives",
           f"rc={p.returncode} rows={len(rows)} mismatches={bad}", ok,
           cmd=cmd_for(path, out))


def main():
    for fn in (p1_unknown_tag_midfile, p2_bare_tag_midfile, p3_free_text_midfile,
               p4_trailing_junk_after_records, p5_one_data_field, p6_two_data_fields,
               p7_second_eoh_midfile, p8_eod_terminator, p9_header_only_midfile,
               p10_trailing_header_record, p11_value_contains_eor_mid,
               p12_unknown_tag_after_eor, p13_banner_with_eoh_prose,
               p14_value_at_eof_no_eor):
        fn()
    dump("p_parser")


if __name__ == "__main__":
    main()
