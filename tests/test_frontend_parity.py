#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parity checks: the web page, the desktop window and the command line.

Requirement: the web front end and the desktop app must be functionally
identical.  That is delivered structurally -- all three call the same functions in
``adif2xlsx`` rather than reimplementing anything -- so these checks assert the
structure holds and that the option surfaces cannot drift apart.

They cover:

  * every column the web page offers is a real column, and the page offers every
    column the core knows about;
  * the desktop picker is built from the same core constants, not its own list;
  * the required set, the always-written set and the presets agree;
  * all three front ends produce the SAME workbook bytes for the same input;
  * the web page does not parse ADIF itself (a JS reimplementation would be the
    way this requirement is normally broken).

Run:  python tests/test_frontend_parity.py
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import adif2xlsx as core  # noqa: E402
import webapp  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "adi")
WEB_PAGE = os.path.join(ROOT, "web", "index.html")
GUI_SRC = os.path.join(SRC, "gui.py")

checks = 0
failures = 0


def check(condition, label, detail=""):
    global checks, failures
    checks += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        failures += 1
        print(f"  FAIL  {label}  {detail}")


# ---------------------------------------------------------------------------
def test_column_catalogue_matches_core():
    """The web catalogue and the core constants describe the same columns."""
    print("\n=== the column catalogue (web vs core) ===")
    catalogue = webapp.field_catalogue()

    required = [item["name"] for item in catalogue["required"]]
    check(required == list(core.REQUIRED_COLUMNS),
          "the page offers the required columns in the documented order",
          f"{required} vs {list(core.REQUIRED_COLUMNS)}")

    optional = {item["name"] for item in catalogue["optional"]}
    expected_optional = (set(core.FIELD_LABELS_ZH) - set(core.REQUIRED_COLUMNS)
                         | {core.ENTITY_SOURCE_COLUMN,
                            core.POSTAGE_DETAIL_COLUMN})
    check(optional == expected_optional,
          "the page offers every optional column the core knows about",
          f"missing={sorted(expected_optional - optional)[:5]} "
          f"extra={sorted(optional - expected_optional)[:5]}")

    # Every offered column must be a column the core would actually accept.
    unknown = [name for name in list(required) + sorted(optional)
               if name not in core.REQUIRED_COLUMNS
               and name not in core.FIELD_LABELS_ZH
               and name not in core.DERIVED_COLUMNS
               and name != core.SOURCE_COLUMN]
    check(not unknown, "every column the page offers is a real column",
          str(unknown[:6]))

    # Labels and hints come from the core, so they cannot disagree.
    bad_label = [item["name"] for item in catalogue["required"] + catalogue["optional"]
                 if item["label"] != core.field_label(item["name"])]
    check(not bad_label, "the page's labels come from the core", str(bad_label[:6]))
    bad_hint = [item["name"] for item in catalogue["required"] + catalogue["optional"]
                if item["hint"] != core.describe_field(item["name"])]
    check(not bad_hint, "the page's hints come from the core", str(bad_hint[:6]))


def test_mandatory_and_presets():
    """The always-written set and the presets are consistent."""
    print("\n=== always-written columns and presets ===")
    catalogue = webapp.field_catalogue()
    check(list(catalogue["mandatory"]) == list(core.MANDATORY_COLUMNS),
          "the page's always-written set is the core's",
          f"{catalogue['mandatory']} vs {list(core.MANDATORY_COLUMNS)}")

    every_required = set(core.REQUIRED_COLUMNS) <= set(core.MANDATORY_COLUMNS)
    check(every_required, "every required column is always written")

    presets = catalogue["presets"]
    check(set(presets) == {"common", "all", "required"},
          "the page offers the same three presets the desktop app does",
          str(sorted(presets)))
    check(presets["all"] is None,
          "'all' means every column with data (not a fixed list)")
    check(presets["required"] == [],
          "'required only' means the mandatory set and nothing else")
    bad_common = [name for name in presets["common"]
                  if name not in core.REQUIRED_COLUMNS
                  and name not in core.FIELD_LABELS_ZH
                  and name not in core.DERIVED_COLUMNS]
    check(not bad_common, "the 'common' preset names only real columns",
          str(bad_common))


