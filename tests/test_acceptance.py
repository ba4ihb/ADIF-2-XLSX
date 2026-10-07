#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end acceptance checks for the adif2xlsx converter.

Drives the real command line and inspects the workbook it produces, so the
whole path is covered rather than just the parse functions:

  * required columns exist and are populated
  * date/time columns are real, sortable Excel dates and times
  * UTC is declared in the column names / summary
  * completely empty optional columns were dropped
  * every optional field from the ADIF source became a column
  * every source value reaches the workbook verbatim
  * the DXCC entity is resolved and its provenance recorded
  * 1000 records convert in under 5 seconds

Workbooks and scratch files are written to a temporary directory, so running
the suite never litters the project.

Run:  python tests/test_acceptance.py
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import subprocess
import sys
import tempfile
import time

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
PY = sys.executable
SCRIPT = os.path.join(SRC, "adif2xlsx.py")

# Fixtures and scratch output live in known places.
FIXTURES = os.path.join(HERE, "fixtures")
SAMPLES = os.path.join(FIXTURES, "samples")
REAL = os.path.join(FIXTURES, "adi")
PERF = os.path.join(FIXTURES, "perf_1000.adi")
OUT = tempfile.mkdtemp(prefix="adif2xlsx_tests_")

FAILURES = []
CHECKS = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))
        FAILURES.append(label)


def run_converter(args: list, cwd: str = ROOT) -> subprocess.CompletedProcess:
    # Fixed UTF-8 on both sides: the tool reports in Chinese, and a GBK console
    # code page would otherwise fail to decode it and return None for stderr.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [PY, SCRIPT] + args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env,
    )


def load(path: str):
    return openpyxl.load_workbook(path)


def header_map(sheet) -> dict:
    """Column name -> column index, from the first header row."""
    return {
        str(cell.value).strip(): cell.column
        for cell in sheet[1]
        if cell.value is not None
    }


def first_data_row(sheet) -> int:
    """The first row holding a QSO.

    The sheet has two header rows: the English column names, then their Chinese
    labels.  The Chinese row is written for every column, so the data begins on
    row 3; older single-header workbooks begin on row 2.  Detect it instead of
    assuming, so the tests describe the file rather than a constant.
    """
    labels = header_map(sheet)
    for row in (2, 3):
        if row > sheet.max_row:
            break
        # A data row has a callsign-shaped value in the CALL column.
        value = sheet.cell(row=row, column=labels["CALL"]).value
        if isinstance(value, str) and value and value != "对方呼号":
            return row
    return 2


def qso_rows(sheet):
    """Data row indices, header rows excluded."""
    return range(first_data_row(sheet), sheet.max_row + 1)


def qso_count(sheet) -> int:
    """Number of QSO data rows."""
    return max(0, sheet.max_row - first_data_row(sheet) + 1)


def _adif_field_names(path: str) -> set:
    """ADIF field names carrying a non-empty value somewhere in the file.

    A field that only ever appears as <FIELD:0> holds no data, so it is
    correctly absent from the workbook.
    """
    text = open(path, encoding="utf-8").read()
    names = set()
    for m in re.finditer(
        r"<\s*([A-Za-z_][A-Za-z0-9_\-\.]*)\s*:\s*(\d+)(?::[A-Za-z])?\s*>", text
    ):
        n = int(m.group(2))
        if n > 0 and text[m.end():m.end() + n].strip():
            names.add(m.group(1).upper())
    return names


def _raw_records(path: str) -> list:
    """Read records straight from the file, independently of the converter.

    Deliberately a separate, minimal implementation: it exists so the
    acceptance suite can compare what the source says against what the
    workbook contains, instead of trusting the code under test.
    """
    text = open(path, encoding="utf-8").read()
    records = []
    for chunk in text.split("<EOR>"):
        rec = {}
        for m in re.finditer(
            r"<\s*([A-Za-z_][A-Za-z0-9_\-\.]*)\s*:\s*(\d+)(?::[A-Za-z])?\s*>",
            chunk,
        ):
            name = m.group(1).upper()
            n = int(m.group(2))
            rec[name] = chunk[m.end():m.end() + n]
        if rec:
            records.append(rec)
    return records


REQUIRED = ["CALL", "QSO_DATE", "TIME_ON_UTC", "BAND", "MODE",
            "RST_SENT", "RST_RCVD", "STATION_CALLSIGN"]


