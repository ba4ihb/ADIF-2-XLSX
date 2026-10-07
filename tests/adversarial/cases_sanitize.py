# -*- coding: utf-8 -*-
r"""Q-group - probes for the NEW attack surface of revision 73443B15.

Targets the three changes:
  sanitize_cell()          - control chars, 32767 cap, formula prefixes
  stray-tag / markup rules - </EOR>, <EOR/>, unknown tags, HTML stop
  vocabulary acceptance    - KNOWN_FIELDS vs "or header"

Run: python verification\cases_sanitize.py   (from the workspace root)
"""
from __future__ import annotations

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (HERE, ROOT, adif, dump, out_path, qso_rows, raw_sheet_xml,  # noqa: E402
                    record, run, stored_text, write_case)

HDR = "<ADIF_VER:5>3.1.4<EOH>\n"
CMD = "python adif2xlsx.py verification\\cases\\{f} -o verification\\out\\{o}"


def one(name, text, outname, binary=False):
    path = write_case(name, text, binary=binary)
    out = out_path(outname)
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    return p, rows, out, path


def cmd_for(path, out):
    return ("python adif2xlsx.py "
            + os.path.relpath(path, ROOT) + " -o " + os.path.relpath(out, ROOT))


# ---------------------------------------------------------------- Q1: RST reports
def q1_rst_minus():
    """RST_SENT/RST_RCVD of weak-signal modes start with '-'."""
    text = (HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
                        ("MODE", "FT8"), ("RST_SENT", "-10"), ("RST_RCVD", "-12"),
                        ("STATION_CALLSIGN", "DL1AA")]) + "\n"
            + adif([("CALL", "K2DEF"), ("QSO_DATE", "20240101"), ("TIME_ON", "1215"),
                    ("MODE", "FT8"), ("RST_SENT", "-05"), ("RST_RCVD", "+12"),
                    ("STATION_CALLSIGN", "DL1AA")]) + "\n")
    p, rows, out, path = one("q1_rst_negative.adi", text, "q1.xlsx")
    got = [(r.get("CALL"), r.get("RST_SENT"), r.get("RST_RCVD")) for r in rows]
    exp = [("W1AW", "-10", "-12"), ("K2DEF", "-05", "+12")]
    raw = None
    if os.path.exists(out):
        raw = (stored_text(out, "RST_SENT", 2), stored_text(out, "RST_SENT", 3))
    ok = got == exp
    record("Q1 RST_SENT/RST_RCVD of FT8 reports (-10, -12, -05, +12) survive intact",
           f"{exp}", f"rc={p.returncode} got={got} raw_stored={raw}", ok,
           note="sanitize_cell() prefixes an apostrophe to any value starting with "
                "- + = or @; RST reports start with '-' by definition",
           cmd=cmd_for(path, out))


