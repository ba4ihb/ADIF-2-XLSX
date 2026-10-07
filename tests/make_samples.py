#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the sample ADIF files used to test adif2xlsx.py.

Length prefixes are computed from the actual value, so the files can never
drift out of alignment with the ADIF spec.  Run:

    python make_samples.py
"""

from __future__ import annotations

import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(HERE, "fixtures", "samples")

# Newline as an explicit constant: keeps this generator
# free of escape sequences that can be mangled in transit.
EOL = chr(10)


def f(name: str, value) -> str:
    """Render one ADIF field with a computed character-length prefix."""
    value = "" if value is None else str(value)
    return f"<{name}:{len(value)}>{value}"


def eor() -> str:
    return "<EOR>"


def record(*pairs) -> str:
    return "".join(f(n, v) for n, v in pairs) + eor()


SAMPLE_LOG = [
    # --- header ------------------------------------------------------------
    [("<ADIF_VER:5>", "3.1.7")],
    # --- 16 QSO records, deliberately mixing which fields appear ----------
    ("KH6BB", "20080608", "180108", "180245", {
        "FREQ": "14.26300", "BAND": "20M", "MODE": "SSB", "RST_SENT": "56",
        "RST_RCVD": "59", "STATION_CALLSIGN": "N0CALL", "NAME": "Bill",
        "QTH": "Honolulu", "GRIDSQUARE": "BL11AJ", "DXCC": "110",
        "COUNTRY": "Hawaii, USA", "COMMENT": "First KH6 on 20m this season",
    }),
    ("DL1ABC", "20240115", "071503", "071945", {
        "FREQ": "14.074000", "BAND": "20M", "MODE": "MFSK", "SUBMODE": "FT8",
        "RST_SENT": "-12", "RST_RCVD": "-08", "STATION_CALLSIGN": "N0CALL",
        "TX_PWR": "100", "PROP_MODE": "ES", "NAME": "Klaus", "QTH": "Munich",
        "GRIDSQUARE": "JN58SD",
    }),
    # TIME_ON in HHMM form (no seconds) -- must still parse.
    ("JA1XX", "20240116", "2330", "2336", {
        "FREQ": "7.030000", "BAND": "40M", "MODE": "CW", "RST_SENT": "599",
        "RST_RCVD": "579", "STATION_CALLSIGN": "N0CALL", "NAME": "Hiro",
        "COMMENT": "QSB",
    }),
    ("W1AW", "20240120", "150000", "150412", {
        "FREQ": "21.25000", "BAND": "15M", "MODE": "SSB", "RST_SENT": "59",
        "RST_RCVD": "59", "STATION_CALLSIGN": "N0CALL", "OPERATOR": "N0CALL",
        "ARRL_SECT": "CTX", "CONTEST_ID": "ARRL-DX-CW",
    }),
    ("VK2XYZ", "20240201", "091212", "091900", {
        "FREQ": "18.100000", "BAND": "17M", "MODE": "SSB", "SUBMODE": "USB",
        "RST_SENT": "55", "RST_RCVD": "57", "STATION_CALLSIGN": "N0CALL",
        "NAME": "Bruce", "QTH": "Sydney", "GRIDSQUARE": "QF56OD", "DXCC": "150",
    }),
    # No TIME_OFF at all.
    ("G3XYZ", "20240214", "184530", None, {
        "FREQ": "3.573000", "BAND": "80M", "MODE": "MFSK", "SUBMODE": "FT8",
        "RST_SENT": "-05", "RST_RCVD": "-15", "STATION_CALLSIGN": "N0CALL",
    }),
    ("VE3ABC", "20240303", "020304", "020900", {
        "FREQ": "1.840000", "BAND": "160M", "MODE": "CW", "RST_SENT": "599",
        "RST_RCVD": "599", "STATION_CALLSIGN": "N0CALL", "NAME": "Dave",
    }),
    ("ON4UN", "20240401", "120000", None, {
        "FREQ": "144.3000", "BAND": "2M", "MODE": "FM", "RST_SENT": "59",
        "RST_RCVD": "59", "STATION_CALLSIGN": "N0CALL", "SAT_NAME": "SO-50",
        "PROP_MODE": "SAT",
    }),
    # BAND present, FREQ absent -- FREQ_RX only.
    ("PY2ZZZ", "20240410", "203045", "203500", {
        "BAND": "10M", "MODE": "RTTY", "RST_SENT": "599", "RST_RCVD": "599",
        "STATION_CALLSIGN": "N0CALL", "FREQ_RX": "28.08000",
    }),
    ("ZL1AA", "20240505", "034500", None, {
        "FREQ": "50.313000", "BAND": "6M", "MODE": "MFSK", "SUBMODE": "MSK144",
        "RST_SENT": "-01", "RST_RCVD": "+12", "STATION_CALLSIGN": "N0CALL",
        "COMMENT": "6m Es opening",
    }),
    ("EA5ABC", "20240606", "161500", "162000", {
        "FREQ": "24.91500", "BAND": "12M", "MODE": "SSB", "RST_SENT": "53",
        "RST_RCVD": "55", "STATION_CALLSIGN": "N0CALL", "NAME": "Maria",
        "QTH": "Valencia",
    }),
    ("UA0QQQ", "20240707", "235959", None, {
        "FREQ": "10.136000", "BAND": "30M", "MODE": "PSK", "SUBMODE": "PSK31",
        "RST_SENT": "599", "RST_RCVD": "589", "STATION_CALLSIGN": "N0CALL",
    }),
    ("K1ABC", "20240808", "000001", "000500", {
        "FREQ": "28.50000", "BAND": "10M", "MODE": "SSB", "SUBMODE": "LSB",
        "RST_SENT": "59", "RST_RCVD": "59", "STATION_CALLSIGN": "N0CALL",
        "QSL_SENT": "Y", "QSL_RCVD": "N", "LOTW_QSL_SENT": "Y",
    }),
    ("HB9XYZ", "20240909", "083000", "084000", {
        "FREQ": "430.2500", "BAND": "70CM", "MODE": "FM", "RST_SENT": "59",
        "RST_RCVD": "59", "STATION_CALLSIGN": "N0CALL", "FREQ_RX": "439.2500",
        "COMMENT": "Repeater contact",
    }),
    # SUBMODE without MODE -- MODE must be derived from the submode table.
    ("LU1AA", "20241010", "112233", "113000", {
        "FREQ": "144.174000", "BAND": "2M", "SUBMODE": "FT8",
        "RST_SENT": "-10", "RST_RCVD": "-03", "STATION_CALLSIGN": "N0CALL",
        "GRIDSQUARE": "GF05RJ",
    }),
    # Zero-length value, plus a non-ASCII name.
    ("SM5ABC", "20241111", "050505", "051010", {
        "FREQ": "5.351500", "BAND": "60M", "MODE": "CW", "RST_SENT": "579",
        "RST_RCVD": "559", "STATION_CALLSIGN": "N0CALL", "COMMENT": "",
        "NAME": "\u00c5ke",
    }),
    # FREQ only, no BAND -- BAND must be derived from the frequency.
    ("ZS6ZZ", "20241212", "061200", "061500", {
        "FREQ": "3.700000", "MODE": "SSB", "RST_SENT": "55", "RST_RCVD": "55",
        "STATION_CALLSIGN": "N0CALL",
    }),
]


def build_sample_log() -> str:
    out = io.StringIO()
    count = len(SAMPLE_LOG) - 1  # the first entry is the header
    out.write(f"ADIF to Excel converter -- sample log ({count} QSOs, mixed field sets)."
              + EOL)
    out.write("All times are UTC. Length prefixes are computed, not hand-written.\n\n")
    out.write(f("ADIF_VER", "3.1.7") + f("PROGRAMID", "ADIF2XLSXDEMO")
              + f("PROGRAMVERSION", "1.0.0")
              + f("CREATED_TIMESTAMP", "20250115 120000") + "\n")
    out.write("<EOH>\n\n")
    for call, date, t_on, t_off, rest in SAMPLE_LOG[1:]:
        pairs = [("CALL", call), ("QSO_DATE", date), ("TIME_ON", t_on)]
        if t_off:
            pairs.append(("TIME_OFF", t_off))
        pairs.extend(sorted(rest.items()))
        out.write(record(*pairs) + "\n\n")
    return out.getvalue()


LOTW_QUIRKS = """LOTW-style ADIF export sample -- exercises the quirks a real parser must survive.

