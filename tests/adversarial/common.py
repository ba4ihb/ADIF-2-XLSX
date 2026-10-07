# -*- coding: utf-8 -*-
r"""Shared helpers for the adversarial verification of adif2xlsx.py.

Everything this module touches lives under verification\ .
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile

import openpyxl
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
TOOL = os.path.join(ROOT, "adif2xlsx.py")
CASES = os.path.join(HERE, "cases")
OUT = os.path.join(HERE, "out")
RESULTS: list[dict] = []


def tool_sha(path: str = TOOL) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


TOOL_SHA = tool_sha()


def ensure_dirs() -> None:
    for d in (CASES, OUT):
        os.makedirs(d, exist_ok=True)


def case_path(name: str) -> str:
    ensure_dirs()
    return os.path.join(CASES, name)


def write_case(name: str, data, binary: bool = False) -> str:
    """Write a fixture file under verification\\cases\\ and return its path."""
    path = case_path(name)
    if binary or isinstance(data, bytes):
        with open(path, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    else:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(data)
    return path


def out_path(name: str) -> str:
    ensure_dirs()
    return os.path.join(OUT, name)


def run(args, cwd: str = ROOT, timeout: int = 120):
    """Run the converter. Returns CompletedProcess (text captured)."""
    return subprocess.run(
        [PY, TOOL] + [str(a) for a in args],
        cwd=cwd, capture_output=True, text=True, timeout=timeout,
    )


def run_py(script: str, cwd: str = ROOT, timeout: int = 300):
    return subprocess.run(
        [PY, script], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def load(path: str):
    return openpyxl.load_workbook(path)


def header_map(ws) -> dict:
    return {
        str(c.value).strip(): c.column
        for c in ws[1]
        if c.value is not None
    }


def qso_rows(xlsx_path: str, sheet: str = "QSOs") -> list[dict]:
    """Every QSO row as {column_name: value}. Raises if the workbook is absent."""
    wb = load(xlsx_path)
    ws = wb[sheet]
    hdr = header_map(ws)
    rows = []
    for r in range(2, ws.max_row + 1):
        rows.append({k: ws.cell(row=r, column=c).value for k, c in hdr.items()})
    return rows


def qso_count(xlsx_path: str) -> int:
    """Row count as reported by openpyxl on the QSOs sheet."""
    return len(qso_rows(xlsx_path))


def record(name, expected, observed, ok, note="", cmd="") -> None:
    RESULTS.append({
        "case": name,
        "expected": expected,
        "observed": observed,
        "verdict": "PASS" if ok else "FAIL",
        "note": note,
        "cmd": cmd,
        "tool_sha256": TOOL_SHA,
    })
    flag = "PASS" if ok else "FAIL"
    line = f"  [{flag}] {name}"
    if not ok:
        line += f"\n         expected: {expected}\n         observed: {observed}"
        if note:
            line += f"\n         note    : {note}"
    print(line, flush=True)


def dump(tag: str) -> None:
    path = os.path.join(HERE, f"results_{tag}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"tool_sha256": TOOL_SHA, "tag": tag, "results": RESULTS},
                  fh, indent=2, default=str)
    n_pass = sum(1 for r in RESULTS if r["verdict"] == "PASS")
    print(f"\n[{tag}] tool_sha256={TOOL_SHA}", flush=True)
    print(f"[{tag}] {n_pass}/{len(RESULTS)} checks passed -> {path}", flush=True)


def adif(fields, eor=True):
    """Build a record string from [(name, value, datatype)] with real lengths."""
    out = []
    for item in fields:
        name, value = item[0], item[1]
        dtype = item[2] if len(item) > 2 else None
        if dtype:
            out.append(f"<{name}:{len(value)}:{dtype}>{value}")
        else:
            out.append(f"<{name}:{len(value)}>{value}")
    if eor:
        out.append("<EOR>")
    return "".join(out)


# --- raw-XML inspection (independent of openpyxl's read-back conversions) ----
_CELL_RE = re.compile(r'<c\s+r="([A-Z]+\d+)"(.*?)(?:/>|</c>)', re.S)


def raw_cells(path: str, sheet_index: int = 1) -> dict:
    """{cell_ref: (t_attribute, raw_text)} straight from the sheet XML.

    Handles numeric <v> cells, sharedStrings indices and inline strings
    (openpyxl writes text as t="inlineStr" with <is><t>...</t></is> here).
    """
    with zipfile.ZipFile(path) as z:
        xml = z.read(f"xl/worksheets/sheet{sheet_index}.xml").decode("utf-8")
    out = {}
    for m in _CELL_RE.finditer(xml):
        ref, body = m.group(1), m.group(2)
        inline = re.search(r"<is>.*?<t[^>]*>(.*?)</t>", body, re.S)
        if inline is not None:
            out[ref] = ("inlineStr", inline.group(1))
            continue
        t = re.search(r't="([^"]+)"', body)
        v = re.search(r"<v>([^<]*)</v>", body)
        out[ref] = (t.group(1) if t else "n", v.group(1) if v else None)
    return out


def raw_sheet_xml(path: str, sheet_index: int = 1) -> str:
    """The raw worksheet XML (for literal-text searches)."""
    with zipfile.ZipFile(path) as z:
        return z.read(f"xl/worksheets/sheet{sheet_index}.xml").decode("utf-8")


def serial_of(path: str, column_name: str, row: int, sheet_index: int = 1):
    """Raw stored number for the cell of `column_name` at `row` (1-based)."""
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[sheet_index - 1]
    col = header_map(ws)[column_name]
    ref = f"{get_column_letter(col)}{row}"
    return raw_cells(path, sheet_index).get(ref)


def shared_strings(path: str) -> list:
    """The workbook's sharedStrings table (proves what is really stored)."""
    with zipfile.ZipFile(path) as z:
        if "xl/sharedStrings.xml" not in z.namelist():
            return []
        xml = z.read("xl/sharedStrings.xml").decode("utf-8")
    return re.findall(r"<t[^>]*>(.*?)</t>", xml, re.S)