def q2_rst_real_fixtures():
    """Cross-check every RST value in the three real fixtures."""
    tag = re.compile(r"<\s*([A-Za-z_][A-Za-z0-9_\-\.]*)\s*:\s*(\d+)\s*(?::\s*[A-Za-z]\s*)?>")
    eor = re.compile(r"<\s*/?\s*EOR\s*>", re.IGNORECASE)
    worst = {}
    corrupted_cells = 0
    checked_cells = 0
    for rel in ("samples/sample_log.adi", "samples/sample_lotw_quirks.adi", "perf_1000.adi"):
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        text = open(path, "rb").read().decode("utf-8-sig")
        raw_pairs = []
        cur, pos = {}, 0
        while pos < len(text):
            m, e = tag.search(text, pos), eor.search(text, pos)
            if m and (not e or m.start() < e.start()):
                cur[m.group(1).upper()] = text[m.end():m.end() + int(m.group(2))]
                pos = m.end() + int(m.group(2))
            elif e:
                if cur:
                    raw_pairs.append((cur.get("RST_SENT", ""), cur.get("RST_RCVD", "")))
                cur, pos = {}, e.end()
            else:
                break
        out = out_path("q2_" + os.path.basename(path) + ".xlsx")
        if os.path.exists(out):
            os.remove(out)
        p = run([path, "-o", out, "--quiet"])
        rows = qso_rows(out) if os.path.exists(out) else []
        wb_pairs = [(r.get("RST_SENT") or "", r.get("RST_RCVD") or "") for r in rows]
        file_bad = {}
        for idx, col in ((0, "RST_SENT"), (1, "RST_RCVD")):
            raw_c = collections.Counter(x[idx] for x in raw_pairs)
            wb_c = collections.Counter(x[idx] for x in wb_pairs)
            checked_cells += sum(raw_c.values())
            for value in raw_c:
                if value.startswith(("-", "+", "=", "@")) and wb_c.get(value, 0) != raw_c[value]:
                    file_bad[col] = file_bad.get(col, {})
                    file_bad[col][value] = (raw_c[value], wb_c.get(value, 0))
                    corrupted_cells += raw_c[value]
        worst[rel] = (len(raw_pairs), file_bad)
    record("Q2 every RST_SENT/RST_RCVD value in the 3 real fixtures matches the source",
           "identical value multisets across all RST cells",
           f"per file (records, corrupted): {worst}; corrupted cells: {corrupted_cells}"
           f"/{checked_cells}",
           corrupted_cells == 0,
           note="an apostrophe is prefixed to every weak-signal RST report, so the exported "
                "value no longer equals the logged value",
           cmd="python adif2xlsx.py samples\\sample_log.adi -o verification\\out\\q2_sample_log.adi.xlsx")

    # prove the apostrophe is physically in the file, not an openpyxl artefact
    out = out_path("q2_sample_log.adi.xlsx")
    if os.path.exists(out):
        xml = raw_sheet_xml(out)
        found = sorted({m for m in re.findall(r"<t[^>]*>('[+\-=@][^<]{0,12})</t>", xml)})
        record("Q2b the apostrophe is physically stored in the .xlsx sheet XML",
               "no apostrophe-prefixed strings in the file",
               f"apostrophe-prefixed cell texts found in xl/worksheets/sheet1.xml: {found}",
               not found,
               note="read straight from the worksheet XML, independent of openpyxl",
               cmd="(inspect xl/worksheets/sheet1.xml of verification\\out\\q2_sample_log.adi.xlsx)")