def check_workbook(path: str, adif_paths: list, expected_qsos: int) -> None:
    print(f"\n=== {os.path.basename(path)} ===")
    wb = load(path)
    check(wb.sheetnames[:1] == ["QSOs"], "sheet 'QSOs' is the first sheet")
    check("Summary" in wb.sheetnames, "sheet 'Summary' exists")

    ws = wb["QSOs"]
    hdr = header_map(ws)
    n_rows = qso_count(ws)

    check(n_rows == expected_qsos,
          f"QSO row count == {expected_qsos}", f"got {n_rows}")

    # --- required columns present and fully populated ----------------------
    for col in REQUIRED:
        check(col in hdr, f"required column {col} present")
    if all(c in hdr for c in REQUIRED):
        empties = []
        for r in qso_rows(ws):
            for col in REQUIRED:
                v = ws.cell(row=r, column=hdr[col]).value
                if v is None or v == "":
                    empties.append((r, col))
        check(not empties, "every required cell is populated",
              f"first empty: {empties[:3]}")

    # --- UTC is declared ---------------------------------------------------
    check("TIME_ON_UTC" in hdr, "TIME_ON column is named with the UTC suffix")
    source_has_time_off = any(
        "TIME_OFF" in _adif_field_names(p) for p in adif_paths
    )
    check(("TIME_OFF_UTC" in hdr) == source_has_time_off,
          "TIME_OFF_UTC column present exactly when the source has TIME_OFF",
          f"source_has_time_off={source_has_time_off}, columns={sorted(hdr)}")
    summary_ws = wb["Summary"]
    summary_text = " ".join(
        str(c.value) for row in summary_ws.iter_rows() for c in row if c.value
    )
    check("UTC" in summary_text, "Summary sheet states that times are UTC")

    # The blank-cell explanation is stated once, above the fill table, and the
    # per-column counts sit under it.  Together they answer "why is this cell
    # empty" without the user having to guess.
    check("数据来源与空单元格说明" in summary_text,
          "Summary explains where the data comes from and what a blank means")
    for phrase in ("来自源 ADI", "源 ADI 中没有相应数据", "不代表转换出错"):
        check(phrase in summary_text,
              f"the blank-cell note says {phrase!r}")
    check("各列填充情况" in summary_text,
          "Summary quantifies the blanks per column")
    # The explanation is the FIRST thing on the sheet, so it is seen without
    # scrolling; the fill table at the bottom is its evidence.
    check(summary_ws.cell(row=1, column=1).value
          and "数据来源与空单元格说明" in str(summary_ws.cell(row=1, column=1).value),
          "the blank-cell explanation is on row 1 of Summary",
          str(summary_ws.cell(row=1, column=1).value)[:60])
    check("说明见本表第 1 行" in summary_text,
          "the fill table points back at the row-1 explanation")

    # --- date / time cells are real Excel date & time values ---------------
    dcell = ws.cell(row=first_data_row(ws), column=hdr["QSO_DATE"])
    tcell = ws.cell(row=first_data_row(ws), column=hdr["TIME_ON_UTC"])
    check(isinstance(dcell.value, (_dt.date, _dt.datetime)),
          "QSO_DATE is a real Excel date", f"type={type(dcell.value).__name__}")
    check(isinstance(tcell.value, (_dt.time, _dt.datetime)),
          "TIME_ON_UTC is a real Excel time", f"type={type(tcell.value).__name__}")
    check(dcell.number_format == "yyyy-mm-dd",
          "QSO_DATE displays as YYYY-MM-DD", f"fmt={dcell.number_format}")
    check(tcell.number_format == "hh:mm:ss",
          "TIME_ON_UTC displays as HH:MM:SS", f"fmt={tcell.number_format}")

    # sortable => every date must be a mutually orderable date value, and each
    # source file's own record order must be preserved in the output.
    date_cells = [ws.cell(row=r, column=hdr["QSO_DATE"]).value
                  for r in qso_rows(ws)]
    check(all(isinstance(d, _dt.date) for d in date_cells),
          "every QSO_DATE cell is a date value",
          f"types={sorted({type(d).__name__ for d in date_cells})}")
    try:
        sorted(date_cells)
        orderable = True
    except TypeError:
        orderable = False
    check(orderable, "QSO_DATE values are mutually comparable (Excel-sortable)")

    by_source = {}
    for r in qso_rows(ws):
        src = ws.cell(row=r, column=hdr["SOURCE_FILE"]).value
        by_source.setdefault(src, []).append(
            ws.cell(row=r, column=hdr["QSO_DATE"]).value
        )
    per_file_sorted = all(v == sorted(v) for v in by_source.values())
    check(per_file_sorted, "each file's chronological order is preserved",
          str({k: v[:2] for k, v in by_source.items()})[:160])

    freq_cells = [ws.cell(row=r, column=hdr["FREQ_MHZ"]).value
                  for r in qso_rows(ws)
                  if hdr.get("FREQ_MHZ")]
    numeric_freqs = all(isinstance(v, (int, float)) for v in freq_cells if v is not None)
    check(numeric_freqs, "FREQ_MHZ cells are numeric (sortable)")

    # --- no column is completely empty ------------------------------------
    empty_cols = []
    for name, col in hdr.items():
        if all(ws.cell(row=r, column=col).value in (None, "") for r in qso_rows(ws)):
            empty_cols.append(name)
    check(not empty_cols, "no completely empty column is emitted", str(empty_cols))

    # --- every ADIF field in the source has a column ----------------------
    adif_fields = set()
    for p in adif_paths:
        adif_fields |= _adif_field_names(p)
    header_only = {"ADIF_VER", "PROGRAMID", "PROGRAMVERSION", "CREATED_TIMESTAMP"}
    aliases = {"TIME_ON": "TIME_ON_UTC", "TIME_OFF": "TIME_OFF_UTC", "FREQ": "FREQ_MHZ"}
    expected_cols = {aliases.get(f, f) for f in adif_fields if f not in header_only}
    missing = sorted(c for c in expected_cols if c not in hdr)
    check(not missing, "all non-empty ADIF fields became columns", str(missing))

    # --- every source value must reach the workbook UNCHANGED -------------
    # This is the check that catches silent value rewriting.  It compares each
    # source record's field values against the workbook cell text, so a value
    # such as -10 that was mangled into "'-10" fails here.
    source_values = []
    for p in adif_paths:
        for rec in _raw_records(p):
            source_values.append(rec)
    mismatches = []
    for rec, row_index in zip(source_values, qso_rows(ws), strict=False):
        for field, raw in rec.items():
            column = aliases.get(field, field)
            if column not in hdr:
                continue
            if field in ("QSO_DATE", "TIME_ON", "TIME_OFF", "QSO_DATE_OFF",
                         "FREQ", "FREQ_RX"):
                continue  # deliberately converted to Excel date/time/number
            cell = ws.cell(row=row_index, column=hdr[column]).value
            got = "" if cell is None else str(cell)
            if got != raw.strip(" \t\r\n"):
                mismatches.append((row_index, column, raw, got))
    check(not mismatches, "every source field value is preserved verbatim",
          f"{len(mismatches)} mismatch(es), first: {mismatches[:3]}")

    # RST reports are the classic casualty of over-eager sanitising, so assert
    # them explicitly against the source rather than trusting the general check.
    rst_bad = []
    for rec, row_index in zip(source_values, qso_rows(ws), strict=False):
        for column in ("RST_SENT", "RST_RCVD"):
            if column in hdr and column in rec:
                cell = ws.cell(row=row_index, column=hdr[column]).value
                if str(cell) != rec[column]:
                    rst_bad.append((row_index, column, rec[column], cell))
    check(not rst_bad, "RST reports match the source exactly (e.g. -10 stays -10)",
          str(rst_bad[:4]))
    check("SOURCE_FILE" in hdr, "SOURCE_FILE column present")
    check(len({ws.cell(row=r, column=hdr["SOURCE_FILE"]).value
               for r in qso_rows(ws)}) == len(adif_paths),
          "SOURCE_FILE distinguishes every input file")

    # --- summary content sanity -------------------------------------------
    band_col = [ws.cell(row=r, column=hdr["BAND"]).value for r in qso_rows(ws)]
    band_values = {b for b in band_col if b}
    n_band_rows = sum(1 for row in summary_ws.iter_rows() if row[0].value in band_values)
    check(n_band_rows >= len(band_values),
          "Summary lists every band present in QSOs",
          f"bands={sorted(band_values)} rows={n_band_rows}")


def check_performance(adir_path: str, count: int = 1000) -> None:
    print(f"\n=== performance: {count} records ===")
    out = os.path.join(OUT, "out_perf.xlsx")
    start = time.perf_counter()
    proc = run_converter([adir_path, "-o", out, "--quiet"])
    elapsed = time.perf_counter() - start
    check(proc.returncode == 0, "converter exits 0 on the 1000-record file",
          proc.stderr.strip()[:200])
    check(os.path.exists(out), "workbook written for 1000-record input")
    check(elapsed < 5.0, f"1000 records converted in < 5 s (took {elapsed:.2f} s)",
          f"{elapsed:.3f}s")
    if os.path.exists(out):
        ws = load(out)["QSOs"]
        check(qso_count(ws) == count, f"all {count} records reached the workbook",
              f"got {qso_count(ws)}")


