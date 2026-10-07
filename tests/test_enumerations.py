#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for the parser's ADIF enumerations.

These guard three things that are easy to break by hand and expensive to get
wrong, because a wrong value silently produces a wrong column rather than an
error:

  * ``SUBMODE_TO_MODE`` covers the whole ADIF 3.1.7 Submode enumeration and
    maps each submode to its true parent mode;
  * every value in the MODE enumeration is recognised as a mode (so a log that
    writes a mode name into SUBMODE still converts);
  * the BAND table matches the published band enumeration.

Run directly (``python tests/test_enumerations.py``) or through pytest.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import adif2xlsx as A  # noqa: E402

FAILURES = []
CHECKS = 0


def check(condition, label, detail=""):
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))
        FAILURES.append(label)


# --- ADIF 3.1.7 Submode enumeration -> parent MODE --------------------------
SUBMODES = {
    "PSK": """8PSK125 8PSK125F 8PSK125FL 8PSK250 8PSK250F 8PSK250FL 8PSK500
        8PSK500F 8PSK1000 8PSK1000F 8PSK1200F FSK31 PSK10 PSK31 PSK63 PSK63F
        PSK63RC4 PSK63RC5 PSK63RC10 PSK63RC20 PSK63RC32 PSK125 PSK125RC4
        PSK125RC5 PSK125RC10 PSK125RC12 PSK125RC16 PSK250 PSK250RC2 PSK250RC3
        PSK250RC5 PSK250RC6 PSK250RC7 PSK500 PSK500RC2 PSK500RC3 PSK500RC4
        PSK800RC2 PSK1000 PSK1000RC2 PSKAM10 PSKAM31 PSKAM50 PSKFEC31 QPSK31
        QPSK63 QPSK125 QPSK250 QPSK500 SIM31""",
    "MFSK": """FSQCALL FST4 FST4W FT2 FT4 JS8 JTMS MFSK4 MFSK8 MFSK11 MFSK16
        MFSK22 MFSK31 MFSK32 MFSK64 MFSK64L MFSK128 MFSK128L Q65""",
    "DOMINO": "DOM-M DOM4 DOM5 DOM8 DOM11 DOM16 DOM22 DOM44 DOM88 DOMINOEX DOMINOF",
    "HELL": "FMHELL FSKH105 FSKH245 FSKHELL HELL80 HELLX5 HELLX9 HFSK PSKHELL SLOWHELL",
    "THOR": """THOR-M THOR4 THOR5 THOR8 THOR11 THOR16 THOR22 THOR25X4
        THOR50X1 THOR50X2 THOR100""",
    "THRB": "THRBX THRBX1 THRBX2 THRBX4 THROB1 THROB2 THROB4",
    "JT4": "JT4A JT4B JT4C JT4D JT4E JT4F JT4G",
    "JT9": """JT9-1 JT9-2 JT9-5 JT9-10 JT9-30 JT9A JT9B JT9C JT9D JT9E
        JT9E-FAST JT9F JT9F-FAST JT9G JT9G-FAST JT9H JT9H-FAST""",
    "JT65": "JT65A JT65B JT65B2 JT65C JT65C2",
    "OLIVIA": """OLIVIA-4/125 OLIVIA-4/250 OLIVIA-8/250 OLIVIA-8/500
        OLIVIA-16/500 OLIVIA-16/1000 OLIVIA-32/1000""",
    "QRA64": "QRA64A QRA64B QRA64C QRA64D QRA64E",
    "DIGITALVOICE": "C4FM DMR DSTAR FREEDV M17",
    "DYNAMIC": "FREEDATA VARA-HF VARA-SATELLITE VARA-FM-1200 VARA-FM-9600",
    "PAC": "PAC2 PAC3 PAC4",
    "ROS": "ROS-EME ROS-HF ROS-MF",
    "FSK": "SCAMP_FAST SCAMP_SLOW SCAMP_VSLOW",
    "TOR": "AMTORFEC GTOR NAVTEX SITORB",
    "ISCAT": "ISCAT-A ISCAT-B",
    "CHIP": "CHIP64 CHIP128",
    "OPERA": "OPERA-BEACON OPERA-QSO",
    "MTONE": "SCAMP_OO SCAMP_OO_SLW",
    "OFDM": "RIBBIT_PIX RIBBIT_SMS",
    "SSB": "LSB USB",
    "CW": "PCW",
    "PAX": "PAX2",
    "RTTY": "ASCI",
}
# hyphen placeholders used above so the table stays readable in source
SPACE_FOR_HYPHEN = {
    "JT9E-FAST": "JT9E FAST", "JT9F-FAST": "JT9F FAST",
    "JT9G-FAST": "JT9G FAST", "JT9H-FAST": "JT9H FAST",
    "OLIVIA-4/125": "OLIVIA 4/125", "OLIVIA-4/250": "OLIVIA 4/250",
    "OLIVIA-8/250": "OLIVIA 8/250", "OLIVIA-8/500": "OLIVIA 8/500",
    "OLIVIA-16/500": "OLIVIA 16/500", "OLIVIA-16/1000": "OLIVIA 16/1000",
    "OLIVIA-32/1000": "OLIVIA 32/1000",
    "VARA-HF": "VARA HF", "VARA-SATELLITE": "VARA SATELLITE",
    "VARA-FM-1200": "VARA FM 1200", "VARA-FM-9600": "VARA FM 9600",
}

