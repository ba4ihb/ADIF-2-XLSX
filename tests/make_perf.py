#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate perf_1000.adi -- a 1000-record ADIF file for the timing check.

Records vary band, mode, callsign and optional-field coverage so the output is
not a degenerate single-column workbook.

    python make_perf.py
"""

from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))

BANDS = ["160M", "80M", "40M", "30M", "20M", "17M", "15M", "12M", "10M",
         "6M", "2M", "70CM"]
FREQ_BY_BAND = {
    "160M": 1.840, "80M": 3.573, "40M": 7.074, "30M": 10.136, "20M": 14.074,
    "17M": 18.100, "15M": 21.074, "12M": 24.915, "10M": 28.074, "6M": 50.313,
    "2M": 144.174, "70CM": 432.100,
}
MODES = [("SSB", "USB"), ("CW", ""), ("MFSK", "FT8"), ("MFSK", "FT4"),
         ("RTTY", ""), ("FM", ""), ("PSK", "PSK31"), ("MFSK", "MSK144")]
PREFIXES = ["K", "W", "N", "DL", "JA", "VK", "ZL", "G", "F", "EA", "I", "PY",
            "UA", "SM", "ON", "HB9", "ZS", "LU", "VE", "KH6"]


def main() -> int:
    lines = ["ADIF to Excel -- 1000 record performance fixture." + "\n",
             "<ADIF_VER:5>3.1.7<PROGRAMID:7>PERFGEN<EOH>" + "\n"]

    for i in range(1000):
        band = BANDS[i % len(BANDS)]
        mode, submode = MODES[i % len(MODES)]
        call = f"{PREFIXES[i % len(PREFIXES)]}{i}{'ABC'[i % 3]}"
        day = (i % 28) + 1
        month = (i % 12) + 1
        qso_date = f"2024{month:02d}{day:02d}"
        time_on = f"{(i * 7) % 24:02d}{(i * 13) % 60:02d}{(i * 29) % 60:02d}"
        time_off = f"{(i * 7) % 24:02d}{((i * 13) + 1) % 60:02d}00"
        freq = FREQ_BY_BAND[band] + (i % 50) / 1000.0

        fields = [
            ("CALL", call),
            ("QSO_DATE", qso_date),
            ("TIME_ON", time_on),
            ("TIME_OFF", time_off),
            ("FREQ", f"{freq:.6f}"),
            ("BAND", band),
            ("MODE", mode),
            ("RST_SENT", "59" if mode not in ("CW", "RTTY", "PSK", "MFSK") else "599"),
            ("RST_RCVD", "59" if mode not in ("CW", "RTTY", "PSK", "MFSK") else "599"),
            ("STATION_CALLSIGN", "N0CALL"),
        ]
        if submode:
            fields.append(("SUBMODE", submode))
        if i % 3 == 0:
            fields.append(("NAME", f"Op{i}"))
        if i % 4 == 0:
            fields.append(("GRIDSQUARE", f"FN{i % 90:02d}AB"))
        if i % 5 == 0:
            fields.append(("DXCC", str(200 + (i % 100))))
        if i % 7 == 0:
            fields.append(("COMMENT", "contest QSO number " + str(i)))
        if i % 11 == 0:
            fields.append(("APP_LOTW_QSL_SENT", "Y"))
            fields.append(("APP_LOTW_QSL_RCVD", "Y"))

        lines.append(
            "".join(f"<{n}:{len(v)}>{v}" for n, v in fields) + "<EOR>\n"
        )

    os.makedirs(os.path.join(HERE, "fixtures"), exist_ok=True)
    path = os.path.join(HERE, "fixtures", "perf_1000.adi")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(lines))
    print(f"wrote tests/fixtures/perf_1000.adi ({os.path.getsize(path)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