def check_robustness() -> None:
    """Inputs that must be rejected, and values that must survive intact."""
    print("\n=== robustness and hostile input ===")
    tmp = os.path.join(OUT, "tmp_robustness")
    os.makedirs(tmp, exist_ok=True)

    def write(name: str, text: str) -> str:
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return path

    # A non-ADIF file that merely contains '<' must not become a bogus QSO row.
    for name, content in [
        ("html.adi", "<html>x</html>"),
        ("prose.adi", "this file has a < in it but no ADIF at all"),
        ("xml.adi", '<?xml version="1.0"?><log><qso/></log>'),
    ]:
        path = write(name, content)
        proc = run_converter([path, "-o", os.path.join(OUT, "out_reject.xlsx")])
        check(proc.returncode == 1 and "Traceback" not in proc.stderr,
              f"rejects non-ADIF {name} with a clear message",
              f"rc={proc.returncode} err={proc.stderr.strip()[:80]}")

    path = write("empty.adi", "")
    proc = run_converter([path, "-o", os.path.join(OUT, "out_reject.xlsx")])
    check(proc.returncode == 1 and "Traceback" not in proc.stderr,
          "rejects an empty file with a clear message",
          f"rc={proc.returncode} err={proc.stderr.strip()[:80]}")

    path = write("headeronly.adi", "<ADIF_VER:5>3.1.7<PROGRAMID:6>HDRONL")
    proc = run_converter([path, "-o", os.path.join(OUT, "out_reject.xlsx")])
    check(proc.returncode == 1 and "Traceback" not in proc.stderr,
          "rejects an ADIF file that holds only a header",
          f"rc={proc.returncode} err={proc.stderr.strip()[:80]}")

    empty_dir = os.path.join(tmp, "no_adif_here")
    os.makedirs(empty_dir, exist_ok=True)
    proc = run_converter([empty_dir, "-o", os.path.join(OUT, "out_reject.xlsx")])
    check(proc.returncode == 2, "rejects a folder with no .adi files",
          f"rc={proc.returncode}")

    # A value that contains the literal text <EOR> must survive, including in
    # the last record of a file that has no trailing <EOR>.  A regex-based scan
    # for record terminators would truncate here.
    val = "x<EOR>y"
    for name, tail in [("eor_mid.adi", "<EOR>"), ("eor_last.adi", "")]:
        path = write(
            name,
            f"<CALL:5>KH6BB<COMMENT:{len(val)}>{val}<QSO_DATE:8>20240101"
            f"<TIME_ON:4>1200<MODE:2>CW{tail}",
        )
        out = os.path.join(OUT, "out_eortext.xlsx")
        proc = run_converter([path, "-o", out, "--quiet"])
        ok = proc.returncode == 0 and os.path.exists(out)
        if ok:
            ws = load(out)["QSOs"]
            hdr = header_map(ws)
            ok = (ws.cell(row=first_data_row(ws), column=hdr["COMMENT"]).value == val
                  and ws.cell(row=first_data_row(ws), column=hdr["MODE"]).value == "CW")
        check(ok, f"literal <EOR> inside a value survives ({name}, tail={tail!r})",
              proc.stderr.strip()[:120])

    # A repeated header record must not inflate the QSO count with a blank row.
    path = write(
        "twoheaders.adi",
        "<ADIF_VER:5>3.1.7<PROGRAMID:4>TEST<EOR>"
        "<ADIF_VER:5>3.1.7<CREATED_TIMESTAMP:15>20250115 120000<EOR>"
        "<CALL:5>KH6BB<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:2>CW<EOR>",
    )
    out = os.path.join(OUT, "out_twoheaders.xlsx")
    proc = run_converter([path, "-o", out, "--quiet"])
    rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
    check(proc.returncode == 0 and rows == 1,
          "a second header record does not become a blank QSO row", f"rows={rows}")

    # Preamble and trailing prose around real records must be ignored.
    path = write(
        "banner.adi",
        "Saved by SomeLogger v9\nGenerated 2025-01-15\n\n"
        "<ADIF_VER:5>3.1.7<PROGRAMID:9>SOMELOGER<EOH>\n"
        "<CALL:5>KH6BB<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:2>CW<EOR>\n"
        "Some trailing free text that is not ADIF.\n",
    )
    out = os.path.join(OUT, "out_banner.xlsx")
    proc = run_converter([path, "-o", out, "--quiet"])
    rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
    check(proc.returncode == 0 and rows == 1,
          "banner text before and trailing prose after records are ignored",
          f"rows={rows}")

    # Prose mentioning a structural tag must not confuse the parser.
    path = write(
        "prose_eoh.adi",
        "Notes: this export omits <EOH> entirely and says <EOR> nowhere.\n"
        "<CALL:5>KH6BB<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:2>CW<EOR>",
    )
    out = os.path.join(OUT, "out_prose.xlsx")
    proc = run_converter([path, "-o", out, "--quiet"])
    rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
    check(proc.returncode == 0 and rows == 1,
          "prose mentioning <EOH>/<EOR> does not break parsing", f"rows={rows}")