# ADIF 3.1.7 MODE enumeration (49 values).
MODES = """AM ARDOP ATV CHIP CLO CONTESTI CW DIGITALVOICE DOMINO DYNAMIC FAX FM
    FSK FSK441 FT8 HELL ISCAT JT4 JT6M JT9 JT44 JT65 MFSK MSK144 MT63 MTONE
    OFDM OLIVIA OPERA PAC PAX PKT PSK PSK2K Q15 QRA64 ROS RTTY RTTYM SSB SSTV
    T10 THOR THRB TOR V4 VOI WINMOR WSPR""".split()

# ADIF 3.1.7 BAND enumeration -> (lower MHz, upper MHz).
BANDS = {
    "2190M": (0.1357, 0.1378), "630M": (0.472, 0.479), "560M": (0.501, 0.504),
    "160M": (1.8, 2.0), "80M": (3.5, 4.0), "60M": (5.06, 5.45),
    "40M": (7.0, 7.3), "30M": (10.1, 10.15), "20M": (14.0, 14.35),
    "17M": (18.068, 18.168), "15M": (21.0, 21.45), "12M": (24.89, 24.99),
    "10M": (28.0, 29.7), "8M": (40.0, 45.0), "6M": (50.0, 54.0),
    "5M": (54.0, 69.9), "4M": (70.0, 71.0), "2M": (144.0, 148.0),
    "1.25M": (222.0, 225.0), "70CM": (420.0, 450.0), "33CM": (902.0, 928.0),
    "23CM": (1240.0, 1300.0), "13CM": (2300.0, 2450.0), "9CM": (3300.0, 3500.0),
    "6CM": (5650.0, 5925.0), "3CM": (10000.0, 10500.0), "1.25CM": (24000.0, 24250.0),
    "6MM": (47000.0, 47200.0), "4MM": (75500.0, 81000.0),
    "2.5MM": (119980.0, 123000.0), "2MM": (134000.0, 149000.0),
    "1MM": (241000.0, 250000.0), "SUBMM": (300000.0, 7500000.0),
}


def expand(table):
    out = {}
    for mode, values in table.items():
        for raw in values.split():
            out[SPACE_FOR_HYPHEN.get(raw, raw)] = mode
    return out


