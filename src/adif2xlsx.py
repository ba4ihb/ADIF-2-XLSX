#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adif2xlsx.py -- ADIF to Excel converter.

Converts ADIF (.adi / .adif) log exports from LoTW, QRZ Logbook, Club Log,
N1MM, WSJT-X, etc. into a structured Excel workbook (.xlsx).

Design notes
------------
* Single file, standard library + openpyxl only. Runs on Windows / Python 3.10+.
* The parser is a strict streaming reader: ADIF field values are located by their
  declared character length, so values may contain '<', '>', spaces and newlines.
* Field names are case-insensitive and unknown/optional fields are discovered
  automatically -- nothing is dropped because of a hard-coded field list.
* All times are UTC. No timezone conversion is ever performed.

Usage
-----
    python adif2xlsx.py log1.adi log2.adif -o out.xlsx
    python adif2xlsx.py C:\\Logs\\LoTW -o lotw.xlsx --recursive
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import math
import os
import re
import sys
import tempfile
from collections import OrderedDict
from typing import Dict, Iterable, Iterator, List, NamedTuple, Optional, Sequence, Tuple

__version__ = "1.0.0"

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError as exc:  # pragma: no cover - dependency guard
    # emit() is defined further down, and in a windowed build there may be no
    # stderr at all, so this guard writes defensively by hand.
    _message = ("ERROR: openpyxl is required.\n"
                "Install it with:  pip install openpyxl\n")
    if sys.stderr is not None:
        sys.stderr.write(_message)
    raise SystemExit(2) from exc

# dxcc.py and postage.py sit next to this file.  They are imported explicitly so
# that PyInstaller bundles them into the standalone executable.
import dxcc
import postage


# ---------------------------------------------------------------------------
# Crash safety.
#
# A windowed build (PyInstaller --noconsole) has NO console streams at all:
# sys.stdout and sys.stderr are both None.  Writing a diagnostic to them raises
# AttributeError, the process dies, and because there is no console the window
# simply disappears -- the classic "double-click and it flashes away" report.
# Everything below makes that impossible: writes are guarded, an unhandled
# exception is written to a log file AND shown in a dialog.
# ---------------------------------------------------------------------------
CRASH_LOG_NAME = "adif2xlsx-crash.log"


def log_path() -> str:
    """Where diagnostics go when there is no console.  Must never raise."""
    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "adif2xlsx")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, CRASH_LOG_NAME)
    except OSError:
        try:
            return os.path.join(tempfile.gettempdir(), CRASH_LOG_NAME)
        except OSError:
            return CRASH_LOG_NAME


def write_log(message: str) -> None:
    """Append to the diagnostic log, silently doing nothing if impossible."""
    try:
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write(message)
            if not message.endswith("\n"):
                fh.write("\n")
    except OSError:
        pass


def emit(message: str) -> None:
    """Write to stderr if one exists, and always to the log."""
    stream = sys.stderr
    if stream is not None:
        try:
            stream.write(message)
            stream.flush()
        except (OSError, ValueError, AttributeError):
            pass
    write_log(message.rstrip("\n"))


def _show_error_dialog(title: str, text: str) -> None:
    """Show a message box, but only when nobody can read a console.

    A console build has already printed the error to stderr; opening a modal
    dialog there would block a script, a scheduled task or a test run forever
    on a dialog no one is present to dismiss.  ADIF2XLSX_NO_DIALOG suppresses
    it anywhere.
    """
    if sys.stderr is not None or sys.stdout is not None:
        return
    if os.environ.get("ADIF2XLSX_NO_DIALOG"):
        return
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, text)
        root.destroy()
    except Exception:  # noqa: BLE001 - no Tk, no display, headless: nothing to do
        pass


def _crash_report(exc_type, exc, tb) -> str:
    import traceback
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detail = "".join(traceback.format_exception(exc_type, exc, tb))
    return (f"\n===== {stamp} =====\n"
            f"adif2xlsx {__version__}  frozen={getattr(sys, 'frozen', False)}\n"
            f"argv={sys.argv!r}\n"
            f"cwd={os.getcwd()}\n"
            f"log={log_path()}\n"
            f"{detail}")


def main_guard(entry) -> int:
    """Run ``entry`` so that no failure can end in a silent disappearance."""
    try:
        return entry()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - this is the last line of defence
        import traceback
        report = _crash_report(type(exc), exc, exc.__traceback__)
        write_log(report)
        emit("ERROR: adif2xlsx hit an unexpected problem.\n")
        emit(traceback.format_exc())
        emit(f"Details were written to: {log_path()}\n")
        _show_error_dialog(
            "adif2xlsx 出错了",
            "程序遇到了意外错误，已记录到日志文件：\n\n"
            f"{log_path()}\n\n"
            f"{type(exc).__name__}: {exc}")
        return 1

EXCEL_MAX_ROWS = 1_048_576
ADIF_EXTENSIONS = (".adi", ".adif")

# ---------------------------------------------------------------------------
# ADIF header fields -- never emitted as data columns.
# ---------------------------------------------------------------------------
HEADER_FIELDS = frozenset(
    {"ADIF_VER", "PROGRAMID", "PROGRAMVERSION", "CREATED_TIMESTAMP"}
)

# ---------------------------------------------------------------------------
# Required output columns (English, upper case) mapped from ADIF fields.
# The key is the Excel column name, the value is the ADIF field name.
#
# "Required" here means two things, and they must not contradict each other:
#
#   1. the tool PROMISES these columns: they are documented, they always appear
#      in the interface as 必选, and they are written even if empty (a log with no
#      callsign is still a log, and silently dropping the column would hide why);
#   2. they are mapped to an ADIF field, so the mapping is the contract.
#
# QSO_DATE_OFF, TIME_OFF_UTC and SUBMODE used to be listed here while being
# dropped when empty, which contradicted both this list and the interface.  The
# project's own acceptance criterion ("如果某字段在所有记录中均为空，不输出该列")
# is the one that wins, so they are optional columns now -- see
# OPTIONAL_WELL_KNOWN below -- and this list holds only what is truly promised.
REQUIRED_COLUMNS: "OrderedDict[str, str]" = OrderedDict(
    [
        ("CALL", "CALL"),
        ("QSO_DATE", "QSO_DATE"),
        ("TIME_ON_UTC", "TIME_ON"),
        ("FREQ_MHZ", "FREQ"),
        ("BAND", "BAND"),
        ("MODE", "MODE"),
        ("RST_SENT", "RST_SENT"),
        ("RST_RCVD", "RST_RCVD"),
        ("STATION_CALLSIGN", "STATION_CALLSIGN"),
    ]
)

#: Well-known optional columns: mapped to an ADIF field, shown in the interface,
#: but written only when at least one record carries a value.  They are the three
#: that were previously mislabelled as required.
OPTIONAL_WELL_KNOWN: "OrderedDict[str, str]" = OrderedDict(
    [
        ("TIME_OFF_UTC", "TIME_OFF"),
        ("QSO_DATE_OFF", "QSO_DATE_OFF"),
        ("SUBMODE", "SUBMODE"),
    ]
)

# Source-file provenance column, injected by the converter.
SOURCE_COLUMN = "SOURCE_FILE"

# DXCC columns produced by the converter (not by any ADIF field).  Kept last so
# they read as derived data rather than something the log exported.
ENTITY_COLUMN = "DXCC_ENTITY"
ENTITY_SOURCE_COLUMN = "DXCC_SOURCE"

# QSL postage columns: what it costs to mail a card to that entity from
# mainland China, as an ordinary letter of the reference weight.
POSTAGE_COLUMN = "QSL_POSTAGE_AIR"
POSTAGE_DETAIL_COLUMN = "QSL_POSTAGE_DETAIL"
DERIVED_COLUMNS = (
    ENTITY_COLUMN, ENTITY_SOURCE_COLUMN, POSTAGE_COLUMN, POSTAGE_DETAIL_COLUMN,
)

# Columns that are always emitted even when every record is empty, so that the
# workbook has a stable, documented shape.  Everything else is dropped when
# completely empty (acceptance criterion: "no empty optional columns").
#
# This is REQUIRED_COLUMNS plus the three columns a merged log needs: the station
# callsign, the DXCC entity and the postage, plus the source file.  Every column
# documented as required is in here -- the two lists must not disagree, or the
# workbook would omit a column the documentation promises.  (They did disagree:
# QSO_DATE_OFF, TIME_OFF_UTC and SUBMODE were listed as required but were dropped
# when empty, so a log without them came out missing documented columns while the
# interface still showed them as 必选.)
ALWAYS_KEEP = frozenset(
    list(REQUIRED_COLUMNS)
    + [ENTITY_COLUMN, POSTAGE_COLUMN, SOURCE_COLUMN]
)

# Fields that are structural markers, not data.
STRUCTURAL_FIELDS = frozenset({"EOR", "EOH", "EOD"})

