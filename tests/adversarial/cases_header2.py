# -*- coding: utf-8 -*-
r"""H-group - header-classification probes for revision 24E51902.

The Lead's worry: a legitimate short/headerless file, or a header that shares a
record with the first QSO, being misread as a header after the new
"before <EOH> == header" rule.  These cases attack that rule from both sides.

Run: python verification\cases_header2.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, adif, dump, out_path, qso_rows, record, run, write_case  # noqa: E402

Q1 = ("<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<BAND:3>20M<MODE:3>SSB"
      "<STATION_CALLSIGN:5>DL1AA<EOR>")
Q2 = ("<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<BAND:3>40M<MODE:2>CW"
      "<STATION_CALLSIGN:5>DL1AA<EOR>")
BANNER = "Saved by MyLogger v2.1 -- do not edit\r\n"
LOTW_HDR = ("<PROGRAMID:4>LoTW<APP_LOTW_LASTQSL:19>2026-10-05 12:19:35"
            "<APP_LOTW_NUMREC:3>199")


def one(name, text, outname, binary=False):
    path = write_case(name, text, binary=binary)
    out = out_path(outname)
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    return p, rows, out, path


def cmd_for(path, out):
    return ("python adif2xlsx.py " + os.path.relpath(path, os.path.dirname(HERE))
            + " -o " + os.path.relpath(out, os.path.dirname(HERE)))


# ---------------------------------------------------------------- H1: real LoTW shape
def h1_lotw_header_lowercase_eoh():
    text = BANNER + LOTW_HDR + "<eoh>\r\n" + Q1 + "\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h1_lotw_header.adi", text, "h1.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H1 banner + <PROGRAMID>/APP_LOTW_* header terminated by lowercase <eoh>",
           "2 QSOs (the header is not a QSO row)",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           note="the real lotw.adi shape; header fields are QSO-legal names, so only "
                "position can identify this record as a header",
           cmd=cmd_for(path, out))


def h1b_lotw_header_no_banner():
    text = LOTW_HDR + "<eoh>\r\n" + Q1 + "\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h1b_lotw_header_no_banner.adi", text, "h1b.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H1b same header but the file starts at '<' (banner stripped / producer "
           "writes no banner)",
           "2 QSOs (header recognised by position, not by the absence of a banner)",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           note="'first character is <' disables header tagging entirely, so any header "
                "record holding a non-header field name becomes a QSO row",
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- H2: preamble, no EOH
def h2_banner_header_no_eoh():
    text = BANNER + "<ADIF_VER:5>3.1.4<PROGRAMID:4>LoTW" + Q1 + "\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h2_banner_no_eoh.adi", text, "h2.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H2 preamble + header + QSOs with NO <EOH> anywhere",
           "2 QSOs (header fields dropped, records kept)",
           f"rc={p.returncode} rows={len(rows)} calls={calls} "
           f"stderr={p.stderr.strip()[:150]!r}",
           ok, note="without <EOH> nothing ever clears the before-header state, so every "
                "record in a banner-prefixed file is tagged as header content",
           cmd=cmd_for(path, out))


def h2b_banner_qsos_only_no_eoh():
    text = BANNER + Q1 + "\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h2b_banner_qsos_no_eoh.adi", text, "h2b.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H2b preamble + headerless QSOs, no <EOH>",
           "2 QSOs",
           f"rc={p.returncode} rows={len(rows)} calls={calls} "
           f"stderr={p.stderr.strip()[:150]!r}",
           ok, note="same root cause as H2: a banner plus no <EOH> swallows every record",
           cmd=cmd_for(path, out))


def h2c_leading_blank_line():
    text = "\r\n" + Q1 + "\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h2c_leading_blank_line.adi", text, "h2c.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H2c headerless file that merely STARTS WITH A NEWLINE",
           "2 QSOs",
           f"rc={p.returncode} rows={len(rows)} calls={calls} "
           f"stderr={p.stderr.strip()[:150]!r}",
           ok, note="a single leading non-'<' byte is enough to mark the first QSO as header",
           cmd=cmd_for(path, out))


def h2d_leading_space():
    text = " " + Q1 + "\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h2d_leading_space.adi", text, "h2d.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H2d headerless file that merely starts with a SPACE",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


def h2e_leading_comment():
    text = "<!-- exported by hand -->\n" + Q1 + "\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h2e_leading_comment.adi", text, "h2e.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H2e headerless file starting with an XML comment (starts with '<')",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           note="control: an '<'-initial comment keeps the file headerless",
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- H3: EOH sharing the record
def h3_record_ends_at_eoh_with_qso_fields():
    text = BANNER + "<ADIF_VER:5>3.1.4" + Q1 + "<EOH>\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h3_eoh_with_qso_fields.adi", text, "h3.xlsx")
    calls = [r.get("CALL") for r in rows]
    record("H3 RECORDED: banner file, one record holds ADIF_VER + a full QSO and ends at <EOH>",
           "Lead asked for the observed behaviour: header or QSO?",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", True,
           note="the whole record is consumed as header, so W1AW is lost from the QSO sheet",
           cmd=cmd_for(path, out))


def h3b_same_without_banner():
    text = "<ADIF_VER:5>3.1.4" + Q1 + "<EOH>\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h3b_eoh_qso_no_banner.adi", text, "h3b.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = calls == ["W1AW", "K2DEF"]
    record("H3b same record content, file starts at '<' (no banner)",
           "2 QSOs - the QSO survives",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           note="same bytes, different result depending only on whether a banner precedes "
                "them - the two H3 cases disagree",
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- H4: regression controls
def h4_jtdx_shape():
    text = ("<call:6>JS6TKY <gridsquare:4>PL14 <mode:3>FT8 <rst_sent:3>-08 "
            "<qso_date:8>20240101 <time_on:4>1200 <band:2>6m <station_callsign:6>BA4IHB "
            "<eor>\r\n<call:6>JF2EEK <gridsquare:4>PM95 <mode:3>FT8 <rst_sent:3>-11 "
            "<qso_date:8>20240102 <time_on:4>1300 <band:2>6m <station_callsign:6>BA4IHB "
            "<eor>\r\n")
    p, rows, out, path = one("h4_jtdx_shape.adi", text, "h4.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["JS6TKY", "JF2EEK"]
    record("H4 JTDX-shaped headerless file (starts at '<', no <EOH>)",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


def h4b_single_record_headerless():
    text = Q1 + "\r\n"
    p, rows, out, path = one("h4b_single_headerless.adi", text, "h4b.xlsx")
    ok = p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
    record("H4b single-record headerless file", "1 QSO",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}", ok,
           cmd=cmd_for(path, out))


def h4c_short_name_only():
    text = "<CALL:4>W1AW<EOR>\r\n"
    p, rows, out, path = one("h4c_call_only.adi", text, "h4c.xlsx")
    ok = p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
    record("H4c short headerless file with one field only", "1 QSO (CALL=W1AW)",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}", ok,
           cmd=cmd_for(path, out))


def h4d_lowercase_eor_only():
    text = ("<call:4>W1AW<qso_date:8>20240101<time_on:4>1200<mode:3>SSB<eor>\r\n"
            "<call:5>K2DEF<qso_date:8>20240102<time_on:4>1300<mode:2>CW<eor>\r\n")
    p, rows, out, path = one("h4d_lowercase.adi", text, "h4d.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H4d all-lowercase tags with lowercase <eor> (JTDX style)",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


def h4e_repeated_header_midfile():
    text = ("<ADIF_VER:5>3.1.4<EOH>" + Q1 + "<ADIF_VER:5>3.1.4<PROGRAMID:4>LoTW<EOR>"
            + Q2)
    p, rows, out, path = one("h4e_repeated_header.adi", text, "h4e.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H4e header-only record in the middle of a headerless file",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- H5: diagnostics
def h5_no_false_missing_warning():
    """A file that never exports RST/STATION_CALLSIGN must not be reported as incomplete."""
    text = ("<ADIF_VER:5>3.1.4<PROGRAMID:4>TEST<EOH>"
            + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
                    ("MODE", "SSB"), ("BAND", "20M")]) + "\n")
    p, rows, out, path = one("h5_no_rst_export.adi", text, "h5.xlsx")
    noisy = ("WARNING" in p.stdout) or ("NOTE" in p.stdout) or ("missing" in p.stdout)
    ok = (not noisy) and p.returncode == 0
    record("H5 no false 'missing fields' alarm for fields the source never exports",
           "no WARNING/NOTE at all (RST/STATION_CALLSIGN are simply absent from this file)",
           f"rc={p.returncode} noisy={noisy} stdout_tail={p.stdout.strip().splitlines()[-1][:110]!r}",
           ok, cmd=cmd_for(path, out))


def h5b_real_missing_is_reported():
    """A file that DOES export RST_SENT but has an empty one must still be reported."""
    text = ("<ADIF_VER:5>3.1.4<EOH>"
            + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
                    ("MODE", "SSB"), ("RST_SENT", "59")]) + "\n"
            + adif([("CALL", "K2DEF"), ("QSO_DATE", "20240102"), ("TIME_ON", "1300"),
                    ("MODE", "SSB"), ("RST_SENT", "")]) + "\n")
    p, rows, out, path = one("h5b_missing_rst.adi", text, "h5b.xlsx")
    reported = "RST_SENT" in p.stdout and ("NOTE" in p.stdout or "WARNING" in p.stdout)
    ok = reported and p.returncode == 0
    record("H5b a genuinely empty exported field is still reported",
           "a NOTE/WARNING naming RST_SENT for the record that leaves it empty",
           f"rc={p.returncode} reported={reported} "
           f"line={[l.strip() for l in p.stdout.splitlines() if 'RST_SENT' in l][-1:]}",
           ok, note="printed as 'NOTE : N record(s) left a column empty that the source file "
                    "does populate'",
           cmd=cmd_for(path, out))


def h6_leading_whitespace_with_header_and_eoh():
    """Control for H2: leading whitespace plus a real <EOH> must still work."""
    text = "\r\n" + "<ADIF_VER:5>3.1.4<PROGRAMID:4>LoTW<EOH>\r\n" + Q1 + "\r\n" + Q2 + "\r\n"
    p, rows, out, path = one("h6_leading_ws_with_eoh.adi", text, "h6.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("H6 control: leading newline + header + <EOH>",
           "2 QSOs (the <EOH> clears the header state)",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           note="isolates the H2 failures to the 'no <EOH> in a non-<-initial file' path",
           cmd=cmd_for(path, out))


def main():
    for fn in (h1_lotw_header_lowercase_eoh, h1b_lotw_header_no_banner,
               h2_banner_header_no_eoh, h2b_banner_qsos_only_no_eoh,
               h2c_leading_blank_line, h2d_leading_space, h2e_leading_comment,
               h3_record_ends_at_eoh_with_qso_fields, h3b_same_without_banner,
               h4_jtdx_shape, h4b_single_record_headerless, h4c_short_name_only,
               h4d_lowercase_eor_only, h4e_repeated_header_midfile,
               h5_no_false_missing_warning, h5b_real_missing_is_reported,
               h6_leading_whitespace_with_header_and_eoh):
        fn()
    dump("h_header2")


if __name__ == "__main__":
    main()
