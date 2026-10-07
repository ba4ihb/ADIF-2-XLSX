# -*- coding: utf-8 -*-
r"""M-group - BANNER INVARIANCE matrix for revision FC0F332B.

The Lead's key invariant: the same record bytes must parse the same way whether
or not a banner precedes them (and whether or not <EOH> was written).  Every
shape below is run in three variants - plain, banner-prefixed and
newline-prefixed - and must produce an identical CALL sequence and row count.

Run: python verification\cases_matrix.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import dump, out_path, qso_rows, record, run, write_case  # noqa: E402

BANNER = "Saved by MyLogger v2.1 -- do not edit\r\n"
BLANK = "\r\n"
Q1 = ("<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<BAND:3>20M<MODE:3>SSB"
      "<STATION_CALLSIGN:5>DL1AA<EOR>")
Q2 = ("<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<BAND:3>40M<MODE:2>CW"
      "<STATION_CALLSIGN:5>DL1AA<EOR>")
HDR = "<ADIF_VER:5>3.1.4<PROGRAMID:4>TEST"
LOTW_HDR = ("<PROGRAMID:4>LoTW<APP_LOTW_LASTQSL:19>2026-10-05 12:19:35"
            "<APP_LOTW_NUMREC:3>199")

# shape name -> (body, expected CALL sequence, note)
SHAPES = [
    ("standard header + <EOH>", HDR + "<EOH>\r\n" + Q1 + "\r\n" + Q2 + "\r\n",
     ["W1AW", "K2DEF"], "the G2a shape"),
    ("LoTW header (APP_* names) + lowercase <eoh>",
     LOTW_HDR + "<eoh>\r\n" + Q1 + "\r\n" + Q2 + "\r\n", ["W1AW", "K2DEF"],
     "the real lotw.adi shape"),
    ("header fields + full QSO in ONE record ending at <EOH>",
     "<ADIF_VER:5>3.1.4" + Q1[:-5] + "<EOH>\r\n" + Q2 + "\r\n", ["W1AW", "K2DEF"],
     "the H3 question: header and QSO share a record"),
    ("header fields + full QSO in one record ending at <EOR>",
     "<ADIF_VER:5>3.1.4" + Q1 + "\r\n" + Q2 + "\r\n", ["W1AW", "K2DEF"],
     "the G2d shape"),
    ("header with NO <EOH> (terminated by <EOR>)",
     HDR + "<EOR>\r\n" + Q1 + "\r\n" + Q2 + "\r\n", ["W1AW", "K2DEF"],
     "the G2c shape"),
    ("empty header block then <EOH>",
     "<EOH>\r\n" + Q1 + "\r\n" + Q2 + "\r\n", ["W1AW", "K2DEF"], "headerless with EOH"),
    ("headerless, no <EOH>, no terminator on the last record",
     Q1 + "\r\n" + Q2, ["W1AW", "K2DEF"], "lenient producer"),
    ("single headerless record, no terminator", Q1, ["W1AW"], "minimal file"),
    ("header-only record in the middle of the file",
     HDR + "<EOH>\r\n" + Q1 + "\r\n<ADIF_VER:5>3.1.4<PROGRAMID:4>LoTW<EOR>\r\n" + Q2 + "\r\n",
     ["W1AW", "K2DEF"], "repeated header must not become a row"),
    ("<?xml?> prologue then header then QSOs",
     '<?xml version="1.0"?>\r\n' + HDR + "<EOH>\r\n" + Q1 + "\r\n", ["W1AW"],
     "the q10b shape"),
    ("header block carrying a QSO-legal name (COMMENT)",
     "<ADIF_VER:5>3.1.4<COMMENT:9>for award<EOH>\r\n" + Q1 + "\r\n", None,
     "RECORDED trade-off: COMMENT is a QSO field, so by the content rule this "
     "header block is itself a QSO row; only banner-invariance is asserted"),
]

VARIANTS = [("plain", ""), ("banner", BANNER), ("blankline", BLANK)]


def run_variant(tag, prefix, body):
    path = write_case(f"m_{tag}.adi", prefix + body)
    out = out_path(f"m_{tag}.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    return p, [r.get("CALL") for r in rows], os.path.relpath(path, os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    for index, (title, body, expected, note) in enumerate(SHAPES):
        results = {}
        for vname, prefix in VARIANTS:
            tag = f"{index:02d}_{vname}"
            p, calls, rel = run_variant(tag, prefix, body)
            results[vname] = (p.returncode, calls, rel)
        rcs = {v: r[0] for v, r in results.items()}
        callseqs = {v: r[1] for v, r in results.items()}
        consistent = len(set(map(tuple, callseqs.values()))) == 1 and len(set(rcs.values())) == 1
        matches = True if expected is None else all(c == expected for c in callseqs.values())
        ok = consistent and matches and set(rcs.values()) == {0}
        want = "identical result in all three variants" if expected is None else str(expected)
        record(f"M matrix: {title}",
               f"plain/banner/blank-line all give {want}",
               f"rc={rcs} calls={callseqs} consistent={consistent} matches_expected={matches}",
               ok, note=note,
               cmd=f"python adif2xlsx.py {results['plain'][2]} -o verification\\out\\m_{index:02d}_plain.xlsx")

    dump("m_matrix")


if __name__ == "__main__":
    main()