def stored_text(path: str, column_name: str, row: int, sheet_index: int = 1) -> str:
    """The literal text stored in a cell, read from the sheet XML (no openpyxl)."""
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[sheet_index - 1]
    col = header_map(ws)[column_name]
    t, v = raw_cells(path, sheet_index).get(f"{get_column_letter(col)}{row}", ("n", None))
    if t == "inlineStr":
        return v
    if t == "s" and v is not None:
        ss = shared_strings(path)
        try:
            return ss[int(v)]
        except (ValueError, IndexError):
            return f"<bad sharedStrings index {v}>"
    return v


def as_date(value):
    """The .date() of a date/datetime cell, else None."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


_TAG_RE = re.compile(r"<\s*([A-Za-z_][A-Za-z0-9_\-\.]*)\s*:\s*(\d+)\s*(?::\s*[A-Za-z]\s*)?>")

# Fixtures that are malformed ON PURPOSE (the case is about the malformed length).
LINT_ALLOWLIST = {
    "g1h_overdeclare_swallow.adi": "case G1h: declared length deliberately too long",
    "g1d2_utf8_bytelen.adi": "case G1d2: length deliberately declared in BYTES",
}


def lint_fixture(path: str) -> list:
    """Report declared lengths that do not end on a tag boundary.

    A declared length must consume exactly its value, so the text up to the next
    '<' must be empty or pure whitespace. This catches hand-written fixtures
    whose declared length is off by one - the parser would otherwise silently
    swallow the next tag and the test would assert on garbage.
    """
    problems = []
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return problems
    for m in _TAG_RE.finditer(text):
        end = m.end() + int(m.group(2))
        value = text[m.end():end]
        gap = text[end:end + 40]
        if gap and not gap[0].isspace() and gap[0] != "<":
            problems.append((m.group(1), int(m.group(2)), value, gap[:12]))
    return problems


def lint_all(verbose: bool = True) -> int:
    """Lint every fixture under verification\\cases\\ ; returns issue count."""
    bad = 0
    for name in sorted(os.listdir(CASES)):
        path = os.path.join(CASES, name)
        if not os.path.isfile(path):
            continue
        if name in LINT_ALLOWLIST:
            continue
        for field, declared, value, after in lint_fixture(path):
            bad += 1
            if verbose:
                print(f"  LINT {name}: <{field}:{declared}> consumed {value!r} "
                      f"and lands on {after!r}")
    if verbose:
        print(f"  fixture lint: {bad} problem(s)")
    return bad