# ---------------------------------------------------------------------------
# The field catalogue.
#
# This is what the interface shows when you choose which columns to write, and
# what the command line accepts as --columns.  Keys are the column names used in
# the workbook, so REQUIRED_COLUMNS above stays the single source of truth for
# the mapped ones.
#
# Required columns are the ones the tool promises: a contact without a callsign,
# a date or a mode is not a usable log record.  Everything else is optional and
# is written only when it holds data.
# ---------------------------------------------------------------------------
FIELD_LABELS_ZH: Dict[str, str] = {
    # --- required, mapped from a named ADIF field ---
    "CALL": "对方呼号",
    "QSO_DATE": "通联日期(UTC)",
    "TIME_ON_UTC": "开始时间(UTC)",
    "TIME_OFF_UTC": "结束时间(UTC)",
    "QSO_DATE_OFF": "结束日期(UTC)",
    "FREQ_MHZ": "频率(MHz)",
    "FREQ_RX": "接收频率(MHz)",
    "BAND_RX": "接收波段",
    "BAND": "波段",
    "MODE": "模式",
    "SUBMODE": "子模式",
    "RST_SENT": "发送信号报告",
    "RST_RCVD": "接收信号报告",
    "STATION_CALLSIGN": "本方呼号",
    # --- derived by this tool ---
    "DXCC_ENTITY": "DXCC 实体",
    "DXCC_SOURCE": "实体判定依据",
    "QSL_POSTAGE_AIR": "QSL 邮资(RMB)",
    "QSL_POSTAGE_DETAIL": "邮资明细",
    "SOURCE_FILE": "来源文件",
    # --- common optional ADIF fields ---
    "NAME": "对方姓名",
    "QTH": "对方地址",
    "GRIDSQUARE": "网格坐标",
    # COUNTRY is the ADIF field the *log* supplies: a country or territory name.
    # It is NOT the DXCC entity -- one country can hold several entities (China
    # covers the mainland, Hong Kong, Macao, Taiwan and Scarborough Reef; Russia
    # splits into European and Asiatic).  Compare it with DXCC_ENTITY rather than
    # treating the two as the same thing.
    "COUNTRY": "国家/地区(日志填写)",
    "DXCC": "DXCC 编号(日志填写)",
    "CQZ": "CQ 分区",
    "ITUZ": "ITU 分区",
    "CONT": "大洲",
    "IOTA": "IOTA 编号",
    "PFX": "前缀",
    "TX_PWR": "发射功率",
    "PROP_MODE": "传播方式",
    "SAT_NAME": "卫星名称",
    "CONTEST_ID": "比赛名称",
    "SRX": "收到的序号",
    "STX": "发出的序号",
    "QSL_SENT": "QSL 已寄出",
    "QSL_RCVD": "QSL 已收到",
    "QSL_VIA": "QSL 转交",
    "LOTW_QSL_SENT": "LoTW 已上传",
    "LOTW_QSL_RCVD": "LoTW 已确认",
    "EQSL_QSL_SENT": "eQSL 已发送",
    "EQSL_QSL_RCVD": "eQSL 已确认",
    "COMMENT": "备注",
    "NOTES": "笔记",
    "OPERATOR": "操作员",
    "EMAIL": "电子邮箱",
    "STATE": "州/省",
    "CNTY": "县",
    "ARRL_SECT": "ARRL 分区",
    "MY_GRIDSQUARE": "本方网格",
    "MY_COUNTRY": "本方国家",
    "MY_CITY": "本方城市",
    "DISTANCE": "距离(km)",
    "LAT": "对方纬度",
    "LON": "对方经度",
}

#: Everything the tool can produce, required set first.  Computed once.
REQUIRED_FIELD_NAMES: Tuple[str, ...] = tuple(REQUIRED_COLUMNS)


def field_label(column: str) -> str:
    """Chinese label for a column, falling back to the column name itself."""
    return FIELD_LABELS_ZH.get(column, column)


def is_required_column(column: str) -> bool:
    """True for the mandatory set, which the tool always writes."""
    return column in REQUIRED_COLUMNS


#: Columns that are always written, whatever the selection says.  This is
#: ALWAYS_KEEP in a stable order, so a caller can assert on it directly: after
#: any conversion, every one of these is present.
MANDATORY_COLUMNS: Tuple[str, ...] = tuple(
    [c for c in REQUIRED_COLUMNS if c in ALWAYS_KEEP]
    + [c for c in ALWAYS_KEEP if c not in REQUIRED_COLUMNS]
)

#: The QSOs sheet has two header rows: the English column name, then its Chinese
#: name.  The English row stays because it is the documented interface and what
#: formulas expect; the Chinese row is what a person reads.
def column_header_label(column: str) -> str:
    """Chinese header for a column, or "" when it has no translation.

    Producer-specific fields (APP_LOTW_*, APP_N1MM_*, ...) have no meaningful
    Chinese name, so their second header cell is left empty rather than filled
    with something invented.
    """
    return FIELD_LABELS_ZH.get(column, "")


def describe_field(column: str) -> str:
    """One line for a tooltip: the Chinese label plus the ADIF field name."""
    label = field_label(column)
    source = REQUIRED_COLUMNS.get(column)
    if source:
        return f"{label}  ·  ADIF 字段 {source}"
    if column in DERIVED_COLUMNS:
        return f"{label}  ·  由本工具自动生成"
    if column == SOURCE_COLUMN:
        return f"{label}  ·  记录来自哪个文件"
    return f"{label}  ·  ADIF 字段 {column}"

# Internal marker added by iter_records to a record that ends at or before
# <EOH>, so parse_adif can keep header content off the QSO sheet.  It can never
# collide with a real ADIF field: names may not begin with a space.
HEADER_MARKER = " HEADER"

# Fields that identify a record as a QSO rather than as header content.  A
# header record never contains one, which is what lets a header be recognised
# by content when <EOH> is missing or when a header field such as LoTW's
# APP_LOTW_NUMREC collides with a legal QSO field name.
QSO_FIELDS = frozenset(
    {
        "CALL", "QSO_DATE", "TIME_ON", "TIME_OFF", "QSO_DATE_OFF", "FREQ",
        "FREQ_RX", "BAND", "BAND_RX", "MODE", "SUBMODE", "RST_SENT", "RST_RCVD",
        "STATION_CALLSIGN", "OPERATOR", "GRIDSQUARE", "DXCC", "COUNTRY", "NAME",
        "QTH", "COMMENT", "NOTES", "TX_PWR", "RX_PWR", "PROP_MODE", "SAT_NAME",
        "CONTEST_ID", "SRX", "STX", "SRX_STRING", "STX_STRING", "QSL_SENT",
        "QSL_RCVD", "QSLSDATE", "QSLRDATE", "EQSL_QSL_SENT", "EQSL_QSL_RCVD",
        "LOTW_QSL_SENT", "LOTW_QSL_RCVD", "LOTW_QSLSDATE", "LOTW_QSLRDATE",
        "CREDIT_GRANTED", "CREDIT_SUBMITTED", "IOTA", "PFX", "CQZ", "ITUZ",
        "CONT", "EMAIL", "AGE", "ADDRESS", "STATE", "CNTY", "ARRL_SECT",
    }
)

# ---------------------------------------------------------------------------
# ADIF field names recognised when deciding whether a file really is a log.
# A record containing none of these is markup that happened to look like a
# field, so it is discarded.  The list covers the ADIF QSO fields plus the
# proprietary names LoTW, QRZ Logbook, N1MM+ and WSJT-X are known to emit; it
# is only a validity smell test, never a filter on output columns -- unknown
# fields are still exported.
# ---------------------------------------------------------------------------
KNOWN_FIELDS = frozenset(
    """
    CALL QSO_DATE TIME_ON TIME_OFF QSO_DATE_OFF FREQ FREQ_RX BAND BAND_RX MODE
    SUBMODE RST_SENT RST_RCVD STATION_CALLSIGN OPERATOR NAME QTH GRIDSQUARE
    DXCC COUNTRY CQZ ITUZ CONT CQ_ZONE ITU_ZONE COMMENT NOTES TX_PWR RX_PWR
    PROP_MODE SAT_NAME SAT_MODE ANT_AZ ANT_EL ANT_PATH ARRL_SECT MY_ARRL_SECT
    SECTION EMAIL EMAIL2 WEB AGE ADDRESS ADDRESS1 ADDRESS2 ADDRESS3 CITY
    STATE POSTALCODE ZIP US_STATE CNTY IOTA PFX PREFIX SILENT_KEY SKCC
    QSL_SENT QSL_RCVD QSL_SENT_VIA QSL_RCVD_VIA QSL_VIA QSLSDATE QSLRDATE
    QSLMSG QSL_VIA_CALL EQSL_QSL_SENT EQSL_QSL_RCVD EQSL_QSLSDATE
    EQSL_QSLRDATE LOTW_QSL_SENT LOTW_QSL_RCVD LOTW_QSLSDATE LOTW_QSLRDATE
    CREDIT_GRANTED CREDIT_SUBMITTED CREDIT_REQUESTED CONTACTED_OP
    MY_CALL MY_CITY MY_CNTY MY_COUNTRY MY_CQ_ZONE MY_DXCC MY_GRIDSQUARE
    MY_IOTA MY_ITU_ZONE MY_NAME MY_POSTALCODE MY_POTA_REF MY_RIG MY_SIG
    MY_SIG_INFO MY_STATE MY_STREET MY_USACA_COUNTIES MY_VUCC_GRIDS
    OWNER_CALLSIGN POTA_REF SIG SIG_INFO SOTA_REF WWFF_REF
    CONTEST_ID SRX STX SRX_STRING STX_STRING PRECEDENCE CHECK CLASS
    EXCHANGE1 EXCHANGE2 EXCHANGE3 ARRL_CLASS ARRL_CHECK ARRL_PRECEDENCE
    CONTEST_NR CABRILLO AGE_INDEX DISTANCE BEARING FORCE_INIT SWL
    LAT LON GRIDSQUARE_EXT MY_LAT MY_LON ALTITUDE ANTENNA ANTENNA_HEIGHT
    TX_PWR_W RX_PWR_W RIG RIG_INFO INTERNET ONLINE STATION_ID SKCC_NR
    TEN_TEN TEN_TEN_NR DARC_DOK DOK JARL_PREFECTURE
    APP_LOTW_OWNCALL APP_LOTW_MODE APP_LOTW_MODEGROUP APP_LOTW_2XQSL
    APP_LOTW_QSLMODE APP_LOTW_QSO_TIMESTAMP APP_LOTW_RXQSO APP_LOTW_RXQSL
    APP_LOTW_CREDIT_GRANTED APP_LOTW_CREDIT_SUBMITTED APP_LOTW_NUMREC
    APP_LOTW_LASTQSL APP_LOTW_LASTQSORX APP_LOTW_EOF APP_LOTW_RP
    APP_LOTW_DXCC_ENTITY_STATUS APP_LOTW_MY_DXCC_ENTITY_STATUS
    APP_LOTW_NPSUNIT APP_LOTW_CQZ_USERINVALID APP_LOTW_ITUZ_USERINVALID
    APP_QRZLOG_LOGID APP_QRZLOG_QSLDATE APP_QRZLOG_STATUS
    APP_N1MM_EXCHANGE1 APP_N1MM_HQ APP_N1MM_POINTS APP_N1MM_RADIO_NR
    APP_N1MM_RUN1RUN2 APP_N1MM_SECTION APP_N1MM_CLASS
    APP_WSJTXT_APP APP_WSJTXT_VERSION
    USERDEF1 USERDEF2 USERDEF3
    """.split()
)

