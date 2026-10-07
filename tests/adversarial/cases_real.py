# -*- coding: utf-8 -*-
r"""REAL - the six genuine exports supplied by the user (C:\Users\Administrator\Desktop\ADI).

Read-only: the files were copied into verification\cases\real\ and hashed, so the
originals are never touched.  Record counts are derived independently from the
raw bytes (case-insensitive <eor> terminators, and LoTW's own APP_LOTW_NUMREC).

Run: python verification\cases_real.py
"""
from __future__ import annotations

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, dump, out_path, qso_rows, record, run  # noqa: E402

REAL = os.path.join(HERE, "cases", "real")
EXPECTED = {"lotw.adi": 199, "JTDX.ADI": 7, "QRZ.adi": 15, "n1MM.adi": 14,
            "CLUBLOG.adi": 11, "tqsl.adi": 3}
EOR_RE = re.compile(r"<\s*/?\s*eor\s*/?\s*>", re.IGNORECASE)
NUMREC_RE = re.compile(r"<app_lotw_numrec:(\d+)>([^<]*)", re.IGNORECASE)


def raw_facts(path: str) -> dict:
    text = open(path, "rb").read().decode("utf-8-sig", errors="replace")
    declared = [m.group(2).strip() for m in NUMREC_RE.finditer(text)]
    return {
        "eor": len(EOR_RE.findall(text)),
        "starts_with_lt": text[:1] == "<",
        "has_eoh": "<eoh" in text.lower(),
        "declared_numrec": declared,
    }


def main() -> None:
    files = {name: os.path.join(REAL, name) for name in EXPECTED
             if os.path.exists(os.path.join(REAL, name))}
    if len(files) != len(EXPECTED):
        print(f"!! missing real exports: {sorted(set(EXPECTED) - set(files))}")
        dump("real")
        return

    total_expected = 0
    for name, path in sorted(files.items()):
        facts = raw_facts(path)
        out = out_path("real_" + name + ".xlsx")
        if os.path.exists(out):
            os.remove(out)
        p = run([path, "-o", out])
        rows = qso_rows(out) if os.path.exists(out) else []
        blank = sum(1 for r in rows if not (r.get("CALL") or ""))
        cols = sorted(rows[0].keys()) if rows else []
        marker_leak = [c for c in cols if "HEADER" in c.upper()]
        declared = facts["declared_numrec"]
        ok = (p.returncode == 0 and len(rows) == facts["eor"] == EXPECTED[name]
              and blank == 0 and not marker_leak
              and (not declared or declared[0] == str(len(rows))))
        total_expected += len(rows)
        record(f"REAL {name}: rows == raw <eor> count == {EXPECTED[name]}",
               f"{EXPECTED[name]} QSOs, no blank CALL row, no header-marker column"
               + (f", matches APP_LOTW_NUMREC={declared}" if declared else ""),
               f"rc={p.returncode} rows={len(rows)} raw_eor={facts['eor']} blank_calls={blank} "
               f"marker_cols={marker_leak} starts_with_lt={facts['starts_with_lt']} "
               f"has_eoh={facts['has_eoh']} declared={declared}",
               ok,
               note="raw count from case-insensitive <eor>; LoTW self-declares its count",
               cmd=f"python adif2xlsx.py verification\\cases\\real\\{name} -o verification\\out\\real_{name}.xlsx")

        # diagnostic noise: the Lead's fix must not report fields the file omits
        noise = [l.strip() for l in (p.stdout + p.stderr).splitlines()
                 if "missing" in l.lower() or "NOTE" in l or "WARNING" in l]
        record(f"REAL {name}: no false 'missing fields' diagnostic",
               "no WARNING/NOTE about missing fields",
               f"diagnostics={noise[:3]}", not noise)

    # merged run: 249 rows, six distinct sources
    merged = out_path("real_merged.xlsx")
    if os.path.exists(merged):
        os.remove(merged)
    p = run(sorted(files.values()) + ["-o", merged, "--quiet"])
    rows = qso_rows(merged) if os.path.exists(merged) else []
    by_src = collections.Counter(r.get("SOURCE_FILE") for r in rows)
    ok = (p.returncode == 0 and len(rows) == sum(EXPECTED.values())
          and len(by_src) == len(EXPECTED)
          and all(by_src.get(n, 0) == EXPECTED[n] for n in EXPECTED))
    record(f"REAL merged: {sum(EXPECTED.values())} rows, per-file counts exact",
           f"249 rows; {EXPECTED}",
           f"rc={p.returncode} rows={len(rows)} by_source={dict(by_src)}", ok,
           cmd="python adif2xlsx.py verification\\cases\\real\\* -o verification\\out\\real_merged.xlsx")

    dump("real")


if __name__ == "__main__":
    main()