def test_submodes():
    print("=== SUBMODE -> MODE ===")
    expected = expand(SUBMODES)
    table = A.SUBMODE_TO_MODE

    # Duplicate literal keys are invisible at runtime: the last one wins.
    import re
    src = open(os.path.join(os.path.dirname(HERE), "src", "adif2xlsx.py"),
               encoding="utf-8").read()
    start = src.index("SUBMODE_TO_MODE")
    block = src[start:src.index("\n}", start)]
    keys = re.findall(r'^\s*"([^"]+)":', block, re.M)
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    check(not duplicates, "the submode table has no duplicate keys",
          str(duplicates))

    wrong = sorted(f"{s}: {table[s]} should be {m}"
                   for s, m in expected.items()
                   if s in table and table[s] != m)
    check(not wrong, f"all {len(expected)} submodes map to their parent mode",
          "; ".join(wrong[:5]))

    missing = sorted(s for s in expected if s not in table)
    check(not missing,
          f"the Submode enumeration is fully covered ({len(expected)} values)",
          f"{len(missing)} missing: {missing[:6]}")

    extra = sorted(s for s in table if s not in expected)
    check(not extra, "the table holds no non-submode values", str(extra[:6]))


def test_modes():
    print("\n=== MODE enumeration ===")
    check(len(MODES) == 49, f"the MODE list has 49 values (found {len(MODES)})")
    # A record carrying SUBMODE=<a mode name> must still yield that mode, which
    # is what happens when the lookup misses and the value is used as-is.
    for mode in ("FT8", "SSB", "CW", "RTTY", "AM", "FM"):
        check(mode not in A.SUBMODE_TO_MODE or A.SUBMODE_TO_MODE[mode] == mode,
              f"{mode} is not remapped away from itself",
              str(A.SUBMODE_TO_MODE.get(mode)))


def test_bands():
    print("\n=== BAND enumeration ===")
    table = {name: (low, high) for name, low, high in A.BAND_PLAN}
    missing = sorted(b for b in BANDS if b not in table)
    check(not missing, f"all {len(BANDS)} published bands are present",
          str(missing))
    extra = sorted(b for b in table if b not in BANDS)
    check(not extra, "the band table holds no unpublished bands", str(extra))
    wrong = sorted(f"{b}: {table[b]} != {BANDS[b]}"
                   for b in BANDS if b in table and table[b] != BANDS[b])
    check(not wrong, "band edges match the published bounds",
          "; ".join(wrong[:5]))


def test_mode_derivation():
    print("\n=== MODE derived from SUBMODE when MODE is absent ===")
    # Mirrors the converter's rule: an explicit MODE wins; otherwise a known
    # submode resolves to its parent, and an unknown one is used verbatim.
    def derive(mode, submode):
        mode = (mode or "").upper().strip()
        submode = (submode or "").upper().strip()
        if not mode and submode:
            mode = A.SUBMODE_TO_MODE.get(submode, submode)
        return mode

    cases = [
        # An explicit MODE always wins.
        ("MFSK", "FT8", "MFSK"),
        ("SSB", "USB", "SSB"),
        # FT8 became a MODE in ADIF 3.1.0, so a bare SUBMODE=FT8 resolves to
        # FT8 itself, not to MFSK -- which is what modern FT8 logs want.
        ("", "FT8", "FT8"),
        # True submodes resolve to their parent mode.
        ("", "FT4", "MFSK"),
        ("", "LSB", "SSB"),
        ("", "USB", "SSB"),
        ("", "PCW", "CW"),
        ("", "ASCI", "RTTY"),
        # DMR is import-only as a MODE: it must fold into DIGITALVOICE.
        ("", "DMR", "DIGITALVOICE"),
        ("", "DSTAR", "DIGITALVOICE"),
        ("", "VARA HF", "DYNAMIC"),
        ("", "JT9E FAST", "JT9"),
        ("", "OLIVIA 32/1000", "OLIVIA"),
        ("", "Q65", "MFSK"),
        # An unknown value is passed through rather than dropped.
        ("", "SOMETHINGNEW", "SOMETHINGNEW"),
        ("", "", ""),
    ]
    wrong = [f"{m}/{s} -> {derive(m, s)} (want {want})"
             for m, s, want in cases if derive(m, s) != want]
    check(not wrong, f"all {len(cases)} derivation cases are correct",
          "; ".join(wrong[:4]))


def main():
    test_submodes()
    test_modes()
    test_bands()
    test_mode_derivation()
    print(f"\n{'=' * 60}")
    print(f"checks: {CHECKS}   failures: {len(FAILURES)}")
    for item in FAILURES:
        print(f"  - {item}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
