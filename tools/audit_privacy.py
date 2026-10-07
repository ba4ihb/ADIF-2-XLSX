"""Proper privacy audit: field-scoped checks plus pseudonym verification.

The first pass flagged 3375 "postcodes", all of which were HHMMSS times: the rule
was matching the wrong thing.  This checks per ADIF FIELD instead, and separately
proves the fixture callsigns are synthetic by confirming none of them appears in
the original exports they were derived from.
"""

import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

ROOT = r"C:\Users\Administrator\Desktop\adif2xlsx"
ORIGINAL = r"C:\Users\Administrator\Desktop\ADI"
FIELD_RE = re.compile(r"<([A-Za-z_][\w.\-]*)\s*:\s*(\d+)(?::[A-Za-z])?>"
                      r"([^<]*)", re.I)

OWNER_CALLS = ["BA4IHB", "BA4JBN", "BG4LNW", "BA4IFR"]
PERSONAL_TEXT = ["\u6cf0\u5b89\u5e02", "\u5c71\u4e1c\u7701", "\u80a5\u57ce\u5e02",
                 "\u6cf0\u5b89", "\u5c71\u4e1c", "\u80a5\u57ce",
                 "\u90c1\u822a"]
#: Fields whose value is a person's own data, not the contact's log data.
PERSONAL_FIELDS = {"NAME", "MY_NAME", "QTH", "MY_CITY", "CITY", "EMAIL",
                   "EMAIL2", "ADDRESS", "ADDRESS1", "MY_STREET", "STREET",
                   "POSTALCODE", "MY_POSTALCODE", "ZIP", "MY_ZIP", "COMMENT",
                   "NOTES", "MY_ANTENNA", "MY_RIG"}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
CALLSIGNISH_RE = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z]{1,4}$", re.I)


def fields(text: str):
    for match in FIELD_RE.finditer(text):
        yield match.group(1).upper(), match.group(3)


def walk_adi():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {".git", "dist", "build",
                                                "__pycache__"}]
        for name in files:
            if os.path.splitext(name)[1].lower() in (".adi", ".adif"):
                yield os.path.join(base, name)


print("=== 1. owner callsigns / personal text anywhere ===")
leaks = []
for path in walk_adi():
    rel = os.path.relpath(path, ROOT)
    text = open(path, encoding="utf-8", errors="replace").read()
    for needle in OWNER_CALLS + PERSONAL_TEXT:
        if needle in text:
            leaks.append((rel, needle))
if leaks:
    for rel, needle in leaks:
        print(f"  LEAK {rel}: {needle}")
else:
    print("  clean: no owner callsign and no personal text")

print()
print("=== 2. personal FIELDS whose value is not the neutral placeholder ===")
suspicious = []
for path in walk_adi():
    rel = os.path.relpath(path, ROOT)
    text = open(path, encoding="utf-8", errors="replace").read()
    for field, value in fields(text):
        if field not in PERSONAL_FIELDS or not value.strip():
            continue
        if EMAIL_RE.search(value):
            suspicious.append((rel, field, value))
        elif field.startswith("MY_") or field in ("NAME", "QTH", "CITY",
                                                  "ADDRESS", "POSTALCODE",
                                                  "ZIP", "COMMENT", "NOTES"):
            # Any non-placeholder value is worth a human look.
            if value not in ("Test Op", "Test City", "1 Test Street", "00000",
                             "test@example.invalid", "AA00aa"):
                suspicious.append((rel, field, value[:50]))
if suspicious:
    for rel, field, value in suspicious[:30]:
        print(f"  CHECK {rel:44} {field:16} {value!r}")
    print(f"  total: {len(suspicious)}")
else:
    print("  clean: every personal field holds a neutral placeholder")

print()
print("=== 3. are the fixture callsigns synthetic? ===")
orig_calls = set()
if os.path.isdir(ORIGINAL):
    for name in os.listdir(ORIGINAL):
        text = open(os.path.join(ORIGINAL, name), encoding="utf-8",
                    errors="replace").read()
        for field, value in fields(text):
            if field in ("CALL", "STATION_CALLSIGN", "OPERATOR", "MY_CALL",
                         "OWNER_CALLSIGN"):
                orig_calls.add(value.strip().upper())
    print(f"  callsigns in the original exports: {len(orig_calls)}")
else:
    print(f"  originals not available at {ORIGINAL}")

fixture_calls = set()
adi_dir = os.path.join(ROOT, "tests", "fixtures", "adi")
for name in os.listdir(adi_dir):
    text = open(os.path.join(adi_dir, name), encoding="utf-8",
                errors="replace").read()
    for field, value in fields(text):
        if field in ("CALL", "STATION_CALLSIGN", "OPERATOR", "MY_CALL",
                     "OWNER_CALLSIGN"):
            fixture_calls.add(value.strip().upper())

print(f"  callsigns in the shipped fixtures : {len(fixture_calls)}")
overlap = sorted(fixture_calls & orig_calls)
print(f"  OVERLAP with the originals        : {len(overlap)} {overlap[:10]}")
if orig_calls:
    print("  => fixtures are synthetic" if not overlap
          else "  => *** REAL CALLSIGNS PRESENT ***")

print()
print("=== 4. every distinct callsign in the shipped fixtures ===")
for name in sorted(os.listdir(adi_dir)):
    text = open(os.path.join(adi_dir, name), encoding="utf-8",
                errors="replace").read()
    calls = sorted({v.strip() for f, v in fields(text)
                    if f in ("CALL", "STATION_CALLSIGN", "OPERATOR")})
    odd = [c for c in calls if not CALLSIGNISH_RE.match(c)]
    print(f"  {name:14} {len(calls):3} distinct; odd-shaped: {odd[:5]}")
