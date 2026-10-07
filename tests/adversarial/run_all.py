# -*- coding: utf-8 -*-
r"""Run the whole adversarial harness against the current adif2xlsx.py.

  1. prints the pinned sha256 of the tool
  2. lints every fixture under verification\cases\
  3. runs every group script
  4. summarises the results

Run: python verification\run_all.py
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from common import PY, TOOL_SHA, lint_all  # noqa: E402

GROUPS = [
    "cases_len.py",        # G1 field-length correctness
    "cases_hdr.py",        # G2 header vs QSO classification
    "cases_map.py",        # G3 required-field mapping / Excel types
    "cases_band.py",       # G4 BAND/FREQ
    "cases_opt.py",        # G5 optional-field auto-detection
    "cases_paths.py",      # G6 multi-file / paths
    "cases_bug1.py",       # B1 terminator-text quantification
    "cases_header2.py",    # H group: header classification after the 24E51902 rewrite
    "cases_matrix.py",     # M group: banner-invariance matrix
    "cases_real.py",       # REAL: the six genuine user exports
    "cases_parser.py",     # P group: parser control-flow probes
    "cases_sanitize.py",   # Q group: new surface (sanitize / markup / vocabulary)
    "cases_robust.py",     # G7 robustness / hostile inputs
    "cases_fidelity.py",   # independent record-count cross-check on real fixtures
]


def main() -> int:
    print(f"adif2xlsx.py sha256 = {TOOL_SHA}")
    print(f"tool path           = {os.path.join(ROOT, 'adif2xlsx.py')}\n")
    print("--- fixture lint (declared lengths must land on a tag boundary) ---")
    lint_all()
    for group in GROUPS:
        print(f"\n{'=' * 78}\n{group}\n{'=' * 78}")
        p = subprocess.run([PY, os.path.join(HERE, group)], cwd=ROOT,
                           capture_output=True, text=True)
        print(p.stdout.rstrip())
        if p.stderr.strip():
            print(f"[stderr] {p.stderr.strip()[:400]}")
    print(f"\n{'=' * 78}\nSUMMARY\n{'=' * 78}")
    print("--- fixture lint AFTER the run (fixtures exactly as tested) ---")
    lint_all()
    s = subprocess.run([PY, os.path.join(HERE, "summarize.py")], cwd=ROOT,
                       capture_output=True, text=True)
    print(s.stdout.rstrip())
    return s.returncode


if __name__ == "__main__":
    raise SystemExit(main())