# ---------------------------------------------------------------------------
# BAND enumeration (ADIF 3.1.7) with inclusive lower / upper bounds in MHz.
# Bounds verified against the published ADIF band enumeration; used only to
# *derive* BAND from FREQ when the export omitted BAND.
# ---------------------------------------------------------------------------
BAND_PLAN: Tuple[Tuple[str, float, float], ...] = (
    ("2190M", 0.1357, 0.1378),
    ("630M", 0.472, 0.479),
    ("560M", 0.501, 0.504),
    ("160M", 1.8, 2.0),
    ("80M", 3.5, 4.0),
    ("60M", 5.06, 5.45),
    ("40M", 7.0, 7.3),
    ("30M", 10.1, 10.15),
    ("20M", 14.0, 14.35),
    ("17M", 18.068, 18.168),
    ("15M", 21.0, 21.45),
    ("12M", 24.89, 24.99),
    ("10M", 28.0, 29.7),
    ("8M", 40.0, 45.0),
    ("6M", 50.0, 54.0),
    ("5M", 54.0, 69.9),
    ("4M", 70.0, 71.0),
    ("2M", 144.0, 148.0),
    ("1.25M", 222.0, 225.0),
    ("70CM", 420.0, 450.0),
    ("33CM", 902.0, 928.0),
    ("23CM", 1240.0, 1300.0),
    ("13CM", 2300.0, 2450.0),
    ("9CM", 3300.0, 3500.0),
    ("6CM", 5650.0, 5925.0),
    ("3CM", 10000.0, 10500.0),
    ("1.25CM", 24000.0, 24250.0),
    ("6MM", 47000.0, 47200.0),
    ("4MM", 75500.0, 81000.0),
    ("2.5MM", 119980.0, 123000.0),
    ("2MM", 134000.0, 149000.0),
    ("1MM", 241000.0, 250000.0),
    ("SUBMM", 300000.0, 7500000.0),
)


def band_from_freq(freq_mhz: Optional[float]) -> Optional[str]:
    """Return the ADIF band name for a frequency in MHz, or None.

    A frequency exactly on a documented band edge is inside that band: 14.350,
    7.300, 29.700 and 148.000 are all legitimate logged limits and must resolve
    to 20M, 40M, 10M and 2M.  Each band therefore claims up to just below the
    next band's lower edge, and the bands are evaluated in ascending order, so
    adjacent entries can never both match.  Frequencies outside every defined
    band return None rather than a guess.
    """
    if freq_mhz is None or freq_mhz <= 0:
        return None
    f = round(float(freq_mhz), 9)
    for index, (name, low, high) in enumerate(BAND_PLAN):
        if f < low:
            return None
        upper = high
        if index + 1 < len(BAND_PLAN):
            nxt_low = BAND_PLAN[index + 1][1]
            if nxt_low <= high:
                upper = min(high, nxt_low) - 1e-9
        if f <= upper:
            return name
    return None


# SUBMODE -> canonical MODE, for exports that carry only SUBMODE.
# Source: ADIF 3.1.7 Mode/Submode enumeration.
SUBMODE_TO_MODE: Dict[str, str] = {
    # Submode -> parent MODE, from the ADIF 3.1.7 Submode enumeration.
    # Used only when a record carries SUBMODE but no MODE, so a logger
    # that writes MODE=MFSK SUBMODE=FT8 and one that writes only
    # SUBMODE=FT8 both produce MODE=MFSK.
    # PSK (50)
    "8PSK1000": "PSK", "8PSK1000F": "PSK", "8PSK1200F": "PSK", "8PSK125": "PSK",
    "8PSK125F": "PSK", "8PSK125FL": "PSK", "8PSK250": "PSK", "8PSK250F": "PSK",
    "8PSK250FL": "PSK", "8PSK500": "PSK", "8PSK500F": "PSK", "FSK31": "PSK",
    "PSK10": "PSK", "PSK1000": "PSK", "PSK1000RC2": "PSK", "PSK125": "PSK",
    "PSK125RC10": "PSK", "PSK125RC12": "PSK", "PSK125RC16": "PSK", "PSK125RC4": "PSK",
    "PSK125RC5": "PSK", "PSK250": "PSK", "PSK250RC2": "PSK", "PSK250RC3": "PSK",
    "PSK250RC5": "PSK", "PSK250RC6": "PSK", "PSK250RC7": "PSK", "PSK31": "PSK",
    "PSK500": "PSK", "PSK500RC2": "PSK", "PSK500RC3": "PSK", "PSK500RC4": "PSK",
    "PSK63": "PSK", "PSK63F": "PSK", "PSK63RC10": "PSK", "PSK63RC20": "PSK",
    "PSK63RC32": "PSK", "PSK63RC4": "PSK", "PSK63RC5": "PSK", "PSK800RC2": "PSK",
    "PSKAM10": "PSK", "PSKAM31": "PSK", "PSKAM50": "PSK", "PSKFEC31": "PSK",
    "QPSK125": "PSK", "QPSK250": "PSK", "QPSK31": "PSK", "QPSK500": "PSK", "QPSK63": "PSK",
    "SIM31": "PSK",
    # CHIP (2)
    "CHIP128": "CHIP", "CHIP64": "CHIP",
    # CW (1)
    "PCW": "CW",
    # DIGITALVOICE (5)
    "C4FM": "DIGITALVOICE", "DMR": "DIGITALVOICE", "DSTAR": "DIGITALVOICE",
    "FREEDV": "DIGITALVOICE", "M17": "DIGITALVOICE",
    # DOMINO (11)
    "DOM-M": "DOMINO", "DOM11": "DOMINO", "DOM16": "DOMINO", "DOM22": "DOMINO",
    "DOM4": "DOMINO", "DOM44": "DOMINO", "DOM5": "DOMINO", "DOM8": "DOMINO",
    "DOM88": "DOMINO", "DOMINOEX": "DOMINO", "DOMINOF": "DOMINO",
    # DYNAMIC (5)
    "FREEDATA": "DYNAMIC", "VARA FM 1200": "DYNAMIC", "VARA FM 9600": "DYNAMIC",
    "VARA HF": "DYNAMIC", "VARA SATELLITE": "DYNAMIC",
    # FSK (3)
    "SCAMP_FAST": "FSK", "SCAMP_SLOW": "FSK", "SCAMP_VSLOW": "FSK",
    # HELL (10)
    "FMHELL": "HELL", "FSKH105": "HELL", "FSKH245": "HELL", "FSKHELL": "HELL",
    "HELL80": "HELL", "HELLX5": "HELL", "HELLX9": "HELL", "HFSK": "HELL",
    "PSKHELL": "HELL", "SLOWHELL": "HELL",
    # ISCAT (2)
    "ISCAT-A": "ISCAT", "ISCAT-B": "ISCAT",
    # JT4 (7)
    "JT4A": "JT4", "JT4B": "JT4", "JT4C": "JT4", "JT4D": "JT4", "JT4E": "JT4",
    "JT4F": "JT4", "JT4G": "JT4",
    # JT65 (5)
    "JT65A": "JT65", "JT65B": "JT65", "JT65B2": "JT65", "JT65C": "JT65", "JT65C2": "JT65",
    # JT9 (17)
    "JT9-1": "JT9", "JT9-10": "JT9", "JT9-2": "JT9", "JT9-30": "JT9", "JT9-5": "JT9",
    "JT9A": "JT9", "JT9B": "JT9", "JT9C": "JT9", "JT9D": "JT9", "JT9E": "JT9",
    "JT9E FAST": "JT9", "JT9F": "JT9", "JT9F FAST": "JT9", "JT9G": "JT9",
    "JT9G FAST": "JT9", "JT9H": "JT9", "JT9H FAST": "JT9",
    # MFSK (19)
    "FSQCALL": "MFSK", "FST4": "MFSK", "FST4W": "MFSK", "FT2": "MFSK", "FT4": "MFSK",
    "JS8": "MFSK", "JTMS": "MFSK", "MFSK11": "MFSK", "MFSK128": "MFSK", "MFSK128L": "MFSK",
    "MFSK16": "MFSK", "MFSK22": "MFSK", "MFSK31": "MFSK", "MFSK32": "MFSK",
    "MFSK4": "MFSK", "MFSK64": "MFSK", "MFSK64L": "MFSK", "MFSK8": "MFSK", "Q65": "MFSK",
    # MTONE (2)
    "SCAMP_OO": "MTONE", "SCAMP_OO_SLW": "MTONE",
    # OFDM (2)
    "RIBBIT_PIX": "OFDM", "RIBBIT_SMS": "OFDM",
    # OLIVIA (7)
    "OLIVIA 16/1000": "OLIVIA", "OLIVIA 16/500": "OLIVIA", "OLIVIA 32/1000": "OLIVIA",
    "OLIVIA 4/125": "OLIVIA", "OLIVIA 4/250": "OLIVIA", "OLIVIA 8/250": "OLIVIA",
    "OLIVIA 8/500": "OLIVIA",
    # OPERA (2)
    "OPERA-BEACON": "OPERA", "OPERA-QSO": "OPERA",
    # PAC (3)
    "PAC2": "PAC", "PAC3": "PAC", "PAC4": "PAC",
    # PAX (1)
    "PAX2": "PAX",
    # QRA64 (5)
    "QRA64A": "QRA64", "QRA64B": "QRA64", "QRA64C": "QRA64", "QRA64D": "QRA64",
    "QRA64E": "QRA64",
    # ROS (3)
    "ROS-EME": "ROS", "ROS-HF": "ROS", "ROS-MF": "ROS",
    # RTTY (1)
    "ASCI": "RTTY",
    # SSB (2)
    "LSB": "SSB", "USB": "SSB",
    # THOR (11)
    "THOR-M": "THOR", "THOR100": "THOR", "THOR11": "THOR", "THOR16": "THOR",
    "THOR22": "THOR", "THOR25X4": "THOR", "THOR4": "THOR", "THOR5": "THOR",
    "THOR50X1": "THOR", "THOR50X2": "THOR", "THOR8": "THOR",
    # THRB (7)
    "THRBX": "THRB", "THRBX1": "THRB", "THRBX2": "THRB", "THRBX4": "THRB",
    "THROB1": "THRB", "THROB2": "THRB", "THROB4": "THRB",
    # TOR (4)
    "AMTORFEC": "TOR", "GTOR": "TOR", "NAVTEX": "TOR", "SITORB": "TOR",
}

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
class AdifParseError(ValueError):
    """Raised when the input cannot be recognised as ADIF data."""


