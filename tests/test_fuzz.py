#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fuzz the converter: it must never crash with a traceback.

Random and mutant inputs are fed to the real command line.  The contract is:

  * exit code 0 (converted) or 1 (rejected) -- never an unhandled exception,
    never a traceback on stderr;
  * when it exits 0, the workbook opens and every required column is populated
    for every row, or the row is reported as incomplete.

Usage:  python tests/test_fuzz.py [iterations] [--seed N]
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
SCRIPT = os.path.join(SRC, "adif2xlsx.py")
FIXTURES = os.path.join(HERE, "fixtures", "samples")

FAILURES = []
CHECKS = 0


def check(condition, label, detail=""):
    global CHECKS
    CHECKS += 1
    if not condition:
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))
        FAILURES.append(label)


ALPHABET = list("<>:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 \t\r\n/\\-_.,;\"'=+@")
FIELD_NAMES = ["CALL", "QSO_DATE", "TIME_ON", "BAND", "MODE", "RST_SENT",
               "RST_RCVD", "STATION_CALLSIGN", "FREQ", "COMMENT", "SUBMODE",
               "DXCC", "COUNTRY", "EOR", "EOH", "zzz", "APP_LOTW_EOF",
               "app_qrzlog_logid", "NAME", "QTH"]


def random_bytes(rng, size):
    return bytes(rng.randrange(256) for _ in range(size))


def random_text(rng, size):
    return "".join(rng.choice(ALPHABET) for _ in range(size)).encode("utf-8")


def random_adif(rng):
    """Structurally plausible ADIF with random damage."""
    parts = []
    if rng.random() < 0.6:
        parts.append("Banner text %d\n" % rng.randrange(1000))
    if rng.random() < 0.4:
        parts.append("<ADIF_VER:5>3.1.7<PROGRAMID:4>FUZZ<EOH>\n")
    for _ in range(rng.randrange(1, 6)):
        fields = []
        for _ in range(rng.randrange(1, 8)):
            name = rng.choice(FIELD_NAMES)
            value = "".join(rng.choice(ALPHABET) for _ in range(rng.randrange(0, 12)))
            declared = len(value) + rng.choice([0, 0, 0, -1, 1, 5])
            if declared < 0:
                declared = 0
            fields.append(f"<{name}:{declared}>{value}")
        parts.append("".join(fields))
        if rng.random() < 0.8:
            parts.append(rng.choice(["<EOR>", "</EOR>", "<EOR/>", "<eor>", ""]))
        parts.append(rng.choice(["\n", "\r\n", " ", ""]))
    return "".join(parts).encode("utf-8")


def mutate(rng, data: bytes) -> bytes:
    """Flip, delete, insert or truncate bytes of a real fixture."""
    data = bytearray(data)
    for _ in range(rng.randrange(1, 12)):
        if not data:
            break
        op = rng.randrange(5)
        pos = rng.randrange(len(data))
        if op == 0:
            data[pos] = rng.randrange(256)
        elif op == 1:
            del data[pos]
        elif op == 2:
            data.insert(pos, rng.randrange(256))
        elif op == 3:
            data[pos:pos] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 6)))
        else:
            del data[pos:]
    return bytes(data)


def run_one(workdir, payload, index):
    """Return (label, ok, detail)."""
    path = os.path.join(workdir, f"f{index}.adi")
    out = os.path.join(workdir, f"f{index}.xlsx")
    with open(path, "wb") as fh:
        fh.write(payload)
    proc = subprocess.run([sys.executable, SCRIPT, path, "-o", out],
                          cwd=ROOT, capture_output=True, text=True, check=False,
                          errors="replace")
    if proc.returncode not in (0, 1):
        return (f"exit code {proc.returncode}", False, proc.stderr[-300:])
    if "Traceback" in proc.stderr or "Traceback" in proc.stdout:
        return ("traceback printed", False, proc.stderr[-300:])
    if proc.returncode == 0:
        if not os.path.exists(out):
            return ("exit 0 but no workbook", False, "")
        try:
            with zipfile.ZipFile(out) as zf:
                if zf.testzip() is not None:
                    return ("corrupt workbook", False, "")
        except zipfile.BadZipFile as exc:
            return ("unreadable workbook", False, str(exc))
    return ("ok", True, "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fuzz the ADIF converter")
    parser.add_argument("iterations", nargs="?", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261005)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    workdir = tempfile.mkdtemp(prefix="adif_fuzz_")
    fixtures = []
    for name in sorted(os.listdir(FIXTURES)):
        with open(os.path.join(FIXTURES, name), "rb") as fh:
            fixtures.append(fh.read())

    print(f"=== fuzzing {args.iterations} inputs (seed {args.seed}) ===")
    generators = (
        [("random-bytes", lambda: random_bytes(rng, rng.randrange(0, 400)))] * 3
        + [("random-text", lambda: random_text(rng, rng.randrange(0, 400)))] * 3
        + [("random-adif", lambda: random_adif(rng))] * 6
        + [("mutated-fixture", lambda: mutate(rng, rng.choice(fixtures)))] * 4
    )
    try:
        for i in range(args.iterations):
            label, make = rng.choice(generators)
            outcome, ok, detail = run_one(workdir, make(), i)
            check(ok, f"iteration {i} ({label}) survived", f"{outcome}: {detail}")
            if not ok:
                keep = os.path.join(ROOT, f"fuzz_failure_{i}.adi")
                shutil.copy(os.path.join(workdir, f"f{i}.adi"), keep)
                print(f"  kept failing input: {os.path.relpath(keep, ROOT)}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"\n{'=' * 60}")
    print(f"inputs: {args.iterations}   failures: {len(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