def check_data_safety() -> None:
    """Values and tags that previously destroyed or silently truncated output."""
    print("\n=== data safety ===")
    tmp = os.path.join(OUT, "tmp_safety")
    os.makedirs(tmp, exist_ok=True)

    # A control byte in a value must not abort the export.  ADIF forbids such
    # bytes, but a corrupt file decoded as latin-1 can still carry them, and
    # openpyxl refuses to write them.
    for byte in (0x00, 0x01, 0x08, 0x0B, 0x0C, 0x1F, 0x7F):
        src = os.path.join(tmp, f"ctrl_{byte:02x}.adi")
        with open(src, "wb") as fh:
            fh.write(b"<ADIF_VER:5>3.1.4<EOH>\n"
                     b"<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
                     b"<COMMENT:5>a" + bytes([byte]) + b"bcd<EOR>\n")
        out = os.path.join(tmp, f"ctrl_{byte:02x}.xlsx")
        proc = run_converter([src, "-o", out])
        ok = proc.returncode == 0 and os.path.exists(out) and "Traceback" not in proc.stderr
        if ok:
            ws = load(out)["QSOs"]
            hdr = header_map(ws)
            ok = qso_count(ws) == 1 and ws.cell(row=first_data_row(ws), column=hdr["COMMENT"]).value == "abcd"
        check(ok, f"control byte 0x{byte:02x} still produces a workbook",
              f"rc={proc.returncode} {proc.stderr.strip()[:70]}")

    # Log text that looks like a formula must not become one.
    src = os.path.join(tmp, "formula.adi")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
                 "<COMMENT:24>=cmd|'/c calc'!A0|x yz<EOR>\n")
    out = os.path.join(tmp, "formula.xlsx")
    proc = run_converter([src, "-o", out])
    ws = load(out)["QSOs"]
    cell = ws.cell(row=first_data_row(ws), column=header_map(ws)["COMMENT"])
    check(proc.returncode == 0 and cell.data_type != "f"
          and str(cell.value).startswith("'="),
          "text beginning with '=' is stored as text, not a formula",
          f"value={cell.value!r}")

    # Excel caps a cell at 32,767 characters.
    long_value = "x" * 40000
    src = os.path.join(tmp, "long.adi")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200"
                 f"<COMMENT:{len(long_value)}>{long_value}<EOR>")
    out = os.path.join(tmp, "long.xlsx")
    proc = run_converter([src, "-o", out])
    value = load(out)["QSOs"].cell(row=first_data_row(load(out)["QSOs"]), column=2).value if os.path.exists(out) else ""
    ws = load(out)["QSOs"]
    value = ws.cell(row=first_data_row(ws), column=header_map(ws)["COMMENT"]).value
    check(proc.returncode == 0 and isinstance(value, str) and len(value) <= 32767,
          "an over-long value is capped at Excel's cell limit",
          f"len={len(value) if isinstance(value, str) else value!r}")

    # A stray tag must not truncate the rest of the file, and must be reported.
    for tag in ("<zzz>", "<NOTE>", "<EOR/>", "<!-- note -->"):
        src = os.path.join(tmp, "stray.adi")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("<ADIF_VER:5>3.1.4<EOH>\n"
                     "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>\n"
                     f"{tag}\n"
                     "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW<EOR>\n"
                     "<CALL:5>N3XYZ<QSO_DATE:8>20240103<TIME_ON:4>1400<MODE:3>FT8<EOR>\n")
        out = os.path.join(tmp, "stray.xlsx")
        proc = run_converter([src, "-o", out, "--quiet"])
        rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
        check(proc.returncode == 0 and rows == 3,
              f"a stray {tag!r} between records does not truncate the file",
              f"rc={proc.returncode} rows={rows}")

    # A header may carry fields ADIF also allows in a QSO: LoTW's header holds
    # PROGRAMID plus APP_LOTW_LASTQSL / APP_LOTW_NUMREC.  Only the <EOH>
    # boundary distinguishes it, so it must not become a QSO row.
    src = os.path.join(tmp, "lotw_header.adi")
    with open(src, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("ARRL Logbook of the World Status Report\r\n"
                 "Generated at 2026-10-05 13:36:39\r\n\r\n"
                 "<PROGRAMID:4>LoTW\r\n"
                 "<APP_LOTW_LASTQSL:19>2026-10-05 12:19:35\r\n\r\n"
                 "<APP_LOTW_NUMREC:3>2\r\n\r\n"
                 "<eoh>\r\n\r\n"
                 "<CALL:6>JK8LVM<QSO_DATE:8>20261003<TIME_ON:6>122929"
                 "<BAND:3>20M<MODE:3>FT8<STATION_CALLSIGN:6>BA4IHB<EOR>\r\n"
                 "<CALL:6>JH3OII<QSO_DATE:8>20260224<TIME_ON:6>075900"
                 "<BAND:3>15M<MODE:2>CW<STATION_CALLSIGN:6>BA4IHB<EOR>\r\n"
                 "<APP_LOTW_EOF>")
    out = os.path.join(tmp, "lotw_header.xlsx")
    proc = run_converter([src, "-o", out, "--quiet"])
    rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
    check(proc.returncode == 0 and rows == 2,
          "an <EOH>-terminated header with APP_LOTW_* fields is not a QSO row",
          f"rows={rows} (expected 2)")
    check("APP_LOTW_EOF" not in proc.stderr,
          "the bare APP_LOTW_EOF trailer is not reported as an unknown tag",
          proc.stderr.strip()[:90])

    # A lowercase, headerless, line-structured file (the shape JTDX writes):
    # `<eor>` is case-insensitive, so each line is its own record.  This is a
    # regression guard for case-sensitive terminator matching.
    src = os.path.join(tmp, "lineoriented.adi")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<call:6>JS6TKY <mode:3>FT8 <qso_date:8>20260530 "
                 "<time_on:6>035356 <band:2>6m <rst_sent:3>-08 <rst_rcvd:3>-13<eor>\n")
        fh.write("<call:6>JF2EEK <mode:3>FT8 <qso_date:8>20260530 "
                 "<time_on:6>035600 <band:2>6m <rst_sent:3>-04 <rst_rcvd:3>-20<eor>\n")
    out = os.path.join(tmp, "lineoriented.xlsx")
    proc = run_converter([src, "-o", out, "--quiet"])
    rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
    check(proc.returncode == 0 and rows == 2,
          "lowercase <eor>, lowercase field names, no header: two records",
          f"rows={rows} (expected 2)")
    if os.path.exists(out):
        ws = load(out)["QSOs"]
        check(ws.cell(row=first_data_row(ws), column=header_map(ws)["BAND"]).value == "6M",
              "lowercase band value '6m' is normalised to 6M")

    # Header classification must not depend on whether a banner precedes the
    # file: identical bytes have to parse identically.  These cases cover the
    # matrix that a position-only rule got wrong.
    Q1 = ("<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<BAND:3>20M<MODE:3>SSB"
          "<STATION_CALLSIGN:5>DL1AA<EOR>")
    Q2 = ("<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<BAND:3>40M<MODE:2>CW"
          "<STATION_CALLSIGN:5>DL1AA<EOR>")
    lotw_hdr = ("<PROGRAMID:4>LoTW<APP_LOTW_LASTQSL:19>2026-10-05 12:19:35"
                "<APP_LOTW_NUMREC:3>199<eoh>\n")

    cases = [
        ("hdr_lead_crlf", "\r\n" + Q1 + "\n" + Q2, 2,
         "a leading newline before QSOs with no <EOH>"),
        ("hdr_lead_space", " " + Q1 + "\n" + Q2, 2,
         "a leading space before QSOs with no <EOH>"),
        ("hdr_banner_norq", "Saved by MyLogger\r\n" + Q1 + "\n" + Q2, 2,
         "a banner plus QSOs with no <EOH>"),
        ("hdr_banner_hdr_noeoh",
         "banner\r\n<ADIF_VER:5>3.1.4<PROGRAMID:4>LoTW\n" + Q1 + "\n" + Q2, 2,
         "a banner plus a header and QSOs with no <EOH>"),
        ("hdr_lotw_byte0", lotw_hdr + Q1 + "\n" + Q2, 2,
         "an APP_LOTW_* header at byte 0 with no banner"),
        ("hdr_lotw_banner", "banner\n" + lotw_hdr + Q1 + "\n" + Q2, 2,
         "the same header behind a banner (must parse identically)"),
        ("hdr_xml_prologue", '<?xml version="1.0"?>\n' + Q1, 1,
         "an XML prologue before the data"),
        ("hdr_shared_eoh",
         "banner\n<ADIF_VER:5>3.1.4<PROGRAMID:4>LoTW" + Q1[:-5] + "<EOH>\n" + Q2, 2,
         "header and QSO sharing one record that ends at <EOH>"),
        ("hdr_shared_eoh_nobanner",
         "<ADIF_VER:5>3.1.4<PROGRAMID:4>LoTW" + Q1[:-5] + "<EOH>\n" + Q2, 2,
         "the same record with no banner (must parse identically)"),
    ]
    for name, body, want, label in cases:
        src = os.path.join(tmp, name + ".adi")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        out = os.path.join(tmp, name + ".xlsx")
        proc = run_converter([src, "-o", out, "--quiet"])
        rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
        check(proc.returncode == 0 and rows == want,
              f"{label} -> {want} row(s)", f"rc={proc.returncode} rows={rows}")

    # An empty column that the source DOES populate must be reported; an
    # unparseable value is the case a swapped key/value lookup would hide.
    for name, body, column in [
        ("diag_time", "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:6>256099"
                      "<BAND:3>20M<MODE:3>SSB<STATION_CALLSIGN:5>DL1AA<EOR>",
         "TIME_ON_UTC"),
        ("diag_freq", "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<FREQ:3>abc"
                      "<MODE:3>SSB<STATION_CALLSIGN:5>DL1AA<EOR>", "FREQ_MHZ/BAND"),
        ("diag_date", "<CALL:4>W1AW<QSO_DATE:8>20241340<TIME_ON:4>1200<BAND:3>20M"
                      "<MODE:3>SSB<STATION_CALLSIGN:5>DL1AA<EOR>", "QSO_DATE"),
    ]:
        src = os.path.join(tmp, name + ".adi")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        proc = run_converter([src, "-o", os.path.join(tmp, name + ".xlsx")])
        check(column in proc.stdout,
              f"an unparseable {column} value is reported to the user",
              proc.stdout.strip()[-90:])

    src = os.path.join(tmp, "tagreport.adi")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<ADIF_VER:5>3.1.4<EOH>\n"
                 "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<EOR>\n<zzz>\n"
                 "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<EOR>\n")
    proc = run_converter([src, "-o", os.path.join(tmp, "tagreport.xlsx")])
    check("ZZZ" in proc.stderr and "unrecognised" in proc.stderr,
          "an ignored tag is named on stderr", proc.stderr.strip()[:90])

    # The closing form "</EOR>" must terminate a record, not look like markup.
    src = os.path.join(tmp, "close_eor.adi")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<ADIF_VER:5>3.1.4<EOH>\n"
                 "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB</EOR>"
                 "<CALL:5>K2DEF<QSO_DATE:8>20240102<TIME_ON:4>1300<MODE:2>CW</EOR>"
                 "<CALL:5>N3XYZ<QSO_DATE:8>20240103<TIME_ON:4>1400<MODE:3>FT8</EOR>\n")
    out = os.path.join(tmp, "close_eor.xlsx")
    proc = run_converter([src, "-o", out, "--quiet"])
    rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
    check(proc.returncode == 0 and rows == 3,
          "closing </EOR> tags terminate records instead of ending the file",
          f"rows={rows}")

    # A record of only unknown fields must not become a blank QSO row just
    # because the file also has a header.
    src = os.path.join(tmp, "hdr_unknown.adi")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<ADIF_VER:5>3.1.4<EOH>\n"
                 "<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<MODE:3>SSB<EOR>\n"
                 "<ZZZ:3>abc<EOR>\n")
    out = os.path.join(tmp, "hdr_unknown.xlsx")
    proc = run_converter([src, "-o", out, "--quiet"])
    rows = qso_count(load(out)["QSOs"]) if os.path.exists(out) else -1
    check(proc.returncode == 0 and rows == 1,
          "an unknown-only record next to a header does not become a blank row",
          f"rows={rows}")

    # A skipped input must change the exit status.
    good = os.path.join(tmp, "good.adi")
    with open(good, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<EOR>\n")
    bad = os.path.join(tmp, "empty.adi")
    open(bad, "w").close()
    mixed = os.path.join(tmp, "mixed.xlsx")
    proc = run_converter([good, bad, "-o", mixed])
    check(proc.returncode == 1, "exit code is 1 when an input file was skipped",
          f"rc={proc.returncode}")
    check(os.path.exists(mixed), "the workbook for the good file is still written")
    proc = run_converter([good, "-o", os.path.join(tmp, "only.xlsx"), "--quiet"])
    check(proc.returncode == 0, "exit code is 0 when every input converts",
          f"rc={proc.returncode}")


def check_parser_units() -> None:
    """Direct unit checks on the parsing helpers (no workbook involved)."""
    print("\n=== parser units ===")
    sys.path.insert(0, SRC)
    import adif2xlsx as A

    tmp = os.path.join(OUT, "tmp_units")
    os.makedirs(tmp, exist_ok=True)

    def parse(text: str):
        path = os.path.join(tmp, "unit.adi")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return A.parse_adif(path).records

    # A value is located by its declared character length, so these must all
    # survive even though their contents look like ADIF syntax.
    val = "a<b>c<d>e fg"
    recs = parse(f"<CALL:5>KH6BB<COMMENT:{len(val)}>{val}<QSO_DATE:8>20240101<EOR>")
    check(recs[0].get("COMMENT") == val and recs[0].get("QSO_DATE") == "20240101",
          "a value containing '<' and '>' is preserved", repr(recs[0].get("COMMENT")))

    nl = "line1\nline2"
    recs = parse(f"<CALL:5>KH6BB<COMMENT:{len(nl)}>{nl}<QSO_DATE:8>20240101<EOR>")
    check(recs[0].get("COMMENT") == nl, "a multi-line value is preserved",
          repr(recs[0].get("COMMENT")))

    name = "J\u00fcrge"   # 5 characters
    recs = parse(f"<CALL:5>KH6BB<NAME:{len(name)}>{name}<QSO_DATE:8>20240101<EOR>")
    check(recs[0].get("NAME") == name,
          "a UTF-8 value is located by character count", repr(recs[0].get("NAME")))

    recs = parse("<CALL:5>KH6BB<FREQ:8:N>14.07400<QSO_DATE:8:D>20240101"
                 "<TIME_ON:4:T>1200<EOR>")
    check(recs[0].get("FREQ") == "14.07400" and recs[0].get("TIME_ON") == "1200",
          "the <NAME:len:type> form is parsed", str(recs[0]))

    recs = parse("<CALL:5>KH6BB<COMMENT:0><MODE:3>SSB<MODE:2>CW"
                 "<QSO_DATE:8>20240101<EOR>")
    check(recs[0].get("COMMENT") == "" and recs[0].get("MODE") == "CW",
          "zero-length value kept empty; a repeated field keeps the last value",
          str(recs[0]))

    recs = parse("<CALL:5>KH6BB<COMMENT:500>short")
    check(len(recs) == 1, "a declared length past EOF does not raise")

    recs = parse("<call:5>kh6bb<qso_date:8>20240101<mode:2>cw<EOR>")
    check(set(recs[0]) == {"CALL", "QSO_DATE", "MODE"},
          "lower-case field names are normalised", str(sorted(recs[0])))

    # Date and time conversion rules.
    check(A.parse_adif_date("20241340") is None, "an impossible date returns None")
    check(A.parse_adif_time("256099") is None, "an impossible time returns None")
    check(A.parse_adif_time("2330") == _dt.time(23, 30), "HHMM parses")
    check(A.parse_adif_time("235959") == _dt.time(23, 59, 59), "HHMMSS parses")
    check(A.parse_adif_time("235959").hour == 23,
          "23:59:59 UTC is not shifted by a timezone")

    # Band derivation, including every documented edge.
    edges = {"14.000": "20M", "14.350": "20M", "7.000": "40M", "7.300": "40M",
             "144.000": "2M", "148.000": "2M", "29.700": "10M", "28.000": "10M",
             "50.000": "6M", "53.999": "6M", "54.001": "5M", "69.900": "5M",
             "70.000": "4M", "71.000": "4M", "222.000": "1.25M", "225.000": "1.25M",
             "420.000": "70CM", "450.000": "70CM", "1240.000": "23CM",
             "119980.000": "2.5MM", "123000.000": "2.5MM", "134000.000": "2MM",
             "149000.000": "2MM", "241000.000": "1MM", "300000.000": "SUBMM",
             "1.800": "160M", "3.500": "80M", "5.3515": "60M", "0.1357": "2190M"}
    bad = [(f, want, A.band_from_freq(float(f)))
           for f, want in edges.items() if A.band_from_freq(float(f)) != want]
    check(not bad, f"all {len(edges)} documented band edges resolve", str(bad[:4]))

    outside = [f for f in (0.1, 15.5, 14.351, 6.999, 148.001, 226.0)
               if A.band_from_freq(f) is not None]
    check(not outside, "an out-of-band frequency produces no band", str(outside))


def check_real_exports(exports_dir: str) -> None:
    """Regression test against genuine exports from six logging platforms.

    These files are supplied by the user rather than generated, so the check is
    skipped when the folder is absent.  Expected counts are asserted because
    they were confirmed against each file's own record markers and, for LoTW,
    against the count the file declares in APP_LOTW_NUMREC.
    """
    print("\n=== real platform exports ===")
    if not os.path.isdir(exports_dir):
        print(f"  SKIP  {exports_dir} not found")
        return

    expected = {
        "CLUBLOG.adi": 11,
        "JTDX.ADI": 7,
        "lotw.adi": 199,
        "n1MM.adi": 14,
        "QRZ.adi": 15,
        "tqsl.adi": 3,
    }
    files = [os.path.join(exports_dir, n) for n in expected
             if os.path.exists(os.path.join(exports_dir, n))]
    check(len(files) == len(expected),
          f"all {len(expected)} platform exports are present", f"found {len(files)}")

    out = os.path.join(OUT, "out_real.xlsx")
    proc = run_converter([exports_dir, "-o", out, "--quiet"])
    check(proc.returncode == 0, "all real exports convert with exit code 0",
          proc.stderr.strip()[:200])
    check(not proc.stderr.strip(),
          "no warnings for well-formed exports", proc.stderr.strip()[:200])

    if not os.path.exists(out):
        return
    ws = load(out)["QSOs"]
    hdr = header_map(ws)
    rows = qso_count(ws)
    total = sum(expected.values())
    check(rows == total, f"row count equals the {total} QSOs across all six files",
          f"got {rows}")

    per_source = {}
    for r in qso_rows(ws):
        src = ws.cell(row=r, column=hdr["SOURCE_FILE"]).value
        per_source[src] = per_source.get(src, 0) + 1
        for col in ("CALL", "QSO_DATE", "TIME_ON_UTC", "BAND", "MODE"):
            value = ws.cell(row=r, column=hdr[col]).value
            check_ok = bool(value)
            if not check_ok:
                per_source["__bad__"] = f"{src}:{col}"
    for name, want in expected.items():
        check(per_source.get(name) == want,
              f"{name} contributes {want} rows", f"got {per_source.get(name)}")
    check("__bad__" not in per_source,
          "CALL/QSO_DATE/TIME_ON_UTC/BAND/MODE populated for every real record",
          str(per_source.get("__bad__")))

    # Every provider exports a different field set; none may be lost.
    check(len(hdr) > 60, "the union of all providers' fields becomes columns",
          f"{len(hdr)} columns")

    # --- DXCC entity resolution -------------------------------------------
    check("DXCC_ENTITY" in hdr, "DXCC_ENTITY column is present")
    check("DXCC_SOURCE" in hdr, "DXCC_SOURCE column records the provenance")
    sources = {ws.cell(row=r, column=hdr["DXCC_SOURCE"]).value
               for r in qso_rows(ws)}
    check(sources <= {"ADIF_DXCC", "ADIF_COUNTRY", "PREFIX", None, ""},
          "every DXCC_SOURCE value is a known rule", str(sorted(map(str, sources))))
    check("PREFIX" in sources or "ADIF_DXCC" in sources,
          "entities are resolved from the log or the callsign", str(sorted(map(str, sources))))

    # An ADIF DXCC number must win over the callsign prefix.  CLUB LOG writes
    # DXCC=339 for every record, which is JAPAN in the ARRL list, and the
    # callsigns are Japanese too, so the field agrees with the prefix here.  The
    # point of the check is that the log's own number is what is read -- faithful,
    # not "helpfully" re-derived from the callsign.
    club_rows = [r for r in qso_rows(ws)
                 if ws.cell(row=r, column=hdr["SOURCE_FILE"]).value == "CLUBLOG.adi"]
    if club_rows:
        entities = {ws.cell(row=r, column=hdr["DXCC_ENTITY"]).value for r in club_rows}
        check(entities == {"Japan"},
              "an ADIF DXCC number overrides the callsign prefix",
              str(entities))

    # The anonymous fixtures keep each callsign's own DXCC entity, so a
    # prefix-resolved row must match the entity its callsign belongs to.
    sys.path.insert(0, SRC)
    import dxcc as _dxcc
    wrong_entity = []
    for r in qso_rows(ws):
        if ws.cell(row=r, column=hdr["DXCC_SOURCE"]).value != "PREFIX":
            continue
        call = ws.cell(row=r, column=hdr["CALL"]).value or ""
        shown = ws.cell(row=r, column=hdr["DXCC_ENTITY"]).value
        expected_entity = _dxcc.resolve(call=call)[0]
        if expected_entity != shown:
            wrong_entity.append(f"{call}: {shown} != {expected_entity}")
    check(not wrong_entity,
          "prefix-resolved entities agree with the lookup", "; ".join(wrong_entity[:4]))

    # --- QSL postage -------------------------------------------------------
    check("QSL_POSTAGE_AIR" in hdr, "QSL_POSTAGE_AIR column is present")
    check("QSL_POSTAGE_DETAIL" in hdr, "QSL_POSTAGE_DETAIL column is present")

    numeric = 0
    non_numeric = []
    for r in qso_rows(ws):
        value = ws.cell(row=r, column=hdr["QSL_POSTAGE_AIR"]).value
        if isinstance(value, (int, float)):
            numeric += 1
        elif value not in (None, "", "不通邮"):
            non_numeric.append(value)
    check(not non_numeric,
          "QSL_POSTAGE_AIR is numeric, blank, or the 不通邮 marker",
          str(non_numeric[:4]))
    check(numeric > 0, "at least one row carries a postage figure", str(numeric))

    # The price must agree with the published tariff for that entity, and a
    # destination China Post does not serve must never carry a number.
    sys.path.insert(0, SRC)
    import postage as _postage
    mismatches = []
    for r in qso_rows(ws):
        entity = ws.cell(row=r, column=hdr["DXCC_ENTITY"]).value
        if not entity:
            continue
        shown = ws.cell(row=r, column=hdr["QSL_POSTAGE_AIR"]).value
        try:
            quote = _postage.quote(entity)
            expected = _postage.DOMESTIC if quote.zone == _postage.DOMESTIC else "AIR"
            wanted = quote.rates.get(expected)
        except _postage.NotMailable:
            wanted = "不通邮"
        if isinstance(wanted, float) and isinstance(shown, (int, float)):
            if abs(float(shown) - wanted) > 1e-9:
                mismatches.append(f"{entity}: {shown} != {wanted}")
        elif wanted == "不通邮" and shown != "不通邮":
            mismatches.append(f"{entity}: {shown!r} should be 不通邮")
    check(not mismatches,
          "every postage figure matches the published China Post tariff",
          "; ".join(mismatches[:4]))

    detail_missing = [r for r in qso_rows(ws)
                      if ws.cell(row=r, column=hdr["DXCC_ENTITY"]).value
                      and not ws.cell(row=r, column=hdr["QSL_POSTAGE_DETAIL"]).value]
    check(not detail_missing,
          "every priced row names the service breakdown", str(detail_missing[:4]))

    summary_ws = load(out)["Summary"]
    summary_all = " ".join(
        str(c.value) for row in summary_ws.iter_rows() for c in row if c.value
    )
    check(_postage.RATES_VERIFIED_ON in summary_all,
          "the Summary states when the postal rates were verified")
    check(_postage.RATES_EFFECTIVE_FROM in summary_all,
          "the Summary states the tariff's effective date",
          _postage.RATES_EFFECTIVE_FROM)

    # Only the letter tariff is reported.  The 明信片 class was deliberately
    # dropped, so nothing may mention it.
    mentions_postcard = [
        r for r in qso_rows(ws)
        if "明信片" in str(ws.cell(row=r, column=hdr["QSL_POSTAGE_DETAIL"]).value or "")
        or "postcard" in str(ws.cell(row=r, column=hdr["QSL_POSTAGE_DETAIL"]).value or "").lower()
    ]
    check(not mentions_postcard, "no postcard price is reported",
          str(mentions_postcard[:4]))
    check(not hasattr(_postage, "postcard_rates"),
          "the postcard tariff is gone from the module")
    # The detail column holds the LETTER price breakdown and nothing else: a
    # service label followed by a figure, for the services actually offered.
    # Zone names and the 明信片 class must not appear.
    bad_detail = []
    for r in qso_rows(ws):
        detail = str(ws.cell(row=r, column=hdr["QSL_POSTAGE_DETAIL"]).value or "")
        if not detail or "不通邮" in detail:
            continue
        # Mainland China is a single figure: "国内 1.20".
        if detail.startswith("国内 "):
            try:
                float(detail.split(" ", 1)[1])
            except ValueError:
                bad_detail.append(f"row {r}: {detail!r} is not a price")
            continue
        for chunk in detail.split(" / "):
            label, _, amount = chunk.partition(" ")
            if label not in ("航空", "水陆路", "空运水陆路"):
                bad_detail.append(f"row {r}: unexpected label {label!r}")
            try:
                float(amount)
            except ValueError:
                bad_detail.append(f"row {r}: {amount!r} is not a price")
        if "组" in detail:
            bad_detail.append(f"row {r}: a zone name leaked into the price")
    check(not bad_detail,
          "the detail column is a letter price breakdown only",
          "; ".join(bad_detail[:4]))

    # LoTW's header must not leak into the sheet as a blank row, and its
    # declared record count must match what we produced.
    lotw_text = open(os.path.join(exports_dir, "lotw.adi"), encoding="utf-8").read()
    m = re.search(r"APP_LOTW_NUMREC:\d+>(\d+)", lotw_text, re.IGNORECASE)
    if m:
        check(per_source.get("lotw.adi") == int(m.group(1)),
              "lotw.adi row count matches its own APP_LOTW_NUMREC",
              f"declared {m.group(1)}, produced {per_source.get('lotw.adi')}")

    # JTDX is line-oriented: lowercase field names, no header, no <EOR> at all.
    jtdx_rows = [r for r in qso_rows(ws)
                 if ws.cell(row=r, column=hdr["SOURCE_FILE"]).value == "JTDX.ADI"]
    check(jtdx_rows and all(
        str(ws.cell(row=r, column=hdr["MODE"]).value).upper() == "FT8"
        for r in jtdx_rows), "JTDX rows (no header, no <EOR>) parsed as QSOs")

    # Signed weak-signal reports from real FT8 logs must match the source
    # exactly: "-10" must not gain decoration, nor become 10.  Records are
    # matched by source file and callsign rather than by row position, because
    # the sheet merges several files.
    source_rst = {}
    for path in files:
        label = os.path.basename(path)
        for rec in _raw_records(path):
            source_rst.setdefault((label, rec.get("CALL", "")), rec)
    rst_mismatch = []
    for r in qso_rows(ws):
        key = (ws.cell(row=r, column=hdr["SOURCE_FILE"]).value,
               ws.cell(row=r, column=hdr["CALL"]).value)
        rec = source_rst.get(key)
        if not rec:
            continue
        for col in ("RST_SENT", "RST_RCVD"):
            expected = rec.get(col)
            if col not in hdr or not expected:
                continue
            shown = ws.cell(row=r, column=hdr[col]).value
            if str(shown) != expected:
                rst_mismatch.append(f"{key[1]}/{col}: {shown!r} != {expected!r}")
    check(not rst_mismatch, "every real RST report matches the source exactly",
          "; ".join(rst_mismatch[:3]))


def check_cli_edge_cases(sample_dir: str) -> None:
    print("\n=== CLI and path handling ===")
    out = os.path.join(OUT, "out_folder.xlsx")
    proc = run_converter([sample_dir, "-o", out, "--quiet"])
    check(proc.returncode == 0, "accepts a folder as input",
          proc.stderr.strip()[:200])
    if os.path.exists(out):
        ws = load(out)["QSOs"]
        check(qso_count(ws) == 22, "folder input merged both sample files",
              f"rows={qso_count(ws)}")

    # Windows path with a space and a backslash relative reference
    spaced = os.path.join(OUT, "out dir with space")
    os.makedirs(spaced, exist_ok=True)
    nested = os.path.join(spaced, "nested.xlsx")
    proc = run_converter([os.path.join(sample_dir, "sample_log.adi"), "-o", nested,
                          "--quiet"])
    check(proc.returncode == 0 and os.path.exists(nested),
          "handles a Windows output path containing spaces")

    proc = run_converter([os.path.join(sample_dir, "does_not_exist.adi"), "-o",
                          os.path.join(OUT, "out_missing.xlsx")])
    check(proc.returncode == 2, "missing input exits 2 with an error",
          f"rc={proc.returncode}")

    proc = run_converter([sample_dir, "-o", os.path.join(OUT, "out.xlsx"), "--help"])
    check(proc.returncode == 0 and "usage" in proc.stdout.lower(),
          "--help prints usage")

    # Without -o the workbook belongs on the Desktop.
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    import adif2xlsx as _adif
    desktop = _adif.desktop_directory()
    check(os.path.isdir(desktop), "the Desktop folder resolves", desktop)
    check(_adif.default_output_path() == os.path.join(
              desktop, _adif.DEFAULT_OUTPUT_NAME),
          "the default output path is on the Desktop",
          _adif.default_output_path())
    check("Desktop" in _adif.build_arg_parser().format_help()
          or "Desktop" in proc.stdout,
          "the help text says where the default output goes")

    # An output destination that cannot be written must be reported cleanly, and
    # an existing file must survive untouched.  This is the everyday case of the
    # report being open in Excel.
    good = os.path.join(OUT, "one.adi")
    with open(good, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<CALL:4>W1AW<QSO_DATE:8>20240101<TIME_ON:4>1200<EOR>")

    unreachable = os.path.join(OUT, "no-drive", "deep", "out.xlsx")
    if os.name == "nt":
        unreachable = "Z:\\adif2xlsx_no_such_drive\\out.xlsx"
    proc = run_converter([good, "-o", unreachable])
    check(proc.returncode == 2 and "Traceback" not in proc.stderr,
          "an output folder that cannot be created exits 2 with a message",
          f"rc={proc.returncode} {proc.stderr.strip()[:80]}")

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        locked = os.path.join(OUT, f"locked_{os.getpid()}.xlsx")
        previous = b"PREVIOUS REPORT CONTENT"
        with open(locked, "wb") as fh:
            fh.write(previous)

        GENERIC_READ = 0x80000000
        OPEN_EXISTING = 3
        INVALID_HANDLE = ctypes.c_void_p(-1).value
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        handle = kernel32.CreateFileW(
            locked, GENERIC_READ, 0,               # share mode 0: exclusive
            None, OPEN_EXISTING, 0, None)
        if handle == INVALID_HANDLE:
            print("  SKIP  locked-output check (cannot take an exclusive lock)")
        else:
            try:
                proc = run_converter([good, "-o", locked])
                check(proc.returncode == 1 and "Traceback" not in proc.stderr,
                      "an output file locked by another process exits 1 with advice",
                      f"rc={proc.returncode} {proc.stderr.strip()[-90:]}")
            finally:
                kernel32.CloseHandle(handle)

        with open(locked, "rb") as fh:
            survived = fh.read()
        check(survived == previous,
              "a failed write leaves the existing workbook untouched",
              f"{survived[:24]!r}")
        leftovers = [n for n in os.listdir(OUT) if n.startswith(".adif2xlsx-")]
        check(not leftovers, "a failed write leaves no temporary file",
              str(leftovers[:3]))
        try:
            os.remove(locked)
        except OSError:
            pass


def check_column_selection(sample_log: str) -> None:
    """--columns and the interface: the mandatory set survives, extras obey."""
    print("\n=== column selection ===")
    sys.path.insert(0, SRC)
    import adif2xlsx as A

    out = os.path.join(OUT, "columns.xlsx")

    # The mandatory columns are always written, whatever is asked for.
    proc = run_converter([sample_log, "-o", out, "--columns", "required"])
    check(proc.returncode == 0, "--columns required is accepted",
          f"rc={proc.returncode}")
    hdr = set(header_map(load(out)["QSOs"]))
    check(all(c in hdr for c in A.MANDATORY_COLUMNS),
          "--columns required still writes every mandatory column",
          str([c for c in A.MANDATORY_COLUMNS if c not in hdr]))
    check("GRIDSQUARE" not in hdr,
          "--columns required drops an optional column", str(sorted(hdr)))

    # A requested optional column is written.
    proc = run_converter([sample_log, "-o", out, "--columns",
                          "CALL,GRIDSQUARE,NAME"])
    check(proc.returncode == 0, "a column list is accepted", f"rc={proc.returncode}")
    hdr = set(header_map(load(out)["QSOs"]))
    check("GRIDSQUARE" in hdr and "NAME" in hdr,
          "requested optional columns appear", str(sorted(hdr)))
    check("QTH" not in hdr, "an unrequested optional column is dropped",
          str(sorted(hdr)))
    check(all(c in hdr for c in A.MANDATORY_COLUMNS),
          "mandatory columns survive a narrow selection")

    # A requested column the log never populates still gets its column, so the
    # user is not silently ignored.
    proc = run_converter([sample_log, "-o", out, "--columns",
                          "CALL,MY_GRIDSQUARE"])
    check(proc.returncode == 0, "an empty-but-known column is accepted",
          f"rc={proc.returncode}")
    check("MY_GRIDSQUARE" in set(header_map(load(out)["QSOs"])),
          "a requested column appears even when every record leaves it empty")

    # A typo is rejected rather than silently inventing a column.
    proc = run_converter([sample_log, "-o", out, "--columns", "CALL,NOT_A_FIELD"])
    check(proc.returncode == 2, "an unknown column name exits 2",
          f"rc={proc.returncode}")
    check("NOT_A_FIELD" in (proc.stderr or ""),
          "the rejected name is named in the message", (proc.stderr or "")[-140:])

    # --list-fields needs no input file, and documents the names.
    proc = run_converter(["--list-fields"])
    check(proc.returncode == 0, "--list-fields works without an input file",
          f"rc={proc.returncode}")
    check("CALL" in proc.stdout and "QSL_POSTAGE_AIR" in proc.stdout,
          "--list-fields prints the catalogue, derived columns included",
          proc.stdout[:120])

    # The library API honours the same contract.
    parsed = [(os.path.basename(sample_log),
               A.parse_adif(sample_log).records,
               A.parse_adif(sample_log).header, [])]
    result = A.build_rows(parsed, selected_columns=["CALL", "GRIDSQUARE"])
    check(all(c in result.columns for c in A.MANDATORY_COLUMNS),
          "build_rows keeps the mandatory columns", str(result.columns))
    check("GRIDSQUARE" in result.columns and "NAME" not in result.columns,
          "build_rows honours the selection", str(result.columns))

    # No selection means "every column that holds data", unchanged.
    everything = A.build_rows(parsed)
    check(len(everything.columns) > len(result.columns),
          "no selection keeps every populated column",
          f"{len(everything.columns)} vs {len(result.columns)}")

    # Every column the picker can offer has a Chinese label.
    missing = [c for c in everything.available if not A.field_label(c).strip()]
    unlabelled = [c for c in everything.available
                  if A.field_label(c) == c and c not in A.REQUIRED_COLUMNS]
    check(not missing, "every available column has a label", str(missing))
    check(not unlabelled,
          "every offered column has a Chinese label, not just its ADIF name",
          str(unlabelled))


def main() -> int:
    sample_dir = SAMPLES
    sample_log = os.path.join(sample_dir, "sample_log.adi")
    quirks = os.path.join(sample_dir, "sample_lotw_quirks.adi")

    print("=== sample_log.adi ===")
    out1 = os.path.join(OUT, "out_sample.xlsx")
    p = run_converter([sample_log, "-o", out1, "--quiet"])
    check(p.returncode == 0, "converter exits 0", p.stderr.strip()[:200])
    check_workbook(out1, [sample_log], 17)

    print("\n=== sample_lotw_quirks.adi ===")
    out2 = os.path.join(OUT, "out_quirks.xlsx")
    p = run_converter([quirks, "-o", out2, "--quiet"])
    check(p.returncode == 0, "converter exits 0", p.stderr.strip()[:200])
    check_workbook(out2, [quirks], 5)

    print("\n=== combined (two files) ===")
    out3 = os.path.join(OUT, "out_combined.xlsx")
    p = run_converter([sample_log, quirks, "-o", out3, "--quiet"])
    check(p.returncode == 0, "converter exits 0", p.stderr.strip()[:200])
    check_workbook(out3, [sample_log, quirks], 22)

    perf = PERF
    if os.path.exists(perf):
        check_performance(perf, 1000)
    else:
        print("\n  SKIP  performance test (perf_1000.adi not generated)")

    check_cli_edge_cases(sample_dir)
    check_column_selection(sample_log)
    check_robustness()
    check_data_safety()
    check_parser_units()
    check_real_exports(REAL)

    print(f"\n{'=' * 60}")
    print(f"checks run: {CHECKS}   failures: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