1. Header fields and QSO fields, with <EOH> omitted entirely.
2. Lower-case field names.
3. Whitespace padding inside field values.
4. A repeated field name within one record (later value wins).
5. APP_LoTW_* application-defined fields, incl. a numeric-suffixed name.
6. A record with FREQ but no BAND (band must be derived from frequency).
7. A record with BAND but no FREQ.
8. <COMMENT:0> zero-length value.
9. Unknown/proprietary fields that must still surface as columns.
10. Trailing free text that is not ADIF and must be ignored.
"""


def build_lotw_quirks() -> str:
    out = io.StringIO()
    out.write(LOTW_QUIRKS + "\n")

    # Header written inline with the first record: no <EOH> anywhere.
    out.write(
        "<ADIF_VER:5>3.1.7 <PROGRAMID:4>LOTW <CREATED_TIMESTAMP:15>20250102 030405"
        "\n\n"
    )

    # Record 1: full LoTW credit set. Note the lower-case <time_on>.
    out.write(record(
        ("CALL", "KH6BB"), ("QSO_DATE", "20080608"), ("time_on", "180108"),
        ("TIME_OFF", "180245"), ("FREQ", "14.26300"), ("BAND", "20M"),
        ("MODE", "SSB"), ("RST_SENT", "56"), ("RST_RCVD", "59"),
        ("STATION_CALLSIGN", "N0CALL"),
        ("APP_LOTW_CREDIT_GRANTED", "DXCC;WAS;WAC;"),
        ("APP_LOTW_QSL_SENT", "Y"), ("APP_LOTW_QSL_RCVD", "Y"),
        ("APP_LOTW_NUMREC", "1"),
    ) + "\n")

    # Record 2: 2xQSL flag, MODEGROUP, long COUNTRY value.
    out.write(record(
        ("CALL", "DL1AB"), ("QSO_DATE", "20240115"), ("TIME_ON", "071503"),
        ("FREQ", "14.074000"), ("BAND", "20M"), ("MODE", "MFSK"),
        ("SUBMODE", "FT8"), ("RST_SENT", "-12"), ("RST_RCVD", "-08"),
        ("STATION_CALLSIGN", "N0CALL"), ("APP_LOTW_2xQSL", "Y"),
        ("APP_LOTW_MODEGROUP", "DATA"), ("DXCC", "230"),
        ("COUNTRY", "Fed. Rep. of Germany"),
    ) + "\n")

    # Record 3: HHMM time with no seconds.
    out.write(record(
        ("CALL", "JA1XX"), ("QSO_DATE", "20240116"), ("TIME_ON", "2330"),
        ("BAND", "40M"), ("MODE", "CW"), ("RST_SENT", "599"),
        ("RST_RCVD", "579"), ("STATION_CALLSIGN", "N0CALL"),
        ("APP_LOTW_RP", "N"),
    ) + "\n")

    # Record 4: repeated MODE (last value wins) + zero-length COMMENT.
    out.write(record(
        ("CALL", "W1AW"), ("QSO_DATE", "20240120"), ("TIME_ON", "150000"),
        ("FREQ", "21.25000"), ("BAND", "15M"), ("MODE", "SSB"), ("MODE", "CW"),
        ("RST_SENT", "59"), ("RST_RCVD", "59"), ("STATION_CALLSIGN", "N0CALL"),
        ("COMMENT", ""),
    ) + EOL)

    # Record 5: whitespace-padded value; FREQ only, so BAND must be derived.
    out.write(record(
        ("CALL", "EA5ABC"), ("QSO_DATE", "20240606"), ("TIME_ON", "161500"),
        ("FREQ", "24.91500"), ("MODE", "SSB"), ("RST_SENT", "53"),
        ("RST_RCVD", "55"), ("STATION_CALLSIGN", "N0CALL"),
        ("PROP_MODE", "  ES  "), ("SAT_NAME", "RS-44"),
    ) + EOL)

    out.write(EOL + "Some trailing free text that is not ADIF and must be ignored." + EOL)
    return out.getvalue()


def main() -> int:
    targets = [
        ("sample_log.adi", build_sample_log()),
        ("sample_lotw_quirks.adi", build_lotw_quirks()),
    ]
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    for name, text in targets:
        path = os.path.join(SAMPLES_DIR, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote tests/fixtures/samples/{name} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
