# -*- coding: utf-8 -*-
r"""FIDELITY - independent cross-check on the real fixtures.

The parser's own count is not trusted: records are counted straight from the
raw bytes with a regex (<EOR> terminators) and callsigns are extracted with an
independent reader, then compared with what landed in the workbook.

Run: python verification\cases_fidelity.py
"""
from __future__ import annotations

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, ROOT, dump, out_path, qso_rows, record, run  # noqa: E402

FIXTURES = ["samples/sample_log.adi", "samples/sample_lotw_quirks.adi", "perf_1000.adi"]
TAG = re.compile(r"<\s*([A-Za-z_][A-Za-z0-9_\-\.]*)\s*:\s*(\d+)\s*(?::\s*[A-Za-z]\s*)?>")
EOR = re.compile(r"<\s*/?\s*EOR\s*>", re.IGNORECASE)


def read_text(path: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    return raw.decode("utf-8-sig")


def raw_records(path: str):
    """[(fields dict)] split on <EOR>, read purely by declared length."""
    text = read_text(path)
    recs = []
    cur = {}
    pos = 0
    while pos < len(text):
        m = TAG.search(text, pos)
        eor = EOR.search(text, pos)
        if m and (not eor or m.start() < eor.start()):
            val = text[m.end():m.end() + int(m.group(2))]
            cur[m.group(1).upper()] = val
            pos = m.end() + int(m.group(2))
        elif eor:
            if cur:
                recs.append(cur)
            cur = {}
            pos = eor.end()
        else:
            break
    if cur:
        recs.append(cur)
    return recs


def main() -> None:
    per_file = {}
    for rel in FIXTURES:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        recs = raw_records(path)
        per_file[rel] = recs
        single = os.path.join(HERE, "out", "fid_" + os.path.basename(path) + ".xlsx")
        if os.path.exists(single):
            os.remove(single)
        p = run([path, "-o", single, "--quiet"])
        rows = qso_rows(single) if os.path.exists(single) else []
        raw_calls = collections.Counter(r.get("CALL", "").upper() for r in recs if r.get("CALL"))
        wb_calls = collections.Counter((r.get("CALL") or "") for r in rows)
        n_eor = len(EOR.findall(read_text(path)))
        ok = (p.returncode == 0 and len(rows) == len(recs) and raw_calls == wb_calls)
        record(f"FID {os.path.basename(rel)}: {len(recs)} raw records -> workbook rows",
               f"rows == raw record count == {len(recs)}; callsign multiset identical "
               f"(raw <EOR> terminators: {n_eor})",
               f"rc={p.returncode} rows={len(rows)} raw={len(recs)} eor={n_eor} "
               f"calls_diff={list((raw_calls - wb_calls).elements())[:5]}"
               f"/{list((wb_calls - raw_calls).elements())[:5]}",
               ok, note="raw counts read with an independent regex reader",
               cmd=f"python adif2xlsx.py {rel} -o verification\\out\\fid_{os.path.basename(path)}.xlsx")

    # merged run: sum of the three, and per-source counts
    merged = out_path("fid_merged.xlsx")
    if os.path.exists(merged):
        os.remove(merged)
    p = run([os.path.join(ROOT, f.replace("/", os.sep)) for f in FIXTURES] + ["-o", merged, "--quiet"])
    rows = qso_rows(merged) if os.path.exists(merged) else []
    expected = sum(len(v) for v in per_file.values())
    by_src = collections.Counter(r.get("SOURCE_FILE") for r in rows)
    ok = (p.returncode == 0 and len(rows) == expected
          and all(by_src.get(os.path.basename(f), 0) == len(per_file[f]) for f in FIXTURES))
    record("FID merged 3 real files: rows == sum of parts, SOURCE_FILE counts match",
           f"{expected} rows; per-file counts "
           f"{ {os.path.basename(f): len(per_file[f]) for f in FIXTURES} }",
           f"rc={p.returncode} rows={len(rows)} by_source={dict(by_src)}",
           ok, cmd="python adif2xlsx.py samples\\sample_log.adi samples\\sample_lotw_quirks.adi perf_1000.adi -o verification\\out\\fid_merged.xlsx")

    # all callsigns from all inputs must be present in the merge (no record lost)
    all_raw = collections.Counter()
    for recs in per_file.values():
        all_raw.update(r.get("CALL", "").upper() for r in recs if r.get("CALL"))
    wb = collections.Counter((r.get("CALL") or "") for r in rows)
    ok = all_raw == wb
    record("FID merged workbook: every raw CALL present exactly the right number of times",
           f"{sum(all_raw.values())} callsigns, identical multiset",
           f"missing={list((all_raw - wb).elements())[:8]} extra={list((wb - all_raw).elements())[:8]}",
           ok, cmd="(same merged run)")

    dump("fidelity")


if __name__ == "__main__":
    main()