# ---------------------------------------------------------------- Q3: formula safety
def q3_formula():
    text = (HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
                        ("COMMENT", "=cmd|'/c calc'!A1"), ("NOTES", "+1+1"),
                        ("STATION_CALLSIGN", "DL1AA")]) + "\n")
    p, rows, out, path = one("q3_formula.adi", text, "q3.xlsx")
    vs = {}
    if os.path.exists(out):
        ws = __import__("openpyxl").load_workbook(out)["QSOs"]
        hdr = {c.value: c.column for c in ws[1]}
        for col in ("COMMENT", "NOTES"):
            if col in hdr:
                vs[col] = (ws.cell(row=2, column=hdr[col]).data_type,
                           ws.cell(row=2, column=hdr[col]).value)
    safe = all(dt != "f" for dt, _v in vs.values()) and bool(vs)
    record("Q3 leading '=' / '+' in log text do not become Excel formulas",
           "no cell has data_type 'f'; text neutralised",
           f"rc={p.returncode} cells={vs}", safe,
           note="neutralisation is visible in the text (apostrophe prefix)",
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- Q4: 32767 cap
def q4_truncation():
    long = "x" * 40000
    text = (HDR + f"<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
            f"<COMMENT:{len(long)}>{long}<STATION_CALLSIGN:5>DL1AA<EOR>\n")
    p, rows, out, path = one("q4_long_value.adi", text, "q4.xlsx")
    val = rows[0].get("COMMENT") if rows else None
    n = len(val or "")
    ok = p.returncode == 0 and 0 < n <= 32767 and "truncated" in (val or "")
    record("Q4 40 000-char COMMENT capped at Excel's 32 767-char cell limit",
           "rc=0; stored length <= 32767; truncation marker present",
           f"rc={p.returncode} stored_len={n} tail={(val or '')[-18:]!r}", ok,
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- Q5: control bytes
def q5_control_bytes():
    seen = {}
    for byte in (0x00, 0x01, 0x08, 0x0B, 0x0C, 0x1F, 0x7F, 0x81):
        val = "a" + chr(byte) + "bcd"
        text = (HDR + f"<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
                f"<COMMENT:{len(val)}>{val}<STATION_CALLSIGN:5>DL1AA<EOR>\n")
        p, rows, out, path = one(f"q5_{byte:02x}.adi", text, f"q5_{byte:02x}.xlsx")
        got = rows[0].get("COMMENT") if rows else None
        seen[f"0x{byte:02X}"] = (p.returncode, got)
    bad = {k: v for k, v in seen.items() if v[0] != 0 or v[1] not in ("abcd", "a\x81bcd")}
    record("Q5 control bytes are removed instead of aborting the export",
           "rc=0 and a complete workbook for every byte; 0x00-0x1F/0x7F removed from the text",
           f"per byte (rc, COMMENT): {seen}; problems={bad}", not bad,
           note="0x81 (C1) is not in openpyxl's illegal set and is kept",
           cmd='python adif2xlsx.py verification\\cases\\q5_01.adi -o verification\\out\\q5_01.xlsx')


# ---------------------------------------------------------------- Q6: </EOR> terminator
def q6_close_eor():
    text = (HDR
            + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB</EOR>"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW</EOR>"
            + "<CALL:5>N3XYZ<QSO_DATE:8>20240103<TIME_ON:4>1400<MODE:3>FT8</EOR>")
    p, rows, out, path = one("q6_close_eor.adi", text, "q6.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF", "N3XYZ"]
    record("Q6 '</EOR>' used as the record terminator (3 records)",
           "3 QSOs - the Lead states '</EOR>' is recognised as a terminator",
           f"rc={p.returncode} rows={len(rows)} calls={calls} stderr={p.stderr.strip()[:120]!r}",
           ok, note="iter_records() checks _MARKUP_TAG_RE (which contains '/') BEFORE "
                    "_END_TAG_RE, so '</' breaks the scan once data has been seen",
           cmd=cmd_for(path, out))


def q6b_slash_eor_midfile():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW<EOR>")
    text = text.replace("<EOR>", "</EOR>", 1)     # only the FIRST terminator is closing-style
    p, rows, out, path = one("q6b_mixed_terminator.adi", text, "q6b.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("Q6b one '</EOR>' terminator in an otherwise normal file",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- Q7: <EOR/> spellings
def q7_selfclosing():
    text = (HDR
            + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR/>"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW<EOR />"
            + "<CALL:5>N3XYZ<QSO_DATE:8>20240103<TIME_ON:4>1400<MODE:3>FT8<EOR>")
    p, rows, out, path = one("q7_selfclosing.adi", text, "q7.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF", "N3XYZ"]
    record("Q7 '<EOR/>' and '<EOR />' accepted as terminators (3 records)",
           "3 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- Q8: stray tags
def q8_stray_tag():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>"
            + "<zzz>" + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW<EOR>"
            + "<CALL:5>N3XYZ<QSO_DATE:8>20240103<TIME_ON:4>1400<MODE:3>FT8<EOR>")
    p, rows, out, path = one("q8_stray_tag.adi", text, "q8.xlsx")
    calls = [r.get("CALL") for r in rows]
    warned = "unrecognised tag" in p.stderr
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF", "N3XYZ"] and warned
    record("Q8 '<zzz>' between records: all 3 QSOs kept and the tag is reported",
           "3 QSOs, rc=0, stderr names ZZZ",
           f"rc={p.returncode} rows={len(rows)} calls={calls} warned={warned} stderr={p.stderr.strip()[:130]!r}",
           ok, cmd=cmd_for(path, out))


def q8b_closing_unknown_tag():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>"
            + "</zzz>" + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW<EOR>")
    p, rows, out, path = one("q8b_closing_tag.adi", text, "q8b.xlsx")
    calls = [r.get("CALL") for r in rows]
    record("Q8b RECORDED residual risk: '</zzz>' between records",
           "documented: any '</'-shaped tag other than </EOR|EOH|EOD> counts as markup and ends the scan",
           f"rc={p.returncode} rows={len(rows)} calls={calls} stderr={p.stderr.strip()[:130]!r}",
           True, note="NOT counted as a defect: '/' is the chosen markup marker so HTML error "
                      "pages stop the scan, and '</EOR>' is now excluded from that rule. "
                      "Residual risk: a stray '</x>' silently drops later records.",
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- Q9: vocabulary rule
def q9_header_plus_unknown_record():
    text = (HDR
            + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>"
            + "<ZZZ:3>abc<EOR>")           # a record of unknown fields only
    p, rows, out, path = one("q9_header_unknown_record.adi", text, "q9.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = len(rows) == 1 and calls == ["W1AW"]
    record("Q9 header file + a record made ONLY of unknown fields",
           "1 QSO (the unknown-only record is junk, not a QSO)",
           f"rc={p.returncode} rows={len(rows)} calls={calls} columns={sorted(rows[0]) if rows else []}",
           ok, note="acceptance rule is 'names & KNOWN_FIELDS or header' - once a header "
                    "exists, ANY record is accepted, so junk becomes a blank QSO row",
           cmd=cmd_for(path, out))


def q9b_headerless_unknown_record():
    text = ("<ZZZ:3>abc<OTHER:2>xy<EOR>\n")
    p, rows, out, path = one("q9b_headerless_unknown.adi", text, "q9b.xlsx")
    ok = p.returncode != 0 and not os.path.exists(out)
    record("Q9b headerless file whose records use only unknown field names",
           "rejected with a clear error, no workbook",
           f"rc={p.returncode} workbook={os.path.exists(out)} rows={len(rows)}",
           ok, cmd=cmd_for(path, out))


def q9c_vocabulary_false_positive():
    email = "a@example.com"                      # 13 characters
    text = f"<name:5>Alice<email:{len(email)}>{email}<EOR>\n"
    p, rows, out, path = one("q9c_vocab_false_positive.txt", text, "q9c.xlsx")
    record("Q9c RECORDED: non-log markup that uses vocabulary words (NAME/EMAIL)",
           "recorded: whether such a file is accepted as a QSO",
           f"rc={p.returncode} workbook={os.path.exists(out)} rows={len(rows)}",
           True, note="the vocabulary smell test cannot distinguish this from ADIF; "
                      "only affects files that were never logs",
           cmd=cmd_for(path, out))


def q9d_p5_single_call():
    text = HDR + "<CALL:4>W1AW<EOR>\n"
    p, rows, out, path = one("q9d_single_call.adi", text, "q9d.xlsx")
    r = rows[0] if rows else {}
    ok = p.returncode == 0 and len(rows) == 1 and r.get("CALL") == "W1AW"
    record("Q9d P5 re-check: '<CALL:4>W1AW<EOR>' (single recognised field)",
           "accepted as 1 QSO (new vocabulary rule) - Lead asked for my opinion",
           f"rc={p.returncode} rows={len(rows)} CALL={r.get('CALL')!r} "
           f"empty_cells={sum(1 for v in r.values() if v in (None, ''))}/{len(r)}",
           ok, note="accepting it is defensible (CALL is a real ADIF field); the risk is "
                    "the 'or header' escape hatch in Q9, not this case",
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- Q10: markup stop
def q10_html_still_rejected():
    p, rows, out, path = one("q10_html.txt", "<html><body>not adif</body></html>\n", "q10.xlsx")
    tb = "Traceback" in p.stderr
    ok = p.returncode == 1 and not os.path.exists(out) and not tb
    record("Q10 HTML error page still rejected cleanly",
           "rc=1, no workbook, no traceback",
           f"rc={p.returncode} workbook={os.path.exists(out)} traceback={tb} stderr={p.stderr.strip()[:110]!r}",
           ok, cmd=cmd_for(path, out))


def q10b_xml_prologue():
    text = "<?xml version=\"1.0\"?>\n" + HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<EOR>\n"
    p, rows, out, path = one("q10b_xml_prologue.adi", text, "q10b.xlsx")
    ok = p.returncode == 0 and len(rows) == 1 and rows[0].get("CALL") == "W1AW"
    record("Q10b '<?xml ...?>' prologue before real ADIF data",
           "1 QSO", f"rc={p.returncode} rows={len(rows)} stderr={p.stderr.strip()[:110]!r}",
           ok, cmd=cmd_for(path, out))


def q10c_xml_after_data():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<EOR>\n"
            "<?xml version=\"1.0\"?><note>error</note>\n"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<EOR>\n")
    p, rows, out, path = one("q10c_xml_after_data.adi", text, "q10c.xlsx")
    record("Q10c RECORDED: markup after real data",
           "parsing stops at the markup (intended: HTML error page)",
           f"rc={p.returncode} rows={len(rows)} calls={[r.get('CALL') for r in rows]}",
           True, note="documented consequence: a record after embedded markup is dropped",
           cmd=cmd_for(path, out))


# ---------------------------------------------------------------- Q11: CLI / exit codes
def q11_skipped_file_exit():
    good = write_case("q11_good.adi", HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<EOR>\n")
    empty = write_case("q11_empty.adi", b"", binary=True)
    out = out_path("q11.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([good, empty, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    ok = p.returncode == 1 and len(rows) == 1
    record("Q11 one good + one empty file: rc=1, good file still converted",
           "rc=1, 1 row, warning on stderr",
           f"rc={p.returncode} rows={len(rows)} stderr_tail={p.stderr.strip().splitlines()[-1][:90]!r}",
           ok, cmd=f"python adif2xlsx.py verification\\cases\\q11_good.adi verification\\cases\\q11_empty.adi -o verification\\out\\q11.xlsx")


def q11b_quiet_skipped_file():
    good = os.path.join(HERE, "cases", "q11_good.adi")
    empty = os.path.join(HERE, "cases", "q11_empty.adi")
    out = out_path("q11b.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([good, empty, "-o", out, "--quiet"])
    ok = p.returncode == 1 and os.path.exists(out)
    record("Q11b same mix with --quiet: rc must still be 1",
           "rc=1, workbook written, stderr carries the warning",
           f"rc={p.returncode} workbook={os.path.exists(out)} stderr={p.stderr.strip()[:110]!r}",
           ok, cmd=f"python adif2xlsx.py verification\\cases\\q11_good.adi verification\\cases\\q11_empty.adi -o verification\\out\\q11b.xlsx --quiet")


def q11c_unwritable_output():
    good = os.path.join(HERE, "cases", "q11_good.adi")
    target = out_path("q11c_dir.xlsx")
    os.makedirs(target, exist_ok=True)          # a DIRECTORY where a file must go
    p = run([good, "-o", target])
    tb = "Traceback" in p.stderr
    ok = p.returncode != 0 and not tb
    record("Q11c output path is an existing directory (OSError while saving)",
           "clean error, no traceback, non-zero exit",
           f"rc={p.returncode} traceback={tb} stderr={p.stderr.strip()[:150]!r}",
           ok, cmd=f"python adif2xlsx.py verification\\cases\\q11_good.adi -o verification\\out\\q11c_dir.xlsx")


# ---------------------------------------------------------------- Q12: formula sweep
def q12_formula_sweep():
    payloads = [
        ("COMMENT", "=1+1"),
        ("NOTES", "=cmd|'/c calc'!A0"),
        ("NAME", "+1+1"),
        ("QTH", "-1+1"),
        ("MY_RIG", "@SUM(1+1)"),
        ("MY_ANTENNA", " =1+1"),          # leading space before '='
        ("MY_SIG", "\t=1+1"),             # leading tab before '='
        ("EMAIL", "-10"),                 # the RST-like shape that must survive
    ]
    fields = [("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200")] + payloads
    text = HDR + adif(fields) + "\n"
    p, rows, out, path = one("q12_formula_sweep.adi", text, "q12.xlsx")
    row = rows[0] if rows else {}
    formulas = []
    if os.path.exists(out):
        for sheet_index in (1, 2):
            xml = raw_sheet_xml(out, sheet_index)
            if "<f>" in xml or "<f " in xml:
                formulas.append(sheet_index)
    changed = {k: (v, row.get(k)) for k, v in payloads if row.get(k) != v}
    dangerous_untouched = [k for k, v in payloads if v[0] in "+-@" and row.get(k) != v]
    ok = p.returncode == 0 and not formulas and not dangerous_untouched
    record("Q12 formula sweep: '=', DDE, '@', '+', '-' payloads in both sheets",
           "no <f> element in either sheet; '@'/'+'/'-' values preserved verbatim; only a "
           "leading '=' defused",
           f"rc={p.returncode} sheets_with_<f>={formulas} changed_values={changed}",
           ok, note="a leading space or tab before '=' is not a formula trigger either",
           cmd=cmd_for(path, out))


def q12b_filename_injection():
    evil = write_case("=evil.adi", HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"),
                                               ("TIME_ON", "1200")]) + "\n")
    out = out_path("q12b.xlsx")
    if os.path.exists(out):
        os.remove(out)
    p = run([evil, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    src = rows[0].get("SOURCE_FILE") if rows else None
    formulas = [i for i in (1, 2) if os.path.exists(out)
                and ("<f>" in raw_sheet_xml(out, i) or "<f " in raw_sheet_xml(out, i))]
    ok = p.returncode == 0 and not formulas and isinstance(src, str) and src.endswith("evil.adi")
    record("Q12b a FILE NAMED '=evil.adi' (SOURCE_FILE is user-controlled text)",
           "SOURCE_FILE cell written as text, no formula element",
           f"rc={p.returncode} SOURCE_FILE={src!r} sheets_with_<f>={formulas}",
           ok, cmd='python adif2xlsx.py "verification\\cases\\=evil.adi" -o verification\\out\\q12b.xlsx')


# ---------------------------------------------------------------- Q13: markup interactions
def q13_comment_between_records():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>\n"
            + "<!-- generated by MyLogger -->\n"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW<EOR>\n")
    p, rows, out, path = one("q13_comment_midfile.adi", text, "q13.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("Q13 an XML comment between records is skipped, not a stop",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


def q14_html_after_records():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>\n"
            + "<html><body>LoTW error</body></html>\n"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW<EOR>\n")
    p, rows, out, path = one("q14_html_after.adi", text, "q14.xlsx")
    calls = [r.get("CALL") for r in rows]
    record("Q14 RECORDED: genuine HTML after real records still ends the scan",
           "record 1 kept; the record after the markup is dropped (intended)",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", True,
           note="intended: an HTML error page must not be parsed as a log",
           cmd=cmd_for(path, out))


def q15_closing_eod():
    text = (HDR + "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB</EOD>"
            + "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW</EOD>")
    p, rows, out, path = one("q15_close_eod.adi", text, "q15.xlsx")
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF"]
    record("Q15 '</EOD>' closing form (same code path as '</EOR>')",
           "2 QSOs", f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd=cmd_for(path, out))


def main():
    for fn in (q1_rst_minus, q2_rst_real_fixtures, q3_formula, q4_truncation,
               q5_control_bytes, q6_close_eor, q6b_slash_eor_midfile, q7_selfclosing,
               q8_stray_tag, q8b_closing_unknown_tag, q9_header_plus_unknown_record,
               q9b_headerless_unknown_record, q9c_vocabulary_false_positive,
               q9d_p5_single_call, q10_html_still_rejected, q10b_xml_prologue,
               q10c_xml_after_data, q11_skipped_file_exit, q11b_quiet_skipped_file,
               q11c_unwritable_output, q12_formula_sweep, q12b_filename_injection,
               q13_comment_between_records, q14_html_after_records, q15_closing_eod):
        fn()
    dump("q_sanitize")


if __name__ == "__main__":
    main()
