# -*- coding: utf-8 -*-
r"""G7 - robustness: hostile / malformed inputs.

For every case the exact exit code, the stderr/stdout text and whether a
workbook was produced are recorded. A "traceback" in stderr is always a FAIL.

Run: python verification\cases_robust.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, dump, out_path, qso_rows, record, run, write_case  # noqa: E402

GOOD_HDR = "<ADIF_VER:5>3.1.4<EOH>\n"
GOOD_QSO = ("<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB"
            "<STATION_CALLSIGN:5>DL1AA<EOR>\n")


def probe(case, name, data, binary=False, args=None, cwd=None, accept_rows=None):
    """Run one hostile input and report rc/stderr/workbook."""
    path = write_case(name, data, binary=binary)
    out = out_path(f"{case}.xlsx")
    if os.path.exists(out):
        os.remove(out)
    argv = list(args) if args else [path]
    p = run(argv + ["-o", out], cwd=cwd or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    exists = os.path.exists(out)
    rows = qso_rows(out) if exists else None
    tb = "Traceback" in p.stderr
    return p, exists, rows, tb, out, path


def report(case, title, expected, p, exists, rows, tb, out, path, ok, note="", cmd=None):
    err = p.stderr.strip().splitlines()
    err1 = err[0] if err else ""
    out1 = p.stdout.strip().splitlines()
    observed = (f"rc={p.returncode} workbook={'yes' if exists else 'no'} "
                f"rows={len(rows) if rows is not None else '-'} traceback={tb} "
                f"stderr[0]={err1[:160]!r} stdout_tail={(out1[-1][:120] if out1 else '')!r}")
    record(title, expected, observed, ok, note=note,
           cmd=cmd or f"python adif2xlsx.py {os.path.relpath(path, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))} -o {os.path.relpath(out, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))}")
    print(f"         rc={p.returncode} stderr={p.stderr.strip()[:400]!r}")


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # r1 empty file
    p, e, rows, tb, out, path = probe("r1", "r1_empty.adi", b"", binary=True)
    report("r1", "R1 empty file (0 bytes)", "rc!=0, clear message, no traceback, no workbook",
           p, e, rows, tb, out, path, p.returncode != 0 and not e and not tb)

    # r2 plain text, no '<'
    p, e, rows, tb, out, path = probe("r2", "r2_plain_text.txt", "Hello world\nthis is not ADIF\n")
    report("r2", "R2 text file with no ADIF content ('<' absent)",
           "rc!=0, clear message, no traceback, no workbook",
           p, e, rows, tb, out, path, p.returncode != 0 and not e and not tb)

    # r3 text with '<' but no ADIF
    p, e, rows, tb, out, path = probe("r3", "r3_html.txt", "<html><body>not adif</body></html>\n")
    report("r3", "R3 text file with '<' but no ADIF at all (HTML)",
           "rc!=0, clear message, no traceback, no workbook",
           p, e, rows, tb, out, path, p.returncode != 0 and not e and not tb,
           note="observed: accepted as 1 bogus QSO row" if rows else "")

    # r3b markup that superficially looks like a field
    p, e, rows, tb, out, path = probe("r3b", "r3b_pseudo_adif.txt",
                                      "<b:2>hi</b> this file is a note, not a log\n")
    report("r3b", "R3b note file containing a pseudo length-prefixed tag '<b:2>hi'",
           "rc!=0, clear message, no traceback, no workbook",
           p, e, rows, tb, out, path, p.returncode != 0 and not e and not tb,
           note="observed: accepted as a QSO row" if rows else "")

    # r4 truncated mid-value
    truncated = GOOD_HDR + GOOD_QSO + "<CALL:4>K2DE"   # last field cut short
    p, e, rows, tb, out, path = probe("r4", "r4_truncated_value.adi", truncated)
    report("r4", "R4 truncated mid-value (declared length runs past EOF)",
           "no traceback; behaviour recorded",
           p, e, rows, tb, out, path, p.returncode == 0 and not tb,
           note="observed: the partial record is emitted silently (no truncation warning)")

    # r5 truncated mid-tag
    p, e, rows, tb, out, path = probe("r5", "r5_truncated_tag.adi",
                                      GOOD_HDR + GOOD_QSO + "<CALL:5>K2DEF<QSO")
    report("r5", "R5 truncated in the middle of a field tag",
           "no traceback", p, e, rows, tb, out, path, not tb,
           note="observed: the dangling record is dropped silently")

    # r6 directory with no .adi files
    d = os.path.join(HERE, "cases", "r6_dir_no_adi")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "notes.txt"), "w", encoding="utf-8") as fh:
        fh.write("nothing here\n")
    p, e, rows, tb, out, path = probe("r6", "r6_dir_no_adi_dummy.txt", "x", args=[d])
    report("r6", "R6 directory containing no .adi/.adif files",
           "rc!=0 with a clear message, no traceback",
           p, e, rows, tb, out, d, p.returncode != 0 and not tb)

    # r7 header-only file
    p, e, rows, tb, out, path = probe("r7", "r7_header_only.adi", GOOD_HDR + "<CREATED_TIMESTAMP:15>20240101 120000<EOR>\n")
    report("r7", "R7 .adi with a header but no QSOs",
           "rc!=0 with a clear message, no traceback, no workbook",
           p, e, rows, tb, out, path, p.returncode != 0 and not tb and not e)

    # r8 nonexistent path
    p, e, rows, tb, out, path = probe("r8", "r8_unused.adi", "x",
                                      args=[os.path.join(HERE, "cases", "does_not_exist.adi")])
    report("r8", "R8 input path that does not exist",
           "rc=2 with a clear message, no traceback",
           p, e, rows, tb, out, path, p.returncode == 2 and not tb)

    # r9 good file + empty file (mixed batch exit code)
    good = os.path.join(HERE, "cases", "r9_good.adi")
    with open(good, "w", encoding="utf-8", newline="") as fh:
        fh.write(GOOD_HDR + GOOD_QSO)
    empty = os.path.join(HERE, "cases", "r9_empty.adi")
    with open(empty, "wb") as fh:
        fh.write(b"")
    out = out_path("r9.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([good, empty, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else None
    report("r9", "R9 one good file + one unreadable (empty) file in the same run",
           "non-zero exit (a file was skipped) with a warning; good file still converted",
           p, os.path.exists(out), rows, "Traceback" in p.stderr, out, good,
           p.returncode != 0 and rows is not None and len(rows) == 1,
           note="observed: rc=0 even though a file was skipped - see "
                "main() 'return 0 if failures == 0 else 0'")

    # r10 control character inside a value
    body = (GOOD_HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            "<COMMENT:5>a\x01bcd<STATION_CALLSIGN:5>DL1AA<EOR>\n").encode("utf-8")
    p, e, rows, tb, out, path = probe("r10", "r10_ctrl_char.adi", body, binary=True)
    report("r10", "R10 control character (0x01) inside a COMMENT value",
           "no traceback: either a clean error or the character neutralised",
           p, e, rows, tb, out, path, not tb,
           note="observed: openpyxl IllegalCharacterError escapes as a traceback" if tb else "")

    # r10b vertical tab
    body = (GOOD_HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            "<COMMENT:5>a\x0bbcd<STATION_CALLSIGN:5>DL1AA<EOR>\n").encode("utf-8")
    p, e, rows, tb, out, path = probe("r10b", "r10b_vtab.adi", body, binary=True)
    report("r10b", "R10b vertical tab (0x0B) inside a COMMENT value",
           "no traceback", p, e, rows, tb, out, path, not tb,
           note="observed: traceback" if tb else "")

    # r10c which bytes actually break the writer
    bytes_seen = {}
    for byte in (0x00, 0x01, 0x08, 0x0B, 0x0C, 0x1F, 0x7F, 0x81):
        val = "a" + chr(byte) + "bcd"
        body = (GOOD_HDR + f"<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
                f"<COMMENT:{len(val)}>{val}<STATION_CALLSIGN:5>DL1AA<EOR>\n"
                ).encode("utf-8")
        p2, e2, rows2, tb2, out2, path2 = probe(f"r10c_{byte:02x}", f"r10c_{byte:02x}.adi",
                                                body, binary=True)
        bytes_seen[f"0x{byte:02X}"] = ("traceback/no workbook" if tb2 else f"rc={p2.returncode}")
    crashing = sorted(k for k, v in bytes_seen.items() if v.startswith("traceback"))
    record("R10c which control bytes break the conversion",
           "no traceback for any byte; every byte neutralised or reported cleanly",
           f"crashing bytes: {crashing}; per-byte: {bytes_seen} "
           f"(for every crashing byte: rc=1, no .xlsx written, 'Traceback ... "
           f"IllegalCharacterError' on stderr)",
           not crashing,
           note="the whole workbook is lost instead of one bad cell being cleaned",
           cmd='python adif2xlsx.py verification\\cases\\r10c_01.adi -o verification\\out\\r10c_01.xlsx')

    # r11 CP1252 high byte
    cp_val = "caf\u00e9"                     # 4 characters, 4 latin-1 bytes
    body = (GOOD_HDR + f"<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            f"<COMMENT:{len(cp_val)}>{cp_val}<STATION_CALLSIGN:5>DL1AA<EOR>\n").encode("latin-1")
    p, e, rows, tb, out, path = probe("r11", "r11_cp1252.adi", body, binary=True)
    got = rows[0].get("COMMENT") if rows else None
    report("r11", "R11 CP1252 (latin-1) high byte in a value",
           "no traceback; value decoded (caf\u00e9)", p, e, rows, tb, out, path,
           (not tb) and got == cp_val, note=f"COMMENT={got!r}")

    # r12 UTF-16 with BOM (the codec adds the BOM)
    body = (GOOD_HDR + f"<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            f"<COMMENT:{len(cp_val)}>{cp_val}<STATION_CALLSIGN:5>DL1AA<EOR>\n").encode("utf-16")
    p, e, rows, tb, out, path = probe("r12", "r12_utf16.adi", body, binary=True)
    got = rows[0].get("COMMENT") if rows else None
    report("r12", "R12 UTF-16 encoded file with BOM",
           "no traceback; value decoded correctly", p, e, rows, tb, out, path,
           (not tb) and got == cp_val, note=f"COMMENT={got!r} call={rows[0].get('CALL') if rows else None!r}")

    # r13 binary garbage
    blob = bytes(range(256)) * 3
    p, e, rows, tb, out, path = probe("r13", "r13_binary.bin", blob, binary=True)
    report("r13", "R13 binary file (all 256 byte values)",
           "no traceback", p, e, rows, tb, out, path, not tb,
           note=f"rows={len(rows) if rows is not None else '-'}")

    # r14 only <EOR>
    p, e, rows, tb, out, path = probe("r14", "r14_only_eor.adi", "<EOR><EOR>\n")
    report("r14", "R14 file containing only <EOR> tags",
           "rc!=0 with a clear message, no traceback, no workbook",
           p, e, rows, tb, out, path, p.returncode != 0 and not tb and not e)

    # r15 field with no value and no terminator
    p, e, rows, tb, out, path = probe("r15", "r15_bare_tag.adi", "<CALL>\n")
    report("r15", "R15 a bare '<CALL>' tag (no length, no value, not a structural tag)",
           "rc!=0 (cannot be ADIF) - behaviour recorded",
           p, e, rows, tb, out, path, p.returncode != 0,
           note="observed: creates a QSO row with an empty CALL" if rows else "")

    # r16 very long value (> Excel 32767-char cell limit)
    long_comment = "x" * 40000
    body = (GOOD_HDR + f"<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            f"<COMMENT:{len(long_comment)}>{long_comment}<STATION_CALLSIGN:5>DL1AA<EOR>\n")
    p, e, rows, tb, out, path = probe("r16", "r16_long_value.adi", body)
    got_len = len(rows[0].get("COMMENT") or "") if rows else 0
    report("r16", "R16 COMMENT of 40000 characters (Excel cell limit is 32767)",
           "no traceback", p, e, rows, tb, out, path, not tb,
           note=f"observed: value written with {got_len} chars; Excel would truncate/repair "
                "on open - no warning from the tool")

    # r17 no <EOR> anywhere but a full record (must still work - see B1h)
    p, e, rows, tb, out, path = probe("r17", "r17_no_terminator.adi",
                                      GOOD_HDR + GOOD_QSO.replace("<EOR>\n", "\n"))
    report("r17", "R17 well-formed record with the trailing <EOR> omitted",
           "1 QSO converted (lenient)", p, e, rows, tb, out, path,
           p.returncode == 0 and rows is not None and len(rows) == 1)

    dump("g7_robust")


if __name__ == "__main__":
    main()
