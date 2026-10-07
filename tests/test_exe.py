"""Verify the built executable matches the Python implementation exactly."""
import hashlib
import os
import subprocess
import sys
import tempfile

# Derived from this file's location: a hardcoded absolute path made the
# suite pass only on the machine it was written on.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXE = os.path.join(ROOT, "dist", "adif2xlsx.exe")
PY = sys.executable
SCRIPT = os.path.join(ROOT, "src", "adif2xlsx.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "adi")

TMP = tempfile.mkdtemp(prefix="execheck_")
ok = True


def run(cmd, args, cwd=ROOT):
    return subprocess.run(cmd + args, cwd=cwd, capture_output=True, text=True)


def sheet_digest(path):
    """Hash every cell value in the workbook, independent of file metadata."""
    import openpyxl
    wb = openpyxl.load_workbook(path)
    h = hashlib.sha256()
    for name in sorted(wb.sheetnames):
        ws = wb[name]
        h.update(name.encode())
        for row in ws.iter_rows():
            for cell in row:
                h.update(repr(cell.value).encode("utf-8", "replace"))
                h.update(str(cell.number_format).encode())
    return h.hexdigest()


print("=== 1. exe converts the six real fixtures ===")
out_exe = os.path.join(TMP, "exe.xlsx")
r = run([EXE], [FIX, "-o", out_exe])
print(f"  exit={r.returncode}")
print("  stdout:", " | ".join(l.strip() for l in r.stdout.splitlines() if l.strip())[:200])
if r.stderr.strip():
    print("  stderr:", r.stderr.strip()[:200])
ok &= r.returncode == 0 and os.path.exists(out_exe)

print("\n=== 2. python converts the same input ===")
out_py = os.path.join(TMP, "py.xlsx")
r2 = run([PY, SCRIPT], [FIX, "-o", out_py])
print(f"  exit={r2.returncode}")
ok &= r2.returncode == 0 and os.path.exists(out_py)

print("\n=== 3. same data, cell for cell ===")
if os.path.exists(out_exe) and os.path.exists(out_py):
    de, dp = sheet_digest(out_exe), sheet_digest(out_py)
    print(f"  exe digest: {de[:32]}")
    print(f"  py  digest: {dp[:32]}")
    same = de == dp
    print(f"  identical: {same}")
    ok &= same
    import openpyxl
    for p, label in ((out_exe, "exe"), (out_py, "py")):
        ws = openpyxl.load_workbook(p)["QSOs"]
        print(f"  {label}: {ws.max_row - 1} rows x {ws.max_column} cols")

print("\n=== 4. exe robustness parity ===")
cases = [
    ("missing input", [os.path.join(TMP, "nope.adi"), "-o", os.path.join(TMP, "a.xlsx")]),
    ("empty file", None),
]
empty = os.path.join(TMP, "empty.adi")
open(empty, "w").close()
cases[1] = ("empty file", [empty, "-o", os.path.join(TMP, "b.xlsx")])
for label, args in cases:
    a = run([EXE], args)
    b = run([PY, SCRIPT], args)
    same = a.returncode == b.returncode
    print(f"  {label}: exe rc={a.returncode} py rc={b.returncode} {'OK' if same else 'DIFFER'}")
    ok &= same

print("\n=== 5. exe handles a Windows path with spaces ===")
spaced = os.path.join(TMP, "My Logs 2024")
os.makedirs(spaced, exist_ok=True)
import shutil
shutil.copy(os.path.join(FIX, "JTDX.ADI"), spaced)
out3 = os.path.join(spaced, "out report.xlsx")
r3 = run([EXE], [spaced, "-o", out3])
print(f"  exit={r3.returncode} exists={os.path.exists(out3)}")
ok &= r3.returncode == 0 and os.path.exists(out3)

print("\n=== 6. no Python needed (bundled runtime) ===")
r4 = run([EXE], ["--version"])
print(f"  --version output: {r4.stdout.strip()!r}")
ok &= "adif2xlsx" in r4.stdout

print("\nRESULT:", "PASS" if ok else "FAIL")
print("temp:", TMP)
