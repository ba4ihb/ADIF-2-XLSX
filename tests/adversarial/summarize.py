# -*- coding: utf-8 -*-
r"""Aggregate every results_*.json written by the group scripts.

Fails loudly if any group was run against a different revision of the tool.

Run: python verification\summarize.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TOOL = os.path.join(os.path.dirname(HERE), "adif2xlsx.py")


def main() -> int:
    import hashlib
    with open(TOOL, "rb") as fh:
        current = hashlib.sha256(fh.read()).hexdigest()
    print(f"adif2xlsx.py sha256 = {current}\n")

    rows = []
    stale = []
    for path in sorted(glob.glob(os.path.join(HERE, "results_*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        sha = data.get("tool_sha256", "?")
        if sha != current:
            stale.append((os.path.basename(path), sha))
        for r in data["results"]:
            rows.append((data["tag"], r))

    n_pass = sum(1 for _t, r in rows if r["verdict"] == "PASS")
    print(f"{'tag':<16} {'verdict':<8} case")
    print("-" * 100)
    for tag, r in rows:
        if r["verdict"] != "PASS":
            print(f"{tag:<16} {r['verdict']:<8} {r['case']}")
    print("-" * 100)
    fails = [(t, r) for t, r in rows if r["verdict"] != "PASS"]
    print(f"TOTAL {n_pass}/{len(rows)} passed, {len(fails)} failed")
    if stale:
        print("!! STALE RESULTS (different tool revision):")
        for name, sha in stale:
            print(f"   {name}: {sha}")
        return 2
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
