# -*- coding: utf-8 -*-
r"""G3 - required-field mapping, real Excel date/time types, no timezone shift,
invalid date/time handling.

Run: python verification\cases_map.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (adif, as_date, dump, header_map, load, out_path,  # noqa: E402
                    qso_rows, record, run, serial_of, write_case)

HDR = "<ADIF_VER:5>3.1.4<PROGRAMID:4>TEST<EOH>\n"
CMD = "python adif2xlsx.py verification\\cases\\{f} -o verification\\out\\{o}"


def one(name, text, outname):
    path = write_case(name, text)
    out = out_path(outname)
    if os.path.exists(out):
        os.remove(out)
    p = run([path, "-o", out])
    rows = qso_rows(out) if os.path.exists(out) else []
    ws = load(out)["QSOs"] if os.path.exists(out) else None
    return p, rows, ws


def cellinfo(ws, row, colname):
    hdr = header_map(ws)
    if colname not in hdr:
        return None, None
    c = ws.cell(row=row, column=hdr[colname])
    return c.value, c.number_format


def g3a_full_mapping():
    text = HDR + adif([("CALL", "w1aw/2"), ("QSO_DATE", "20240101"), ("TIME_ON", "1200"),
                       ("FREQ", "14.074"), ("BAND", "20M"), ("MODE", "FT8"),
                       ("RST_SENT", "-10"), ("RST_RCVD", "-12"),
                       ("STATION_CALLSIGN", "dl1aa")]) + "\n"
    p, rows, ws = one("g3a_required.adi", text, "g3a.xlsx")
    r = rows[0] if rows else {}
    exp = {"CALL": "W1AW/2", "TIME_ON_UTC": dt.time(12, 0),
           "FREQ_MHZ": 14.074, "BAND": "20M", "MODE": "FT8", "RST_SENT": "-10",
           "RST_RCVD": "-12", "STATION_CALLSIGN": "DL1AA"}
    bad = {k: (v, r.get(k)) for k, v in exp.items() if r.get(k) != v}
    for col in list(exp) + ["QSO_DATE"]:
        if col not in r:
            bad[col] = ("present", "MISSING COLUMN")
    if as_date(r.get("QSO_DATE")) != dt.date(2024, 1, 1):
        bad["QSO_DATE"] = ("2024-01-01", r.get("QSO_DATE"))
    dval, dfmt = cellinfo(ws, 2, "QSO_DATE")
    tval, tfmt = cellinfo(ws, 2, "TIME_ON_UTC")
    dtype, dserial = serial_of(out_path("g3a.xlsx"), "QSO_DATE", 2)
    integral = dserial is not None and float(dserial).is_integer()
    ok = (p.returncode == 0 and len(rows) == 1 and not bad and dfmt == "yyyy-mm-dd"
          and tfmt == "hh:mm:ss" and isinstance(dval, dt.date)
          and isinstance(tval, dt.time) and integral
          and getattr(dval, "hour", 0) == 0 and getattr(dval, "minute", 0) == 0)
    record("G3a all required fields mapped; QSO_DATE/TIME_ON are real Excel values",
           "9 required fields correct; QSO_DATE stored as an integral Excel date serial "
           "(fmt yyyy-mm-dd); TIME_ON_UTC a real time (fmt hh:mm:ss)",
           f"rc={p.returncode} rows={len(rows)} mismatches={bad} date={dval!r}/{dfmt!r} "
           f"raw=({dtype},{dserial}) time={tval!r}/{tfmt!r}",
           ok, note="openpyxl reads any date-formatted cell back as datetime (its own "
                    "round-trip of datetime.date does the same; verified separately)",
           cmd=CMD.format(f="g3a_required.adi", o="g3a.xlsx"))


def g3b_time_formats():
    text = (HDR
            + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "0000"),
                    ("STATION_CALLSIGN", "DL1AA")]) + "\n"
            + adif([("CALL", "K2DEF"), ("QSO_DATE", "20240101"), ("TIME_ON", "235959"),
                    ("STATION_CALLSIGN", "DL1AA")]) + "\n"
            + adif([("CALL", "N3XYZ"), ("QSO_DATE", "20240101"), ("TIME_ON", "120000"),
                    ("STATION_CALLSIGN", "DL1AA")]) + "\n")
    p, rows, ws = one("g3b_time_formats.adi", text, "g3b.xlsx")
    got = [r.get("TIME_ON_UTC") for r in rows]
    dates = [as_date(r.get("QSO_DATE")) for r in rows]
    exp = [dt.time(0, 0), dt.time(23, 59, 59), dt.time(12, 0, 0)]
    expdates = [dt.date(2024, 1, 1)] * 3
    fmts = {cellinfo(ws, i, "TIME_ON_UTC")[1] for i in (2, 3, 4)}
    tfmts = {type(v) for v in got}
    ok = (p.returncode == 0 and got == exp and dates == expdates
          and fmts == {"hh:mm:ss"} and tfmts == {dt.time})
    record("G3b TIME_ON HHMM (0000) and HHMMSS (235959, 120000), no timezone shift",
           f"times={exp}; dates all 2024-01-01; type=time; fmt hh:mm:ss",
           f"rc={p.returncode} times={got} dates={dates} types={tfmts} formats={fmts}",
           ok, cmd=CMD.format(f="g3b_time_formats.adi", o="g3b.xlsx"))


def g3c_2359_stays():
    text = HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "2359"),
                       ("STATION_CALLSIGN", "DL1AA")]) + "\n"
    p, rows, ws = one("g3c_utc_2359.adi", text, "g3c.xlsx")
    r = rows[0] if rows else {}
    ok = (r.get("TIME_ON_UTC") == dt.time(23, 59)
          and as_date(r.get("QSO_DATE")) == dt.date(2024, 1, 1))
    record("G3c record logged 23:59 stays 23:59 on the same date (no tz conversion)",
           "TIME_ON_UTC == 23:59:00, QSO_DATE == 2024-01-01",
           f"time={r.get('TIME_ON_UTC')!r} date={r.get('QSO_DATE')!r}",
           ok, cmd=CMD.format(f="g3c_utc_2359.adi", o="g3c.xlsx"))


def g3d_invalid_date():
    text = (HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20241340"), ("TIME_ON", "1200"),
                        ("STATION_CALLSIGN", "DL1AA")]) + "\n")
    p, rows, ws = one("g3d_bad_date.adi", text, "g3d.xlsx")
    val = rows[0].get("QSO_DATE") if rows else "NO ROW"
    ok = p.returncode == 0 and len(rows) == 1 and val is None and ("WARNING" in p.stdout or "NOTE" in p.stdout)
    record("G3d invalid <QSO_DATE:8>20241340",
           "no crash; empty date cell; a warning is printed",
           f"rc={p.returncode} rows={len(rows)} QSO_DATE={val!r} warning={'WARNING' in p.stdout}",
           ok, cmd=CMD.format(f="g3d_bad_date.adi", o="g3d.xlsx"))


def g3e_invalid_time():
    text = (HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "256099"),
                        ("STATION_CALLSIGN", "DL1AA")]) + "\n")
    p, rows, ws = one("g3e_bad_time.adi", text, "g3e.xlsx")
    val = rows[0].get("TIME_ON_UTC") if rows else "NO ROW"
    ok = p.returncode == 0 and len(rows) == 1 and val is None and ("WARNING" in p.stdout or "NOTE" in p.stdout)
    record("G3e invalid <TIME_ON:6>256099",
           "no crash; empty time cell; a warning is printed",
           f"rc={p.returncode} rows={len(rows)} TIME_ON_UTC={val!r} warning={'WARNING' in p.stdout}",
           ok, cmd=CMD.format(f="g3e_bad_time.adi", o="g3e.xlsx"))


def g3f_time_off_and_date_off():
    text = HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "2300"),
                       ("QSO_DATE_OFF", "20240102"), ("TIME_OFF", "0130"),
                       ("STATION_CALLSIGN", "DL1AA")]) + "\n"
    p, rows, ws = one("g3f_time_off.adi", text, "g3f.xlsx")
    r = rows[0] if rows else {}
    ok = (r.get("TIME_OFF_UTC") == dt.time(1, 30)
          and as_date(r.get("QSO_DATE_OFF")) == dt.date(2024, 1, 2))
    record("G3f TIME_OFF / QSO_DATE_OFF mapped and typed",
           "TIME_OFF_UTC == 01:30, QSO_DATE_OFF == 2024-01-02",
           f"TIME_OFF_UTC={r.get('TIME_OFF_UTC')!r} QSO_DATE_OFF={r.get('QSO_DATE_OFF')!r}",
           ok, cmd=CMD.format(f="g3f_time_off.adi", o="g3f.xlsx"))


def g3g_leap_second():
    text = HDR + adif([("CALL", "W1AW"), ("QSO_DATE", "20240101"), ("TIME_ON", "235960"),
                       ("STATION_CALLSIGN", "DL1AA")]) + "\n"
    p, rows, ws = one("g3g_leap_second.adi", text, "g3g.xlsx")
    val = rows[0].get("TIME_ON_UTC") if rows else None
    ok = p.returncode == 0 and val == dt.time(23, 59, 59)
    record("G3g leap second 235960",
           "no crash; clamped to 23:59:59 (Excel cannot store :60)",
           f"rc={p.returncode} TIME_ON_UTC={val!r}",
           ok, note="clamping is silent - a logged 23:59:60 becomes 23:59:59",
           cmd=CMD.format(f="g3g_leap_second.adi", o="g3g.xlsx"))


def main():
    for fn in (g3a_full_mapping, g3b_time_formats, g3c_2359_stays, g3d_invalid_date,
               g3e_invalid_time, g3f_time_off_and_date_off, g3g_leap_second):
        fn()
    dump("g3_mapping")


if __name__ == "__main__":
    main()