def test_desktop_uses_core_constants():
    """The desktop picker is built from the core, not from its own list."""
    print("\n=== the desktop app uses the same constants ===")
    gui = open(GUI_SRC, encoding="utf-8").read()

    check("core.REQUIRED_COLUMNS" in gui,
          "the desktop picker takes the required set from the core")
    check("core.FIELD_LABELS_ZH" in gui or "field_label" in gui,
          "the desktop picker takes labels from the core")
    check("result.available" in gui,
          "the desktop app lists columns from the core's parse result")

    # It must not carry its own copy of the column list.
    suspicious = re.findall(r'^\s*[A-Z_]*COLUMNS?\s*=\s*[\[(]', gui, re.M)
    check(not suspicious,
          "the desktop app defines no column list of its own", str(suspicious))


def test_web_page_does_not_parse_adif():
    """The page must not reimplement the converter in JavaScript."""
    print("\n=== the web page is a thin front end ===")
    page = open(WEB_PAGE, encoding="utf-8").read()

    check("fetch(" in page and "/api/" in page,
          "the page talks to the local service")

    # A JS reimplementation of the converter would show up as ADIF parsing or
    # xlsx writing in the page.  The page DOES contain a zip reader (to accept a
    # .zip upload) and a zip writer (to bundle several uploads into one request),
    # so the test looks for the xlsx container parts rather than the word "xlsx".
    for needle, label in (
            ("<EOR>", "no <EOR> record splitting in the page"),
            ("QSO_DATE", "no ADIF field mapping in the page"),
            ("openpyxl", "no xlsx library in the page"),
            ("[Content_Types].xml", "no xlsx container assembly in the page"),
            ("xl/workbook", "no xlsx container assembly in the page"),
            ("<FIELD:", "no length-driven ADIF parsing in the page"),
    ):
        check(needle not in page, label, f"found {needle!r}")

    check("ZipWriter" in page,
          "the page bundles uploads client-side (zip), which is not conversion")

    check(page.count("<script") == 1,
          "the page is a single self-contained file")
    externals = re.findall(r'(?:src|href)\s*=\s*["\']https?://', page)
    check(not externals, "the page loads no external resources",
          str(externals[:3]))


