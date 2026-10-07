#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run every test suite and summarise the result.

    python tests/run_all_tests.py            # unit + end-to-end
    python tests/run_all_tests.py --with-exe # also check dist\\adif2xlsx.exe

Each suite runs in its own process so a crash in one cannot hide the others.
The exit status is 0 only when every suite passes.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SUITES = [
    ("ADIF enumerations (unit)", os.path.join(HERE, "test_enumerations.py")),
    ("DXCC lookup (unit)", os.path.join(HERE, "test_dxcc.py")),
    ("QSL postage (unit)", os.path.join(HERE, "test_postage.py")),
    ("converter (end-to-end)", os.path.join(HERE, "test_acceptance.py")),
    # Parity is a project requirement, not an optional extra: the web page and
    # the desktop app must stay functionally identical, so this runs by default
    # rather than behind a flag.
    ("front-end parity", os.path.join(HERE, "test_frontend_parity.py")),
    # The browser edition must stay the same converter, not become a second one.
    ("browser edition", os.path.join(HERE, "test_browser_edition.py")),
]
# The UI suite drives real windows, so it only runs when asked for.
GUI_SUITE = ("desktop UI", os.path.join(HERE, "test_gui.py"))
# The web suite starts a loopback service and talks to it over HTTP.
WEB_SUITE = ("web interface", os.path.join(HERE, "test_web.py"))
EXE_SUITE = ("packaged executable", os.path.join(HERE, "test_exe.py"))


def run_suite(label: str, path: str) -> tuple:
    print(f"\n{'=' * 70}\n{label}  --  {os.path.relpath(path, ROOT)}\n{'=' * 70}")
    start = time.perf_counter()
    proc = subprocess.run([sys.executable, path], cwd=ROOT, check=False)
    elapsed = time.perf_counter() - start
    status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
    print(f"\n-> {label}: {status} in {elapsed:.1f}s")
    return label, proc.returncode, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all adif2xlsx tests")
    parser.add_argument("--with-exe", action="store_true",
                        help="also test the built executables in dist\\")
    parser.add_argument("--with-gui", action="store_true",
                        help="also run the desktop UI suite (opens real windows)")
    parser.add_argument("--with-web", action="store_true",
                        help="also run the web interface suite")
    parser.add_argument("--all", action="store_true",
                        help="everything: --with-exe --with-gui --with-web")
    args = parser.parse_args()
    with_exe = args.with_exe or args.all
    with_gui = args.with_gui or args.all
    with_web = args.with_web or args.all

    suites = list(SUITES)
    if with_gui:
        suites.append(GUI_SUITE)
    if with_web:
        suites.append(WEB_SUITE)
    if with_exe:
        suites.append(EXE_SUITE)
        if with_gui:
            print("note: the UI suite covers dist\\adif2xlsx-ui.exe when run "
                  "with --with-gui; see tests\\test_gui.py --with-exe")
    else:
        exe = os.path.join(ROOT, "dist", "adif2xlsx.exe")
        if os.path.isfile(exe):
            print("note: dist\\adif2xlsx.exe exists; add --with-exe to test it")

    results = [run_suite(label, path) for label, path in suites]

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    failed = 0
    for label, code, elapsed in results:
        mark = "PASS" if code == 0 else "FAIL"
        if code != 0:
            failed += 1
        print(f"  [{mark}] {label:28} {elapsed:6.1f}s")
    total = sum(r[2] for r in results)
    print(f"\n  {len(results) - failed}/{len(results)} suites passed in {total:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
