# -*- coding: utf-8 -*-
r"""G6 - multi-file, folder, --recursive, output paths with spaces, relative paths.

Run: python verification\cases_paths.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, adif, dump, out_path, qso_rows, record, run, write_case  # noqa: E402

HDR = "<ADIF_VER:5>3.1.4<EOH>\n"
CASES = os.path.join(HERE, "cases")


def make(path, calls):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        for call, day in calls:
            fh.write(HDR + adif([("CALL", call), ("QSO_DATE", day),
                                 ("TIME_ON", "1200")]) + "\n")
    return path


def fresh(out):
    if os.path.exists(out):
        os.remove(out)
    return out


def g6a_two_files():
    a = make(os.path.join(CASES, "g6a_one.adi"), [("W1AW", "20240101"), ("K2DEF", "20240102"), ("N3XYZ", "20240103")])
    b = make(os.path.join(CASES, "g6a_two.adi"), [("DL1AA", "20240104"), ("DL2BB", "20240105")])
    out = fresh(out_path("g6a.xlsx"))
    p = run([a, b, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    calls = [r.get("CALL") for r in rows]
    ok = p.returncode == 0 and calls == ["W1AW", "K2DEF", "N3XYZ", "DL1AA", "DL2BB"]
    record("G6a two positional files merge to 3+2 = 5 rows, no record lost",
           "5 rows in order W1AW,K2DEF,N3XYZ,DL1AA,DL2BB",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd='python adif2xlsx.py verification\\cases\\g6a_one.adi verification\\cases\\g6a_two.adi -o verification\\out\\g6a.xlsx')


def g6b_folder():
    d = os.path.join(CASES, "g6b_folder")
    make(os.path.join(d, "f1.adi"), [("AA1AA", "20240101"), ("AA2AA", "20240102")])
    make(os.path.join(d, "f2.adif"), [("BB1BB", "20240103")])
    make(os.path.join(d, "ignore.txt"), [("CC1CC", "20240104")])
    out = fresh(out_path("g6b.xlsx"))
    p = run([d, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    calls = sorted(r.get("CALL") for r in rows)
    ok = p.returncode == 0 and calls == ["AA1AA", "AA2AA", "BB1BB"]
    record("G6b folder input picks up .adi/.adif only (txt ignored): 2+1 = 3 rows",
           "3 rows: AA1AA, AA2AA, BB1BB; ignore.txt not read",
           f"rc={p.returncode} rows={len(rows)} calls={calls}", ok,
           cmd='python adif2xlsx.py verification\\cases\\g6b_folder -o verification\\out\\g6b.xlsx')


def g6c_recursive():
    d = os.path.join(CASES, "g6c_rec")
    make(os.path.join(d, "top.adi"), [("TOP1", "20240101")])
    make(os.path.join(d, "nested", "deep.adi"), [("DEEP1", "20240102")])
    make(os.path.join(d, "nested", "deeper", "deepest.adi"), [("DEEP2", "20240103")])

    out_flat = fresh(out_path("g6c_flat.xlsx"))
    p_flat = run([d, "-o", out_flat])
    calls_flat = sorted(r.get("CALL") for r in (qso_rows(out_flat) if os.path.exists(out_flat) else []))

    out_rec = fresh(out_path("g6c_rec.xlsx"))
    p_rec = run([d, "-r", "-o", out_rec])
    calls_rec = sorted(r.get("CALL") for r in (qso_rows(out_rec) if os.path.exists(out_rec) else []))

    ok = (p_flat.returncode == 0 and calls_flat == ["TOP1"]
          and p_rec.returncode == 0 and calls_rec == ["DEEP1", "DEEP2", "TOP1"])
    record("G6c --recursive includes nested folders; without it only the top level",
           "flat = [TOP1]; recursive = [DEEP1, DEEP2, TOP1]",
           f"flat rc={p_flat.returncode} {calls_flat}; recursive rc={p_rec.returncode} {calls_rec}",
           ok, cmd='python adif2xlsx.py verification\\cases\\g6c_rec -r -o verification\\out\\g6c_rec.xlsx')


def g6d_output_with_spaces():
    a = make(os.path.join(CASES, "g6d.adi"), [("W1AW", "20240101")])
    out = fresh(out_path(os.path.join("out dir with space", "merged out.xlsx")))
    p = run([a, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    ok = p.returncode == 0 and len(rows) == 1
    record("G6d output path containing spaces (and a new sub-folder)",
           "rc=0, workbook written, 1 row",
           f"rc={p.returncode} exists={os.path.exists(out)} rows={len(rows)} stderr={p.stderr.strip()[:120]!r}",
           ok, cmd=f'python adif2xlsx.py verification\\cases\\g6d.adi -o "{out}"')


def g6e_relative_paths():
    a = make(os.path.join(CASES, "g6e.adi"), [("W1AW", "20240101"), ("K2DEF", "20240102")])
    rundir = os.path.join(HERE, "relrun")
    os.makedirs(rundir, exist_ok=True)
    rel_in = os.path.relpath(a, rundir)
    out_flat = os.path.join(rundir, "rel_flat.xlsx")
    if os.path.exists(out_flat):
        os.remove(out_flat)
    p1 = run([rel_in, "-o", "rel_flat.xlsx"], cwd=rundir)
    n1 = len(qso_rows(out_flat)) if os.path.exists(out_flat) else 0

    out_nested = os.path.join(rundir, "sub", "rel_nested.xlsx")
    if os.path.exists(out_nested):
        os.remove(out_nested)
    p2 = run([rel_in, "-o", os.path.join("sub", "rel_nested.xlsx")], cwd=rundir)
    n2 = len(qso_rows(out_nested)) if os.path.exists(out_nested) else 0

    ok = (p1.returncode == 0 and n1 == 2 and p2.returncode == 0 and n2 == 2
          and "rel_flat.xlsx" in p1.stdout.replace("\\", "/"))
    record("G6e relative input and relative output paths (cwd = verification\\relrun)",
           "rc=0; 2 rows; 'sub\\rel_nested.xlsx' created (missing dirs made)",
           f"rc1={p1.returncode} rows1={n1}; rc2={p2.returncode} rows2={n2} stderr={p2.stderr.strip()[:120]!r}",
           ok, cmd='cd verification\\relrun && python ..\\..\\adif2xlsx.py ..\\cases\\g6e.adi -o sub\\rel_nested.xlsx')


def g6f_duplicate_path_dedup():
    """The same file passed twice must not double-count."""
    a = make(os.path.join(CASES, "g6f.adi"), [("W1AW", "20240101")])
    out = fresh(out_path("g6f.xlsx"))
    p = run([a, a, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    ok = p.returncode == 0 and len(rows) == 1
    record("G6f the same file given twice on the command line",
           "1 row (input de-duplicated) or 2 rows (duplicated) - recorded, not judged",
           f"rc={p.returncode} rows={len(rows)}", ok,
           note="de-duplication by path is intentional in discover_inputs()",
           cmd='python adif2xlsx.py verification\\cases\\g6f.adi verification\\cases\\g6f.adi -o verification\\out\\g6f.xlsx')


def main():
    for fn in (g6a_two_files, g6b_folder, g6c_recursive, g6d_output_with_spaces,
               g6e_relative_paths, g6f_duplicate_path_dedup):
        fn()
    dump("g6_paths")


if __name__ == "__main__":
    main()