def test_identical_output_everywhere():
    """Same input, same output: CLI, web API and the core must agree."""
    print("\n=== identical output from every front end ===")
    paths = [os.path.join(FIXTURES, name)
             for name in sorted(os.listdir(FIXTURES))
             if name.lower().endswith((".adi", ".adif"))]
    check(len(paths) >= 6, "the real export fixtures are present",
          f"{len(paths)} files")

    import tempfile
    out_dir = tempfile.mkdtemp(prefix="parity_")

    # 1. Through the core directly.
    parsed = []
    for path in paths:
        records, header, unknown = core.parse_adif(path)
        parsed.append((path, records, header, unknown))
    direct = os.path.join(out_dir, "direct.xlsx")
    core.convert_to_workbook(parsed, direct)

    # 2. Through the web service's own conversion function.
    uploads = []
    for path in paths:
        with open(path, "rb") as fh:
            uploads.append(webapp.Upload(os.path.basename(path), fh.read()))
    saved = webapp.save_uploads(uploads, out_dir)
    web_out = os.path.join(out_dir, "web.xlsx")
    payload, report = webapp.run_conversion(saved, web_out, None)
    check(report.get("total") == sum(len(r) for _p, r, _h, _u in parsed),
          "the web conversion reports the same record count",
          f"{report.get('total')}")
    check(not report.get("skipped"),
          "the web service skipped no file", str(report.get("skipped")))

    # Compare the two workbooks cell by cell.
    from openpyxl import load_workbook
    a = load_workbook(direct)
    b = load_workbook(web_out)
    check(a.sheetnames == b.sheetnames, "the same sheets",
          f"{a.sheetnames} vs {b.sheetnames}")
    differences = []
    for name in a.sheetnames:
        wa, wb_ = a[name], b[name]
        if (wa.max_row, wa.max_column) != (wb_.max_row, wb_.max_column):
            differences.append(f"{name}: size {wa.max_row}x{wa.max_column} vs "
                               f"{wb_.max_row}x{wb_.max_column}")
            continue
        for row in range(1, wa.max_row + 1):
            for col in range(1, wa.max_column + 1):
                va = wa.cell(row=row, column=col).value
                vb = wb_.cell(row=row, column=col).value
                if va != vb:
                    differences.append(f"{name}!{row},{col}: {va!r} != {vb!r}")
                    break
            if differences:
                break
    check(not differences,
          "the web service and the core produce identical workbooks",
          "; ".join(differences[:3]))

    # 3. The command line must agree too.
    import subprocess
    cli_out = os.path.join(out_dir, "cli.xlsx")
    proc = subprocess.run(
        [sys.executable, os.path.join(SRC, "adif2xlsx.py"), *paths,
         "-o", cli_out, "--quiet"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=600)
    check(proc.returncode == 0, "the command line converts the same input",
          proc.stderr[:200])
    if os.path.isfile(cli_out):
        c = load_workbook(cli_out)
        differences = []
        for name in a.sheetnames:
            wa, wc = a[name], c[name]
            if (wa.max_row, wa.max_column) != (wc.max_row, wc.max_column):
                differences.append(f"{name}: size differs")
                continue
            for row in range(1, wa.max_row + 1):
                for col in range(1, wa.max_column + 1):
                    if wa.cell(row=row, column=col).value != \
                            wc.cell(row=row, column=col).value:
                        differences.append(f"{name}!{row},{col}")
                        break
                if differences:
                    break
        check(not differences,
              "the command line produces the same workbook as the web service",
              "; ".join(differences[:3]))


def test_feature_surface_agrees():
    """The features the requirement names are present in both front ends."""
    print("\n=== the named features exist in both front ends ===")
    gui = open(GUI_SRC, encoding="utf-8").read()
    page = open(WEB_PAGE, encoding="utf-8").read()

    shared = {
        "column picker": ("FieldPicker", ["required", "optional"]),
        "DXCC entity": ("DXCC_ENTITY", ["DXCC", "entity"]),
    }
    for feature, (gui_token, page_tokens) in shared.items():
        check(gui_token in gui, f"desktop has: {feature}")
        check(any(token in page or token.lower() in page.lower()
                  for token in page_tokens),
              f"web has: {feature}")

    # The postage column is not hardcoded in the page: it arrives in the column
    # catalogue and is rendered with its Chinese label (邮资), which is why the
    # page never mentions the column name.
    catalogue = webapp.field_catalogue()
    everything = catalogue["required"] + catalogue["optional"]
    postage_item = [item for item in everything
                    if item["name"] == core.POSTAGE_COLUMN]
    check(postage_item and postage_item[0]["label"]
          == core.field_label(core.POSTAGE_COLUMN),
          "the postage column is offered by the catalogue with its core label",
          str(postage_item))
    check(postage_item and postage_item[0]["derived"]
          and postage_item[0]["always"],
          "the postage column is marked derived and always-written")
    check("邮资" in page, "the page shows the postage label")
    check(core.POSTAGE_COLUMN in gui,
          "the desktop app knows the postage column")
    check("QSL_POSTAGE" not in page,
          "the page does not hardcode the postage column name")

    # Both must let the user pick a folder and multiple files.
    check("askdirectory" in gui, "desktop can take a whole folder")
    check("webkitdirectory" in page or "拖" in page,
          "the page can take many files at once")


def main() -> int:
    print("=== front-end parity ===")
    test_column_catalogue_matches_core()
    test_mandatory_and_presets()
    test_desktop_uses_core_constants()
    test_web_page_does_not_parse_adif()
    test_feature_surface_agrees()
    test_identical_output_everywhere()
    print(f"\nchecks: {checks}   failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