# <NAME:length[:datatype]> value...
_FIELD_START_RE = re.compile(r"<\s*([A-Za-z_][A-Za-z0-9_\-\.]*)\s*(?::\s*(\d+)\s*)?(?::\s*([A-Za-z])\s*)?>")
# Tolerates the malformed spellings some tools emit: "</EOR>", "<EOR/>", "<EOR />".
_END_TAG_RE = re.compile(r"<\s*/?\s*(EOR|EOH|EOD)\s*/?\s*>", re.IGNORECASE)


def _read_text(path: str) -> str:
    """Read an ADIF file, tolerating BOMs and unknown encodings.

    ADIF is defined as ASCII/UTF-8.  Some Windows loggers emit CP1252 or a
    UTF-16 BOM; those are handled rather than crashing.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    if not raw:
        return ""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# A tag whose content is not a legal ADIF field name cannot open a field.
_VALID_TAG_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")
# Markup such as "<html>", "<!DOCTYPE ...>" or "<?xml ...>".  A '<' inside a
# headerless file is legal ADIF, but this shape means the payload is an error
# page or HTML document rather than a log -- LoTW returns HTML on failure.
_MARKUP_TAG_RE = re.compile(r"<!--|<!|[?/]")
# Comment terminator, also used to step over an unterminated comment.
_COMMENT_END_RE = re.compile(r"--\s*>")


def iter_records(
    text: str, unknown_tags: Optional[List[str]] = None
) -> Iterator[Dict[str, str]]:
    """Yield one dict per ADIF record (QSO).

    Yields header records and QSO records alike; the caller sorts them out.
    Values are deduplicated by keeping the *last* occurrence of a repeated
    field name, which matches how logging programs emit superseding values.

    A value is always located by the character length declared in its data
    specifier, so it may legitimately contain '<', '>', newlines and the
    literal text ``<EOR>``.  Non-ADIF text between records -- whitespace, a
    saved-by banner, an XML comment, a stray tag -- is skipped rather than
    treated as data, and is never allowed to end the file early.  Only real
    markup stops the scan, because that means the payload is an HTML error
    page rather than a log.

    The ADIF header is marked off by ``<EOH>``, but producers omit that tag, so
    a record is classed as header by content as well as position: the header is
    whatever precedes the ``<EOH>`` tag and carries no QSO field.  The first
    record holding a QSO field ends header mode, which means a headerless file
    is handled correctly whether or not it starts with '<', and whether or not
    it carries a banner.

    ``unknown_tags``, when supplied, collects the names of tags that were not
    valid ADIF data specifiers, so the caller can report them.
    """
    record: Dict[str, str] = {}
    pos = 0
    size = len(text)
    in_header = True   # still inside the header?  A header precedes <EOH>.

    while pos < size:
        if text[pos] != "<":
            nxt = text.find("<", pos + 1)
            if nxt == -1:
                break
            pos = nxt
            continue

        if text.startswith("<!--", pos):
            # A comment may sit between records; ignore it and its contents.
            end = _COMMENT_END_RE.search(text, pos + 4)
            if end is None:
                break
            pos = end.end()
            continue

        # The structural tags are checked before the markup test, because a
        # closing form such as "</EOR>" starts with the same '/' that marks
        # markup.  Testing markup first would end the file at the first record.
        end_tag = _END_TAG_RE.match(text, pos)
        if end_tag is not None:
            if record:
                # Classify by content, not position alone.  A header record
                # holds no QSO field, so LoTW's PROGRAMID + APP_LOTW_LASTQSL +
                # APP_LOTW_NUMREC block is a header even though those last two
                # are legal QSO field names -- and a record carrying CALL is a
                # QSO even if <EOH> was never written.
                if in_header and not (set(record) & QSO_FIELDS):
                    record[HEADER_MARKER] = "1"
                else:
                    in_header = False
                yield record
                record = {}
            if end_tag.group(1).upper() == "EOH":
                in_header = False
            pos = end_tag.end()
            continue

        if _MARKUP_TAG_RE.match(text, pos + 1):
            close = text.find(">", pos + 1)
            if close == -1:
                break
            if in_header:
                # Prologue before the data, e.g. "<?xml ...?>" or a DOCTYPE.
                pos = close + 1
                continue
            # Markup after real data means the payload is an HTML error page
            # (LoTW returns one when a query fails), not a log.
            break

        match = _FIELD_START_RE.match(text, pos)
        if match is None or match.group(2) is None:
            # Not a data specifier: a bare tag such as "<zzz>", a malformed
            # "<EOR/>", or stray text.  Step over it and keep reading; ending
            # the scan here would silently discard every later record.
            close = text.find(">", pos + 1)
            if close == -1:
                break
            if unknown_tags is not None:
                tag = text[pos + 1:close].strip()
                name = tag.split(":", 1)[0].strip().upper()
                # A bare trailer such as LoTW's APP_LOTW_EOF is documented as
                # "not followed by <EOR>", so it is a known field name and must
                # not be reported as an unrecognised tag.
                if _VALID_TAG_NAME_RE.match(tag.split(":", 1)[0].strip()) \
                        and name not in KNOWN_FIELDS:
                    unknown_tags.append(tag.upper())
            pos = close + 1
            continue

        declared = int(match.group(2))
        start = match.end()
        stop = start + declared
        if stop <= size:
            value = text[start:stop]
            pos = stop
        else:
            # Declared length runs past EOF: take what remains.
            value = text[start:]
            pos = size

        # Strip only ASCII whitespace that some exporters pad around values.
        record[match.group(1).upper()] = value.strip(" \t\r\n")

    if record:
        # A trailing record with no <EOR> is still a record.
        if in_header and not (set(record) & QSO_FIELDS):
            record[HEADER_MARKER] = "1"
        yield record


class ParseResult(NamedTuple):
    """Result of parsing one ADIF file.

    Unpacks as ``(records, header, unknown_tags)`` and exposes the same three
    names as attributes.
    """

    records: List[Dict[str, str]]
    header: Dict[str, str]
    unknown_tags: List[str]


def parse_adif(path: str) -> ParseResult:
    """Parse one ADIF file.

    Returns a :class:`ParseResult` holding the QSO records, the header fields
    and any unrecognised tags that were skipped.  Header fields such as
    ADIF_VER and PROGRAMID are kept out of the QSO records.

    Raises AdifParseError when the file holds no recognisable ADIF records, so a
    stray non-ADIF file is reported instead of silently producing a bogus row.
    """
    text = _read_text(path)
    if "<" not in text:
        raise AdifParseError(f"{path}: no ADIF fields found")

    header: Dict[str, str] = {}
    records: List[Dict[str, str]] = []
    unknown: List[str] = []

    for rec in iter_records(text, unknown):
        is_header = rec.pop(HEADER_MARKER, None) is not None
        data = {k: v for k, v in rec.items() if k not in STRUCTURAL_FIELDS}
        if not data:
            continue
        names = set(data)
        # Header content, and never a QSO:
        #   * a record before <EOH> -- LoTW's header carries PROGRAMID plus
        #     APP_LOTW_LASTQSL/APP_LOTW_NUMREC, which are also legal QSO fields,
        #     so position is the only reliable signal; and
        #   * a record whose fields are all header fields, wherever it appears,
        #     so a repeated header does not become a blank QSO row.
        if is_header or names <= HEADER_FIELDS:
            for key, val in data.items():
                if key not in KNOWN_FIELDS or key in HEADER_FIELDS:
                    header.setdefault(key, val)
            continue
        if names & KNOWN_FIELDS:
            records.append(data)

    if not records:
        raise AdifParseError(
            f"{path}: no ADIF QSO records found (is this really an ADIF file?)"
        )
    return ParseResult(records, header, unknown)


# ---------------------------------------------------------------------------
# Field conversion
# ---------------------------------------------------------------------------
_DATE_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_TIME_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})?$")


def parse_adif_date(value: str) -> Optional[_dt.date]:
    """YYYYMMDD -> datetime.date. Returns None when unparseable."""
    if not value:
        return None
    m = _DATE_RE.match(value.strip())
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_adif_time(value: str) -> Optional[_dt.time]:
    """HHMM or HHMMSS -> datetime.time (UTC). Returns None when unparseable."""
    if not value:
        return None
    m = _TIME_RE.match(value.strip())
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    second = int(m.group(3)) if m.group(3) else 0
    if hour > 23 or minute > 59 or second > 60:
        return None
    if second == 60:  # leap second: Excel cannot store it
        second = 59
    try:
        return _dt.time(hour, minute, second)
    except ValueError:
        return None


def parse_freq(value: str) -> Optional[float]:
    """FREQ in MHz -> float."""
    if not value:
        return None
    try:
        freq = float(value.strip())
    except (TypeError, ValueError):
        return None
    if freq <= 0 or not math.isfinite(freq):
        return None
    return freq


# ---------------------------------------------------------------------------
# Conversion of parsed ADIF records into Excel rows
# ---------------------------------------------------------------------------
class ConversionResult:
    """Holds the converted rows plus the column layout that was chosen."""

    def __init__(self) -> None:
        self.rows: List[Dict[str, object]] = []
        self.columns: List[str] = []
        self.sources: "OrderedDict[str, int]" = OrderedDict()
        self.headers: "OrderedDict[str, str]" = OrderedDict()
        self.total_records = 0
        self.incomplete: List[Tuple[int, str, List[str]]] = []
        #: Every column the source data could produce, including the ones that
        #: turned out to be empty everywhere.  The interface needs this to offer
        #: a field that this particular export happens not to use.
        self.available: List[str] = []


def build_rows(
    parsed: Sequence[Tuple[str, List[Dict[str, str]], Dict[str, str], List[str]]],
    selected_columns: Optional[Iterable[str]] = None,
) -> ConversionResult:
    """Turn parsed ADIF records into normalised row dictionaries.

    ``selected_columns`` limits the workbook to the named columns (the required
    set is always included); ``None`` keeps every column that holds data.
    """
    result = ConversionResult()
    seen_labels: Dict[str, int] = {}
    for path, records, header, _unknown in parsed:
        label = os.path.basename(path)
        # Two folders can hold same-named logs; keep the labels distinguishable.
        if label in seen_labels:
            seen_labels[label] += 1
            stem, ext = os.path.splitext(label)
            label = f"{stem} ({seen_labels[label]}){ext}"
        else:
            seen_labels[label] = 1
        result.sources[label] = result.sources.get(label, 0) + len(records)
        for key, val in header.items():
            result.headers.setdefault(key, val)

        # Which of the desired columns this file exports at all.  A column the
        # producer never emits is not a defect -- LoTW and QRZ Logbook export no
        # RST report, and Club Log and TQSL omit STATION_CALLSIGN -- so only a
        # field the file DOES carry is reported when it fails to convert.
        exported = set()
        for rec in records:
            for column, adif_name in REQUIRED_COLUMNS.items():
                if adif_name in rec and str(rec[adif_name]).strip():
                    exported.add(column)

        # Row dictionaries carry the mapped columns (a key that stayed empty)
        # plus every optional field seen, so their keys are what this file can
        # produce.  The union is collected below, once every file is read.
        # The well-known optional columns are included here as well, so the
        # interface offers them even for a log that happens to omit them; they
        # are still dropped from the workbook when nothing carries a value.
        result.available.extend(
            column for column, adif_name
            in list(REQUIRED_COLUMNS.items()) + list(OPTIONAL_WELL_KNOWN.items())
            if any(adif_name in rec or column in rec for rec in records))
        for rec in records:
            for name in rec:
                if name == HEADER_MARKER or name in STRUCTURAL_FIELDS:
                    continue
                if name not in REQUIRED_COLUMNS.values() \
                        and name not in OPTIONAL_WELL_KNOWN.values():
                    result.available.append(name)

        for rec in records:
            row: Dict[str, object] = {}

            raw_date = rec.get("QSO_DATE", "")
            raw_time = rec.get("TIME_ON", "")
            raw_date_off = rec.get("QSO_DATE_OFF", "")
            raw_time_off = rec.get("TIME_OFF", "")

            row["CALL"] = rec.get("CALL", "").upper()
            row["QSO_DATE"] = parse_adif_date(raw_date)
            row["TIME_ON_UTC"] = parse_adif_time(raw_time)
            row["TIME_OFF_UTC"] = parse_adif_time(raw_time_off)
            row["QSO_DATE_OFF"] = parse_adif_date(raw_date_off)
            row["RST_SENT"] = rec.get("RST_SENT", "")
            row["RST_RCVD"] = rec.get("RST_RCVD", "")
            row["STATION_CALLSIGN"] = rec.get("STATION_CALLSIGN", "").upper()
            row[SOURCE_COLUMN] = label

            # -- DXCC entity -------------------------------------------------
            # AUTHORITATIVE if the log already says so via DXCC or COUNTRY,
            # otherwise derived from the callsign prefix.  DXCC_SOURCE records
            # which rule applied, so a derived entity is never mistaken for one
            # the log actually exported.
            entity, _entity_code, entity_source = dxcc.resolve(
                call=row["CALL"],
                dxcc_field=rec.get("DXCC", ""),
                country=rec.get("COUNTRY", ""),
            )
            row[ENTITY_COLUMN] = entity if entity != dxcc.UNKNOWN else ""
            row[ENTITY_SOURCE_COLUMN] = (
                entity_source if entity != dxcc.UNKNOWN else ""
            )

            # -- QSL postage to that entity ----------------------------------
            # Derived from the entity, so it is only meaningful once the entity
            # is known.  A price is never invented: an unmapped destination
            # leaves the cell empty.  The main column is numeric so it sorts and
            # sums; the detail column carries the per-service breakdown.
            if entity and entity != dxcc.UNKNOWN:
                try:
                    quote = postage.quote(entity)
                except postage.NotMailable as exc:
                    row[POSTAGE_COLUMN] = "不通邮"
                    row[POSTAGE_DETAIL_COLUMN] = str(exc)
                else:
                    if quote.zone == postage.DOMESTIC:
                        # Mailing inside mainland China has no air/surface
                        # choice: the rate depends only on 本埠 or 外埠.
                        row[POSTAGE_COLUMN] = quote.cost(postage.DOMESTIC)
                    else:
                        air = quote.cost("AIR")
                        if air is not None:
                            row[POSTAGE_COLUMN] = air
                    row[POSTAGE_DETAIL_COLUMN] = quote.detail

            # -- frequency / band -------------------------------------------
            freq = parse_freq(rec.get("FREQ", ""))
            if freq is None:
                freq = parse_freq(rec.get("FREQ_RX", ""))
            row["FREQ_MHZ"] = freq
            band = (rec.get("BAND", "") or "").upper().strip()
            if not band:
                band = band_from_freq(freq) or ""
            row["BAND"] = band

            # -- mode / submode ---------------------------------------------
            mode = (rec.get("MODE", "") or "").upper().strip()
            submode = (rec.get("SUBMODE", "") or "").upper().strip()
            if not mode and submode:
                mode = SUBMODE_TO_MODE.get(submode, submode)
            row["MODE"] = mode
            row["SUBMODE"] = submode

            # -- all remaining ADIF fields, discovered automatically --------
            for key, val in rec.items():
                if not val:
                    continue
                if key in HEADER_FIELDS:
                    continue
                column = _column_for_adif_field(key)
                if column in REQUIRED_COLUMNS and key == REQUIRED_COLUMNS[column]:
                    continue  # already handled above
                if column in row and row[column] not in ("", None):
                    continue  # first writer wins for a mapped column
                row[column] = val

            # -- completeness check on the mandatory set -------------------
            # Only report a field the source file actually exports.
            missing = [
                col
                for col in ("CALL", "QSO_DATE", "TIME_ON_UTC", "MODE", "RST_SENT",
                            "RST_RCVD", "STATION_CALLSIGN")
                if col in exported and row.get(col) in (None, "")
            ]
            if ("FREQ_MHZ" in exported or "BAND" in exported) \
                    and row.get("FREQ_MHZ") is None and not row.get("BAND"):
                missing.append("FREQ_MHZ/BAND")
            result.total_records += 1
            if missing:
                result.incomplete.append((result.total_records, row["CALL"], missing))

            result.rows.append(row)

    _apply_datatypes(result.rows)
    # Every field the source data could yield, in a stable order: the mapped
    # columns first, then whatever the logs carried.  The field picker and
    # --columns both work from this, so a column this export leaves blank can
    # still be asked for.
    available: List[str] = []
    for column in list(REQUIRED_COLUMNS) + result.available:
        if column and column not in available:
            available.append(column)
    for derived in (ENTITY_COLUMN, ENTITY_SOURCE_COLUMN, POSTAGE_COLUMN,
                    POSTAGE_DETAIL_COLUMN, SOURCE_COLUMN):
        if derived not in available:
            available.append(derived)
    result.available = available
    result.columns = _choose_columns(result.rows, selected_columns,
                                     result.available)
    _report_entity_coverage(result)
    return result


def _entity_columns_needed(rows: Sequence[Dict[str, object]]) -> bool:
    """True unless every record already carried both DXCC and COUNTRY."""
    if not rows:
        return False
    return not all(row.get("DXCC") and row.get("COUNTRY") for row in rows)


def _report_entity_coverage(result: "ConversionResult") -> None:
    """Count how each DXCC entity was resolved, for the Summary sheet."""
    counts: "OrderedDict[str, int]" = OrderedDict()
    unknown = 0
    for row in result.rows:
        source = str(row.get(ENTITY_SOURCE_COLUMN) or "")
        if source in ("ADIF_DXCC", "ADIF_COUNTRY", "PREFIX"):
            counts[source] = counts.get(source, 0) + 1
        else:
            unknown += 1
    result.entity_sources = counts
    result.entity_unknown = unknown


# ADIF field names that carry a date or a time, used to promote auto-detected
# optional columns to real Excel date/time cells.
_DATE_FIELD_RE = re.compile(r"(?:^|_)DATE(?:_|$)|DATE$")
_TIME_FIELD_RE = re.compile(r"(?:^|_)TIME(?:_|$)|_TIME$")
_DATE_TIME_SUFFIX_RE = re.compile(r"(?:^|_)TIME(?:_|$)")


def _apply_datatypes(rows: Sequence[Dict[str, object]]) -> None:
    """Promote date/time-looking optional columns to real Excel types.

    A column is only converted when *every* non-empty value parses, so a field
    holding free text is never silently turned into something else.
    """
    if not rows:
        return
    candidates = {
        key
        for row in rows
        for key in row
        if isinstance(row.get(key), str) and key not in ("CALL", "STATION_CALLSIGN")
        and (_DATE_FIELD_RE.search(key) or _DATE_TIME_SUFFIX_RE.search(key))
    }
    for key in sorted(candidates):
        values = [row.get(key) for row in rows]
        present = [v for v in values if isinstance(v, str) and v]
        if not present:
            continue
        if _DATE_TIME_SUFFIX_RE.search(key):
            parsed = [parse_adif_time(v) for v in present]
            if all(p is not None for p in parsed):
                for row in rows:
                    v = row.get(key)
                    if isinstance(v, str) and v:
                        row[key] = parse_adif_time(v)
        elif _DATE_FIELD_RE.search(key):
            parsed = [parse_adif_date(v) for v in present]
            if all(p is not None for p in parsed):
                for row in rows:
                    v = row.get(key)
                    if isinstance(v, str) and v:
                        row[key] = parse_adif_date(v)


def _column_for_adif_field(field: str) -> str:
    """Map an ADIF field name to an Excel column name (upper case)."""
    aliases = {
        "TIME_ON": "TIME_ON_UTC",
        "TIME_OFF": "TIME_OFF_UTC",
        "FREQ": "FREQ_MHZ",
    }
    return aliases.get(field, field)


def _choose_columns(
    rows: Sequence[Dict[str, object]],
    selected: Optional[Iterable[str]] = None,
    available: Optional[Iterable[str]] = None,
) -> List[str]:
    """Decide the output column set and order.

    * Required columns first, in their documented order.
    * Then every other field actually present, in first-seen order.
    * A column is dropped when it is empty in *every* record, unless it is in
      ALWAYS_KEEP.

    ``selected`` restricts the result to a caller-chosen set of columns, which is
    what the interface and ``--columns`` use.  The required columns are added to
    any selection: a workbook missing the callsign column would not be a log.

    ``available`` names every column the source data could produce, including
    ones that are empty in every record.  A requested column is written as long
    as it appears there, so asking for a field yields the column instead of a
    silent omission.
    """
    seen: List[str] = []
    for row in rows:
        for key in row:
            if key not in seen:
                seen.append(key)

    ordered: List[str] = [c for c in REQUIRED_COLUMNS if c in seen]
    ordered += [c for c in seen if c not in REQUIRED_COLUMNS and c != SOURCE_COLUMN]
    ordered.append(SOURCE_COLUMN)

    def non_empty(column: str) -> bool:
        for row in rows:
            value = row.get(column)
            if value is not None and value != "":
                return True
        return False

    kept = [c for c in ordered if c in ALWAYS_KEEP or non_empty(c)]

    if selected is not None:
        wanted = set(selected)
        # ALWAYS_KEEP is unconditional: the callsign, the date and the source
        # file are what make the sheet a usable log, so a selection can narrow
        # the optional fields but never remove these.
        keep = {c for c in ordered if c in ALWAYS_KEEP}
        keep |= {c for c in wanted if c in ordered}
        # A requested column that this export happens to leave blank still gets
        # its column: the user asked for it, and an empty column is more honest
        # than a silently missing one.  Only names the tool knows are honoured,
        # so a typo cannot invent a column out of nothing.
        known = set(available) if available is not None else set()
        extra = sorted(
            c for c in wanted
            if c not in keep and c != SOURCE_COLUMN
            and (c in known or c in FIELD_LABELS_ZH or c in DERIVED_COLUMNS
                 or c in REQUIRED_COLUMNS))
        kept = [c for c in ordered if c in keep] + extra

    return kept


# ---------------------------------------------------------------------------
# Excel output
# ---------------------------------------------------------------------------
_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_SUBHEADER_FILL = PatternFill("solid", fgColor="DCE6F1")
_SUBHEADER_FONT = Font(bold=True, color="1F4E78", size=9)
_TITLE_FONT = Font(bold=True, size=12, color="1F4E78")
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_DATE_FORMAT = "yyyy-mm-dd"
_TIME_FORMAT = "hh:mm:ss"
# Keeps up to 6 decimals for frequencies but does not pad a logged 14.263 MHz
# out to "14.263000".
_FREQ_FORMAT = "0.000###"

# ---------------------------------------------------------------------------
# Excel cell hygiene.
#
# ADIF forbids control characters, but real exports carry them: a corrupt byte
# survives the latin-1 fallback in _read_text(), and DXLab documents that such
# a byte "can prematurely terminate the import process".  openpyxl refuses to
# write them at all, which would abort the entire export, so they are dropped
# from the cell text instead.  Excel also caps a cell at 32,767 characters.
# ---------------------------------------------------------------------------
EXCEL_MAX_CELL_CHARS = 32767
_EXCEL_ILLEGAL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRUNCATION_MARKER = " ... [truncated]"
# A leading '=' is the only character that makes openpyxl write a formula
# element.  '+' and '-' deliberately are NOT treated as dangerous: weak-signal
# reports such as -10, +12 and -05 are ordinary logged values, and openpyxl
# stores them as plain text, so altering them would corrupt RST_SENT for every
# FT8/FT4/WSPR contact.
_FORMULA_PREFIX = "="


def sanitize_cell(value):
    """Return a value that is safe to store in an Excel cell.

    Numbers, dates and times pass through untouched so they stay sortable and
    numerically correct.  Text has illegal control characters removed and is
    capped at Excel's cell limit.  Text beginning with '=' -- the only shape
    openpyxl turns into an evaluable formula -- is defused, because log content
    is untrusted and a downloaded log could otherwise run as a formula.
    """
    if not isinstance(value, str):
        return value
    text = value
    changed = False

    if len(text) > EXCEL_MAX_CELL_CHARS:
        keep = EXCEL_MAX_CELL_CHARS - len(_TRUNCATION_MARKER)
        text = text[:keep] + _TRUNCATION_MARKER
        changed = True

    cleaned = _EXCEL_ILLEGAL_RE.sub("", text)
    if cleaned != text:
        text = cleaned
        changed = True

    if text[:1] == _FORMULA_PREFIX:
        # Without this, openpyxl would write a formula element and Excel would
        # evaluate attacker-controlled log text as a formula on open.
        text = "'" + text
        changed = True

    return text if changed else value


def sanitize_columns(columns: Iterable[str]) -> List[str]:
    """Apply :func:`sanitize_cell` to column headings."""
    return [str(sanitize_cell(name)) for name in columns]


def _write_header(sheet, columns: Sequence[str], row_index: int = 1) -> None:
    for idx, name in enumerate(columns, start=1):
        cell = sheet.cell(row=row_index, column=idx, value=name)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _BORDER


def _display_width(text: str) -> int:
    """Approximate rendered width, counting CJK characters as two columns.

    len() is wrong for Chinese: 对方呼号 is 4 characters but occupies about 8
    Excel columns, so a header sized by len() gets clipped.
    """
    return sum(2 if "\u1100" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef"
               else 1 for ch in text)


def _autosize(sheet, columns: Sequence[str], sample_rows: int = 300,
              header_rows: int = 1, headers: Optional[Sequence[str]] = None
              ) -> None:
    """Set sensible column widths from the data already written."""
    widths = {name: _display_width(name) for name in columns}
    if headers is not None:
        for name, header in zip(columns, headers, strict=False):
            widths[name] = max(widths[name], _display_width(header or ""))
    checked = 0
    for row in sheet.iter_rows(min_row=header_rows + 1):
        if checked >= sample_rows:
            break
        checked += 1
        # strict=False: a row may be shorter than the column list when the
        # trailing columns of a record are all empty.
        for cell, name in zip(row, columns, strict=False):
            value = cell.value
            if value is None:
                continue
            if isinstance(value, _dt.datetime):
                text = value.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, _dt.date):
                text = value.strftime("%Y-%m-%d")
            elif isinstance(value, _dt.time):
                text = value.strftime("%H:%M:%S")
            else:
                text = str(value)
            width = _display_width(text)
            if width > widths[name]:
                widths[name] = width
    for idx, name in enumerate(columns, start=1):
        # Clamp: keep wide comment-like columns readable but bounded.
        sheet.column_dimensions[get_column_letter(idx)].width = min(
            max(widths[name] + 2, 8), 48
        )


def write_qso_sheet(
    workbook: Workbook,
    result: ConversionResult,
) -> None:
    """Write the main 'QSOs' sheet with typed, formatted cells."""
    sheet = workbook.create_sheet("QSOs")
    columns = result.columns
    _write_header(sheet, columns)

    # Chinese header beside each English one.  The English name stays because it
    # is the documented interface, and a separate row keeps it intact for
    # formulas and the autofilter.
    labels: List[str] = []
    for idx, name in enumerate(columns, start=1):
        label = column_header_label(name)
        labels.append(label)
        cell = sheet.cell(row=2, column=idx, value=label)
        cell.fill = _SUBHEADER_FILL
        cell.font = _SUBHEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = _BORDER

    for r, row in enumerate(result.rows, start=3):
        for c, name in enumerate(columns, start=1):
            value = row.get(name)
            if value is None or value == "":
                continue
            cell = sheet.cell(row=r, column=c, value=sanitize_cell(value))
            # Format by the value's real type, so both the mandatory columns and
            # any auto-detected date/time column render as Excel date or time.
            if isinstance(value, _dt.datetime):
                cell.number_format = f"{_DATE_FORMAT} {_TIME_FORMAT}"
            elif isinstance(value, _dt.date):
                cell.number_format = _DATE_FORMAT
                cell.alignment = Alignment(horizontal="left")
            elif isinstance(value, _dt.time):
                cell.number_format = _TIME_FORMAT
                cell.alignment = Alignment(horizontal="left")
            elif name == "FREQ_MHZ" or name.endswith("_MHZ"):
                cell.number_format = _FREQ_FORMAT

    # Freeze below both header rows so the names stay visible while scrolling.
    sheet.freeze_panes = "A3"
    if result.rows:
        sheet.auto_filter.ref = (
            f"A1:{get_column_letter(len(columns))}{len(result.rows) + 2}"
        )
    _autosize(sheet, columns, header_rows=2, headers=labels)


def write_summary_sheet(
    workbook: Workbook,
    result: ConversionResult,
    adif_headers: Dict[str, str],
) -> None:
    """Write the 'Summary' sheet: BAND / MODE / CALL breakdown counts."""
    sheet = workbook.create_sheet("Summary")

    def count_by(field: str) -> "OrderedDict[str, int]":
        counts: "OrderedDict[str, int]" = OrderedDict()
        for row in result.rows:
            value = row.get(field)
            if value is None or value == "":
                key = "(none)"
            elif isinstance(value, (float, int)):
                key = f"{value:g}"
            else:
                key = str(value)
            key = str(sanitize_cell(key))
            counts[key] = counts.get(key, 0) + 1
        return OrderedDict(
            sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        )

    row = 1
    # The data-source / blank-cell explanation goes FIRST, because the question it
    # answers ("why is this empty?") is asked while looking at the QSOs sheet, and
    # the old placement -- just above the per-column fill table -- was two screens
    # down in a 100+ row Summary, where nobody found it.  The fill table stays at
    # the bottom as the evidence for it.
    note = sheet.cell(
        row=row, column=1,
        value="数据来源与空单元格说明：本表数据全部来自源 ADI 文件，"
              "按 ADIF 字段名映射后原样写出，时间一律为 UTC、不做时区换算；"
              "标 [自动生成] 的几列由本工具计算得出，不是源文件内容。"
              "单元格为空表示源 ADI 中没有相应数据 —— "
              "多数导出软件本身就不提供某些字段（例：LoTW、QRZ Logbook 不导出 RST，"
              "Club Log、TQSL 不导出 STATION_CALLSIGN），"
              "所以空单元格、乃至整列为空，都不代表转换出错。"
              "本表最下方「各列填充情况」逐列列出实际填充数，供对照。")
    note.font = Font(size=9, color="595959")
    note.alignment = Alignment(wrap_text=True, vertical="top")
    # The note spans columns A-D (its neighbours stay empty), and wrapping needs
    # an explicit height or Excel clips the later lines away.
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    sheet.row_dimensions[row].height = 58
    row += 2

    title = sheet.cell(row=row, column=1,
                       value="ADIF 转 Excel —— 汇总表（所有时间为 UTC，未做时区换算）")
    title.font = _TITLE_FONT
    row += 2

    blocks = (
        ("按波段统计 (QSOs by BAND)", "BAND"),
        ("按模式统计 (QSOs by MODE)", "MODE"),
        ("通联最多的呼号 (QSOs by CALL, top 50)", "CALL"),
    )
    for heading, field in blocks:
        head = sheet.cell(row=row, column=1, value=heading)
        head.font = Font(bold=True, size=11)
        row += 1
        _write_header(sheet, [field, field_label(field)], row_index=row)
        row += 1
        counts = count_by(field)
        items = list(counts.items())
        if field == "CALL":
            items = items[:50]
        if not items:
            sheet.cell(row=row, column=1, value="(没有记录)")
            row += 1
        for key, count in items:
            sheet.cell(row=row, column=1,
                       value=sanitize_cell(key)).border = _BORDER
            count_cell = sheet.cell(row=row, column=2, value=count)
            count_cell.border = _BORDER
            count_cell.alignment = Alignment(horizontal="right")
            row += 1
        row += 1

    # -- totals and source provenance ---------------------------------------
    head = sheet.cell(row=row, column=1, value="总览 (Overview)")
    head.font = Font(bold=True, size=11)
    row += 1
    _write_header(sheet, ["METRIC", "指标"], row_index=row)
    row += 1
    overview: List[Tuple[str, object]] = [
        ("Total QSOs", result.total_records),
        ("Distinct callsigns", len(count_by("CALL"))),
        ("Distinct bands", len({r.get("BAND") for r in result.rows if r.get("BAND")})),
        ("Distinct modes", len({r.get("MODE") for r in result.rows if r.get("MODE")})),
        ("First QSO date (UTC)", min(
            (r["QSO_DATE"] for r in result.rows if r.get("QSO_DATE")), default=""
        ) or ""),
        ("Last QSO date (UTC)", max(
            (r["QSO_DATE"] for r in result.rows if r.get("QSO_DATE")), default=""
        ) or ""),
        ("Time zone handling", "UTC as logged -- no conversion applied"),
        ("ADIF version", adif_headers.get("ADIF_VER", "")),
        ("Source program", adif_headers.get("PROGRAMID", "")),
        ("Program version", adif_headers.get("PROGRAMVERSION", "")),
        # Postal prices must never appear without their provenance, because
        # tariffs change and a stale figure is worse than none.
        ("QSL postage basis", "China Post ordinary letter (平信), "
                             f"{postage.REFERENCE_WEIGHT_G} g, RMB"),
        ("QSL postage rates effective", postage.RATES_EFFECTIVE_FROM),
        ("QSL postage rates verified", postage.RATES_VERIFIED_ON),
        ("QSL postage domestic source", postage.SOURCES["domestic"]),
        ("QSL postage international source", postage.SOURCES["international"]),
        ("QSL postage services", " / ".join(
            f"{postage.SERVICE_LABELS[k]} {k}" for k in postage.SERVICES)),
    ]
    for label, value in overview:
        sheet.cell(row=row, column=1, value=label).border = _BORDER
        cell = sheet.cell(row=row, column=2, value=sanitize_cell(value))
        cell.border = _BORDER
        if isinstance(value, _dt.date):
            cell.number_format = _DATE_FORMAT
        row += 1
    row += 1

    head = sheet.cell(row=row, column=1, value="来源文件 (Source files)")
    head.font = Font(bold=True, size=11)
    row += 1
    _write_header(sheet, ["SOURCE_FILE", "QSO_COUNT"], row_index=row)
    row += 1
    for label, count in result.sources.items():
        sheet.cell(row=row, column=1,
                   value=sanitize_cell(label)).border = _BORDER
        sheet.cell(row=row, column=2, value=count).border = _BORDER
        row += 1
    row += 1

    # -- the evidence for the note at the top of this sheet ------------------
    # A log export does not carry every field: LoTW and QRZ Logbook write no RST
    # report and Club Log and TQSL omit STATION_CALLSIGN.  The explanation is
    # stated once, on row 1; this table quantifies it per column.
    head = sheet.cell(row=row, column=1,
                      value="各列填充情况 (column fill — 说明见本表第 1 行)")
    head.font = Font(bold=True, size=11)
    row += 1
    for idx, name in enumerate(("COLUMN", "中文名", "已填/总数", "比例"), start=1):
        cell = sheet.cell(row=row, column=idx, value=name)
        cell.fill = _SUBHEADER_FILL
        cell.font = _SUBHEADER_FONT
        cell.border = _BORDER
    row += 1
    total_rows = len(result.rows)
    for name in result.columns:
        filled = 0
        for data_row in result.rows:
            value = data_row.get(name)
            if value is not None and value != "":
                filled += 1
        sheet.cell(row=row, column=1,
                   value=sanitize_cell(name)).border = _BORDER
        sheet.cell(row=row, column=2,
                   value=field_label(name) if name in FIELD_LABELS_ZH else ""
                   ).border = _BORDER
        cell = sheet.cell(row=row, column=3,
                          value=f"{filled} / {total_rows}")
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="right")
        ratio = sheet.cell(
            row=row, column=4,
            value=(filled / total_rows if total_rows else 0))
        ratio.border = _BORDER
        ratio.number_format = "0%"
        if filled == 0:
            for col in (1, 2, 3, 4):
                sheet.cell(row=row, column=col).fill = PatternFill(
                    "solid", fgColor="FFF2CC")
        row += 1
    row += 1
    # The explanation is on row 1 of this sheet; this only points back at it and
    # explains the highlight.
    note = sheet.cell(
        row=row, column=1,
        value="说明：空单元格的含义见本表第 1 行「数据来源与空单元格说明」。"
              "本表标黄的行是在所有记录中都为空的列。")
    note.font = Font(italic=True, size=9, color="808080")
    row += 1

    sheet.column_dimensions["A"].width = 34
    sheet.column_dimensions["B"].width = 26
    sheet.column_dimensions["C"].width = 14
    sheet.column_dimensions["D"].width = 10


def convert_to_workbook(
    parsed: Sequence[Tuple[str, List[Dict[str, str]], Dict[str, str], List[str]]],
    out_path: str,
    selected_columns: Optional[Iterable[str]] = None,
) -> ConversionResult:
    """Build the workbook from parsed ADIF data and save it."""
    result = build_rows(parsed, selected_columns)

    if result.total_records == 0:
        raise AdifParseError("no QSO records found in the supplied ADIF data")
    if result.total_records > EXCEL_MAX_ROWS - 1:
        raise AdifParseError(
            f"{result.total_records} QSOs exceed the Excel row limit "
            f"({EXCEL_MAX_ROWS - 1}); split the input."
        )

    workbook = Workbook()
    workbook.remove(workbook.active)  # drop the default empty sheet
    write_qso_sheet(workbook, result)
    write_summary_sheet(workbook, result, dict(result.headers))
    _save_workbook(workbook, out_path)
    return result


# ---------------------------------------------------------------------------
# Input discovery / CLI
# ---------------------------------------------------------------------------
def discover_inputs(paths: Iterable[str], recursive: bool = False) -> List[str]:
    """Expand files and directories into a sorted list of ADIF files."""
    found: List[str] = []
    for raw in paths:
        path = os.path.abspath(os.path.expanduser(raw))
        if os.path.isdir(path):
            walker = os.walk(path) if recursive else [
                (path, [], os.listdir(path))
            ]
            for root, _dirs, files in walker:
                for name in files:
                    if name.lower().endswith(ADIF_EXTENSIONS):
                        found.append(os.path.join(root, name))
        elif os.path.isfile(path):
            found.append(path)
        else:
            raise FileNotFoundError(f"input not found: {raw}")
    # De-duplicate while preserving order.
    unique: List[str] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


DEFAULT_OUTPUT_NAME = "adif_export.xlsx"


def desktop_directory() -> str:
    """The user's Desktop folder, whatever Windows calls it.

    On a Chinese Windows the folder is 桌面, on a German one Schreibtisch, so
    the name is read from the registry rather than assumed.  Falls back to
    ``~/Desktop`` and then to the home folder.
    """
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            try:
                value, _kind = winreg.QueryValueEx(key, "Desktop")
            finally:
                winreg.CloseKey(key)
            value = os.path.expandvars(value)
            if value and os.path.isdir(value):
                return value
        except (ImportError, OSError):
            pass

    candidate = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.isdir(candidate):
        return candidate
    return os.path.expanduser("~")


def default_output_path() -> str:
    """Where the workbook goes when ``-o`` is not given: the Desktop."""
    return os.path.join(desktop_directory(), DEFAULT_OUTPUT_NAME)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adif2xlsx",
        description="Convert ADIF (.adi/.adif) logs to a structured Excel workbook.",
        epilog=(
            "All times are UTC; no timezone conversion is performed.  "
            f"Without -o the workbook is written to the Desktop as "
            f"{DEFAULT_OUTPUT_NAME}.  Example: adif2xlsx sample.adi"
        ),
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="ADIF files and/or folders containing .adi/.adif files",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(f"output .xlsx path (default: Desktop\\{DEFAULT_OUTPUT_NAME})"),
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="recurse into sub-folders when an input is a folder",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print errors",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="open the graphical interface (default when double-clicked)",
    )
    parser.add_argument(
        "--columns",
        metavar="NAME,NAME",
        help=("write only these columns, in addition to the required set. "
              "Use --list-fields to see the names; 'required' means the "
              "required columns only."),
    )
    parser.add_argument(
        "--list-fields",
        action="store_true",
        help="list the column names that --columns accepts, then exit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _save_workbook(workbook: Workbook, out_path: str) -> None:
    """Write the workbook to ``out_path`` via a temporary file.

    Two reasons this does not simply call ``workbook.save(out_path)``:

    * A failure part-way through would leave a half-written workbook where the
      user's previous file was.  Writing beside the target and renaming means
      the destination is either the old file or the complete new one.
    * openpyxl keeps a ZipFile open while saving.  If the destination is locked
      -- the everyday case of the report being open in Excel -- that ZipFile is
      finalised during interpreter shutdown and CPython prints an
      "Exception ignored in: ZipFile.__del__" traceback.  Writing to a free
      temporary path removes that failure mode entirely.
    """
    directory = os.path.dirname(out_path) or "."
    handle, temp_path = tempfile.mkstemp(
        dir=directory, prefix=".adif2xlsx-", suffix=".xlsx.tmp")
    os.close(handle)
    try:
        workbook.save(temp_path)
        os.replace(temp_path, out_path)
    except BaseException:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def parse_column_argument(text: Optional[str]) -> Optional[List[str]]:
    """Turn a ``--columns`` argument into a column list.

    Accepts comma- or space-separated names, case-insensitively.  The word
    ``required`` on its own means "the mandatory columns and nothing else".
    Returns None when the flag was not used, meaning "every column with data".
    """
    if text is None:
        return None
    names = [part.strip().upper() for part in re.split(r"[,;\s]+", text) if part.strip()]
    if not names:
        return None
    if names == ["REQUIRED"]:
        return []
    unknown = [n for n in names
               if n not in FIELD_LABELS_ZH and n not in REQUIRED_COLUMNS
               and n not in DERIVED_COLUMNS and n != SOURCE_COLUMN]
    if unknown:
        raise AdifParseError(
            "unknown column name(s): " + ", ".join(sorted(unknown))
            + " -- run with --list-fields to see the accepted names")
    return names


def print_field_list() -> None:
    """Print the field catalogue for --list-fields."""
    out = sys.stdout
    if out is None:  # a windowed build has nowhere to print
        return
    out.write("必选列 (always written):\n")
    for column in REQUIRED_COLUMNS:
        out.write(f"  {column:<22} {field_label(column)}\n")
    out.write("\n附加列 (optional):\n")
    written = set()
    extras = [c for c in FIELD_LABELS_ZH if c not in REQUIRED_COLUMNS]
    for column in sorted(extras):
        written.add(column)
        label = field_label(column)
        note = "  [自动生成]" if column in DERIVED_COLUMNS else ""
        out.write(f"  {column:<22} {label}{note}\n")
    if SOURCE_COLUMN not in written:
        out.write(f"  {SOURCE_COLUMN:<22} {field_label(SOURCE_COLUMN)}\n")
    out.write("\n用法: --columns CALL,QSO_DATE,GRIDSQUARE\n"
              "      --columns required      (只输出必选列)\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.list_fields:
        print_field_list()
        return 0

    if not args.inputs:
        # Previously enforced by argparse; now handled here so that --list-fields
        # can run without any input file.
        emit("ERROR: no input files given\n"
             "       usage: adif2xlsx <files or folders> [-o out.xlsx]\n")
        return 2

    try:
        selected_columns = parse_column_argument(args.columns)
    except AdifParseError as exc:
        emit(f"ERROR: {exc}\n")
        return 2

    try:
        inputs = discover_inputs(args.inputs, recursive=args.recursive)
    except FileNotFoundError as exc:
        emit(f"ERROR: {exc}\n")
        return 2
    if not inputs:
        emit("ERROR: no .adi/.adif files found in the given inputs\n")
        return 2

    parsed: List[Tuple[str, List[Dict[str, str]], Dict[str, str], List[str]]] = []
    failures = 0
    skipped_tags: "OrderedDict[str, int]" = OrderedDict()
    for path in inputs:
        try:
            records, header, unknown = parse_adif(path)
        except (AdifParseError, OSError) as exc:
            emit(f"WARNING: skipped {path}: {exc}\n")
            failures += 1
            continue
        for tag in unknown:
            skipped_tags[tag] = skipped_tags.get(tag, 0) + 1
        if not args.quiet:
            print(f"  read {os.path.basename(path)}: {len(records)} QSO(s)")
        parsed.append((path, records, header, unknown))

    if not parsed:
        emit("ERROR: no readable ADIF files\n")
        return 1

    out_path = os.path.abspath(os.path.expanduser(
        args.output if args.output else default_output_path()))
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as exc:
            emit(
                f"ERROR: cannot create the output folder {out_dir}: {exc}\n")
            return 2


    try:
        result = convert_to_workbook(parsed, out_path, selected_columns)
    except AdifParseError as exc:
        emit(f"ERROR: {exc}\n")
        return 1
    except OSError as exc:
        emit(
            f"ERROR: cannot write {out_path}: {exc}\n"
            f"       (if the file is open in Excel, close it and retry)\n")
        return 1

    if not args.quiet:
        print(f"\nWrote {out_path}")
        print(f"  QSOs      : {result.total_records}")
        print(f"  Columns   : {len(result.columns)} -> {', '.join(result.columns)}")
        print(f"  Source    : {len(result.sources)} file(s)")
        if result.incomplete:
            # Summarise by field: "RST_SENT x12" is actionable, a bare count is not.
            counts: "OrderedDict[str, int]" = OrderedDict()
            for _index, _call, fields in result.incomplete:
                for name in fields:
                    counts[name] = counts.get(name, 0) + 1
            summary = ", ".join(f"{name} x{n}" for name, n in
                                sorted(counts.items(), key=lambda kv: -kv[1]))
            print(f"  NOTE      : {len(result.incomplete)} record(s) left a column empty "
                  f"that the source file does populate: {summary}")
            print("              (a field the producer does not export at all is normal, "
                  "e.g. RST in LoTW exports)")

    if skipped_tags:
        # Never fail silently: say what was not understood.
        summary = ", ".join(f"{tag} x{n}" for tag, n in skipped_tags.items())
        emit(
            f"WARNING: ignored {sum(skipped_tags.values())} unrecognised tag(s) "
            f"that are not ADIF fields: {summary}\n"
        )

    # Non-zero when part of the requested input could not be converted.
    return 1 if failures else 0


#: Set on a process that was started only to open the window.  A UI build that
#: finds this already set must not start another copy: without the guard, a UI
#: build that cannot locate gui.py spawns itself forever.
SPAWN_MARKER = "ADIF2XLSX_UI_CHILD"


def _load_gui_module():
    """Import gui.py, or return None when it is not available.

    PyInstaller bundles gui.py because adif2xlsx does not import it statically,
    so the spec can be missing from an older or stripped build; that is checked
    rather than assumed.
    """
    gui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui.py")
    if os.path.isfile(gui_path):
        sys.path.insert(0, os.path.dirname(gui_path))
    elif importlib.util.find_spec("gui") is None:
        return None
    try:
        import gui as gui_module
    except ImportError:
        return None
    return gui_module


def launch_gui(extra: Optional[Sequence[str]] = None) -> int:
    """Start the desktop UI.

    gui.py is imported directly when reachable; in a frozen build PyInstaller
    also bundles it as an importable module, so the import normally succeeds
    either way.  Only if it does not do we re-run this executable once, guarded
    by ``SPAWN_MARKER`` against a spawn loop.
    """
    extra = list(extra or ())
    gui_module = _load_gui_module()
    if gui_module is not None:
        saved = sys.argv
        try:
            sys.argv = ["gui"] + extra
            return gui_module.main()
        finally:
            sys.argv = saved

    if os.environ.get(SPAWN_MARKER):
        # Already a window-only child and still no UI: give up loudly rather
        # than spawning copies without end.
        emit("ERROR: the interface module (gui.py) is missing from this build.\n")
        return 3
    if "--gui" in sys.argv[1:]:
        # Reached through the --gui marker, so spawning again would recurse.
        emit("ERROR: the interface module (gui.py) could not be loaded.\n")
        return 3

    import subprocess
    env = dict(os.environ, **{SPAWN_MARKER: "1"})
    return subprocess.run([sys.executable, "--gui", *extra],
                          check=False, env=env).returncode


def log_startup(argv: Sequence[str]) -> None:
    """Record how the program was started.

    A windowed build has no console, so when a user reports "it flashes and
    vanishes" this line is the only evidence of how it was launched.  Remove the
    noisy success case by writing only when something looks unusual, plus always
    on the GUI route where there is no other output at all.
    """
    try:
        write_log(f"[{_dt.datetime.now():%Y-%m-%d %H:%M:%S}] start argv={list(argv)!r} "
                  f"frozen={getattr(sys, 'frozen', False)} "
                  f"gui_in_argv={'--gui' in argv} "
                  f"console={sys.stdout is not None} v{__version__}")
    except Exception:  # noqa: BLE001 - diagnostics must never break startup
        pass


def entry(argv: Optional[Sequence[str]] = None) -> int:
    """Decide between the UI and the command line, then run the chosen one.

    The rule exists because of how people actually start the program:

    * double-clicked with no terminal (the packaged windowed build) -> open the UI
    * double-clicked with a terminal (the console build, "python adif2xlsx.py")
      -> print usage, because there is a console to read it in
    * explicit arguments, or --gui -> do exactly that

    The UI lives in gui.py.  In a frozen build that file sits inside the bundle
    next to this one, so it is imported directly; nothing here re-executes the
    program, which is what keeps a mis-set flag from spawning a storm of copies.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    log_startup(argv)

    # In a frozen build sys.argv[0] is the executable itself, so "--gui" is the
    # marker that says "you are the UI build being asked to open the window".
    if argv and argv[0] == "--gui":
        argv = argv[1:]
        if not argv:
            return launch_gui()
        # A child started by launch_gui() must run the UI for real now, never
        # dispatch again -- that is what would become an endless spawn loop.
        return launch_gui(argv)

    # Flags understood by gui.py rather than by the command-line parser.
    if argv and argv[0].startswith("--self-test"):
        return launch_gui(argv)

    if not argv:
        # Two signals that this build exists to show a window:
        #   * ADIF2XLSX_UI_BUILD, set by the runtime hook of the windowed build,
        #     which is reliable;
        #   * no console, the double-click case for a build without the hook.
        # The environment variable matters because a UI build started by a
        # parent that has a console inherits stdout and would otherwise fall
        # through to the command-line parser and show nothing.
        if os.environ.get("ADIF2XLSX_UI_BUILD") or sys.stdout is None:
            return launch_gui()
        build_arg_parser().print_help()
        return 2

    return main(argv)


if __name__ == "__main__":
    raise SystemExit(main_guard(entry))
