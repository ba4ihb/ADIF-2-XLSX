<div align="center">

# ADIF → Excel ✨

**Turn an amateur radio log into a clean Excel workbook**

[![tests](https://github.com/ba4ihb/ADIF-2-XLSX/actions/workflows/tests.yml/badge.svg)](https://github.com/ba4ihb/ADIF-2-XLSX/actions/workflows/tests.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-2b2b2b.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-94%2E0%25-3776AB?logo=python&logoColor=white)](#language-composition)
[![HTML](https://img.shields.io/badge/HTML-5%2E8%25-E34F26?logo=html5&logoColor=white)](#language-composition)
[![Batchfile](https://img.shields.io/badge/Batchfile-0%2E3%25-4D4D4D)](#language-composition)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](#requirements)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D4?logo=windows&logoColor=white)](#download)
[![DXCC](https://img.shields.io/badge/DXCC-ARRL%202026-FF7EA8)](src/dxcc_tables.py)

**🌐 Language： [简体中文](README.md) · `English`**

</div>

> ### 🤖 About the author
>
> **Every line of code, every test and all documentation in this project was written by
> [DeepSeek Harness](https://github.com/deepseek-ai) + DeepSeek-V4.1-Flash Max.**
>
> **本项目的全部代码、测试与文档，均由 DeepSeek Harness + DeepSeek-V4.1-Flash Max 编写。**
> The Chinese documentation is [README.md](README.md).

---

## Contents

- [Just use it: the browser edition](#just-use-it-the-browser-edition)
- [Download](#download)
- [Four front ends, one implementation](#four-front-ends-one-implementation)
- [Quick start](#quick-start)
- [The workbook it writes](#the-workbook-it-writes)
- [DXCC entity is NOT the country](#dxcc-entity-is-not-the-country)
- [QSL postage](#qsl-postage-china-post)
- [Time handling](#time-handling-please-read-this)
- [Privacy](#privacy)
- [Requirements](#requirements)
- [Command line](#command-line)
- [Architecture](#architecture)
- [Language composition](#language-composition)
- [Project layout](#project-layout)
- [Verify it yourself](#verify-it-yourself)
- [Known limitations](#known-limitations)
- [Licence](#licence)

---

## Just use it: the browser edition

### 👉 <https://ba4ihb.github.io/ADIF-2-XLSX/web.html>

**Open the link and work. No download, no install, no local program to run.**

Drop your `.adi` / `.adif` onto the page → choose the columns → press start → the
workbook downloads.

| | |
|---|---|
| 🔒 **Nothing is uploaded** | The conversion happens inside your browser; the log never leaves the machine |
| 💻 **Any platform** | Phone, tablet, macOS, Linux (the packaged desktop app is Windows-only) |
| ⏱️ **~10 MB on first visit** | The Python runtime; the browser caches it afterwards and later visits are instant |
| 🚫 **No server** | The page calls no API and has no backend |

### How that is possible

The converter is Python (`src/adif2xlsx.py`). The browser edition runs **that same
Python file in the page** through [Pyodide](https://pyodide.org/) — CPython compiled
to WebAssembly. It is **not** a second implementation in JavaScript; it is the same
converter in a different place.

So the browser and desktop editions **cannot drift apart**, and that is enforced by a
test rather than hoped for: `tests/test_browser_edition.py` checks that the sources
packed into the page are **byte-identical to `src/`**, and drives a real conversion in
a headless browser.

---

## Download

Prefer not to wait for those 10 MB, or offline? Get a ZIP from
[**Releases**](https://github.com/ba4ihb/ADIF-2-XLSX/releases/latest).
Every ZIP is **unpack and run** — no Python needed, nothing to install.

| ZIP | Interface | Double-click after unpacking |
|-----|-----------|------------------------------|
| `adif2xlsx-web.zip` | Local service + browser UI | `启动网页版.bat` |
| `adif2xlsx-ui.zip` | Desktop window | `adif2xlsx-ui.exe` |
| `adif2xlsx-cli.zip` | Command line | run `adif2xlsx.exe` in a terminal |
| `adif2xlsx-all.zip` | All six builds | your choice |
| `*-onedir-*.zip` | Folder build | **starts much faster — recommended for daily use** |
| `SHA256SUMS.txt` | Checksums | `certutil -hashfile <file> SHA256` |

> **The single-file build starts slowly**: it unpacks itself to a temp folder on every
> launch, about 8–60 s depending on disk and memory. The `-onedir` folder build starts
> much faster.

---

## Four front ends, one implementation

The browser, local-service, desktop and command-line editions **share one converter**,
so the column catalogue, the Chinese labels, the presets and the output format are
identical. A test enforces this rather than trusting it.

| Capability | Browser | Local service | Desktop | CLI |
|------------|:---:|:---:|:---:|:---:|
| Multiple files / a whole folder | ✅ | ✅ | ✅ | ✅ |
| Column selection (common / all / required only / per-column) | ✅ | ✅ | ✅ | ✅ |
| Auto-detects ADIF fields (nothing hardcoded) | ✅ | ✅ | ✅ | ✅ |
| DXCC entity + the evidence for it | ✅ | ✅ | ✅ | ✅ |
| QSL letter postage | ✅ | ✅ | ✅ | ✅ |
| Merges several logs into one workbook | ✅ | ✅ | ✅ | ✅ |
| Where the output goes | browser download | download or disk | disk (Desktop by default) | disk (Desktop by default) |
| Installation needed | none | ZIP | ZIP | ZIP |
| Platform | any | Windows | Windows | Windows |
| Network access | none | none | none | none |

The only difference is **where the output goes**: a web page cannot write to an
arbitrary path on your disk, and should not be able to, so the browser edition
downloads to your browser's download folder with a name you can edit.

---

## Quick start

### Browser edition

Open [this link](https://ba4ihb.github.io/ADIF-2-XLSX/web.html). There is no step two.

### Desktop edition

1. Unpack the ZIP and double-click `adif2xlsx-ui.exe`.
2. Drag your ADI files, or a whole folder, into the window.
3. Tick the optional columns you want, or use the common / all / required-only presets.
4. Press start, then open the workbook it writes.

### Command line

```bat
:: one file, written to the Desktop
adif2xlsx.exe mylog.adi

:: a whole folder including sub-folders, named output
adif2xlsx.exe D:\logs -r -o D:\out\all.xlsx

:: required columns plus the two generated ones only
adif2xlsx.exe mylog.adi --columns required

:: what column names can I pass?
adif2xlsx.exe --list-fields
```

### From source

```bash
git clone https://github.com/ba4ihb/ADIF-2-XLSX.git
cd ADIF-2-XLSX
pip install openpyxl

python src/adif2xlsx.py mylog.adi          # command line
python src/adif2xlsx.py --gui              # desktop window
python src/webapp.py                       # local web service
```

---

## The workbook it writes

Two sheets.

### Sheet `QSOs`

- **Row 1**: the English column names in upper case. This is the documented
  interface — formulas and scripts should use it.
- **Row 2**: Chinese labels, for reading.
- **Row 3 onwards**: one row per QSO.
- The panes are frozen at `A3` and autofilter covers the data range.
- Dates and times are **real Excel date/time values**, not text, so they sort and
  subtract properly.

**Required columns (9, always written):**

| Column | Chinese label | Meaning |
|--------|---------------|---------|
| `CALL` | 对方呼号 | the other station |
| `QSO_DATE` | 通联日期(UTC) | date of contact |
| `TIME_ON_UTC` | 开始时间(UTC) | start time |
| `FREQ_MHZ` | 频率(MHz) | frequency |
| `BAND` | 波段 | band |
| `MODE` | 模式 | mode |
| `RST_SENT` | 发送信号报告 | report sent |
| `RST_RCVD` | 接收信号报告 | report received |
| `STATION_CALLSIGN` | 本方呼号 | your callsign |

Plus three **generated columns**, also always written:

| Column | Chinese label | Meaning |
|--------|---------------|---------|
| `SOURCE_FILE` | 来源文件 | which ADI this row came from |
| `DXCC_ENTITY` | DXCC 实体 | the resolved entity |
| `QSL_POSTAGE_AIR` | QSL 邮资(RMB) | 20 g letter rate |

And two more generated columns, written **only when they have something to say**:

| Column | Chinese label | Meaning |
|--------|---------------|---------|
| `DXCC_SOURCE` | 实体判定依据 | `ADIF_DXCC`, `ADIF_COUNTRY` or `PREFIX`; for an ambiguous prefix it names the other candidates |
| `QSL_POSTAGE_DETAIL` | 邮资明细 | for example `航空 6.00 / 水陆路 4.00` |

**Optional columns are not hardcoded.** The tool scans the ADI for **every** field
that actually appears and gives each one a column. 55 common fields have Chinese
labels; anything else keeps its ADIF name.

> **A field that is empty in every record produces no column at all.** Different
> producers export different fields, so the column sets differ — that is deliberate,
> and the Summary sheet explains the fill state column by column.

`--list-fields` prints every name `--columns` accepts.

### Sheet `Summary`

| Where | What |
|-------|------|
| **Row 1** | Data sources and what an empty cell means (merged A1:D1, wrapped) |
| Middle | Overview, per-band and per-mode counts, top callsigns, source files |
| Bottom | **Per-column fill state** — how many rows have a value, how many do not |

Row 1 sits at the top on purpose: "why is this cell empty?" is a question you ask while
looking at the `QSOs` sheet, and the previous placement — just above the fill table —
was two screens down in a 100-plus-row sheet where nobody found it.

---

## DXCC entity is NOT the country

This is where the tool is easiest to get wrong, so it is worth being precise.

**One country can contain several DXCC entities:**

| Country | Its DXCC entities |
|---------|-------------------|
| China | mainland (`B<digit>`) · Hong Kong (`VR2`) · Macao (`XX9`) · **Taiwan** (`BM`–`BQ`, `BU`–`BW`, `BX`) · Scarborough Reef (`BS7`) |
| Russia | European part (call areas 1–7) · Asiatic part (8/9/0) · Kaliningrad (`UA2`/`RA2`) |
| United States | mainland · Hawaii (`KH6/7`) · Alaska (`KL/AL/NL`) · Puerto Rico (`KP3/4`) · Guam · Wake I. … |
| France | mainland · Corsica · Guadeloupe · Martinique · Réunion · New Caledonia … |

**Resolution order:**

1. The log's own `DXCC` number — **authoritative**, used as-is
2. The log's own `COUNTRY` field
3. The callsign prefix (longest match, plus special rules)

Which one was used is written to `DXCC_SOURCE`, so every row shows how its answer was
reached.

### The DXCC table is generated from the ARRL list

It is **not hand-written**. Scripts under `tools/` build it from the
**ARRL DXCC List (January 2026 edition: 340 current entities, 62 deleted, 769 prefix
rows)**:

```bash
python tools/parse_arrl_pdf.py       <DXCC_Current.pdf> tools/data/arrl_dxcc_2026.txt
python tools/strip_glossary_notes.py <DXCC_Current.pdf> tools/data/arrl_dxcc_2026.txt
python tools/build_dxcc.py           # -> src/dxcc_tables.py
```

> `src/dxcc_tables.py` is **generated — do not edit it by hand.**

**Why this matters.** An early version used a hand-written number table, and the number
is authoritative: LoTW, Club Log and N1MM all write `DXCC`, and the parser trusts it
first. The mistakes it made:

| Callsign | Number in the log | Hand-written table said | The ARRL list says |
|----------|------------------|------------------------|--------------------|
| `SP4DDS` | 269 | **Togo** ❌ | Poland |
| `E74K` | 501 | **Jordan** ❌ | Bosnia and Herzegovina |

The country was wrong and so was the postage. It was not two bad entries; the whole
number table was wrong.

**How the parsing is made trustworthy.** A PDF cell glues call areas, glossary footnote
numbers and even part of the entity name together:

| What the cell contains | What it means |
|------------------------|---------------|
| `ZC442UK` | allocation `ZC4` + footnote 42 + the "UK" inside the entity name |
| `JD119` | `JD1` + footnote 19 |
| `OK-OL23` | the range `OK-OL` + footnote 23 |
| `9M2,4` | `9M2`, `9M4` |

**No digit is ever guessed to be a footnote.** The script also reads the document's own
glossary, where each footnote states which allocation it belongs to
(`42   (ZC4) ...`), and matches on that. Every correction therefore comes from the
document itself and can be checked one by one.

### 56 prefixes belong to several entities

**Fifty-six prefixes in the ARRL list are held by more than one entity, and the
list does not say which call area belongs to which:**

| Prefix | Entities the list gives it |
|--------|----------------------------|
| `CE0` | Easter I. · Juan Fernandez Is. · San Felix & San Ambrosio |
| `FO` / `TX` | French Polynesia · Clipperton I. · Austral I. · Marquesas Is. |
| `TO` | Guadeloupe · Mayotte · Saint Barthelemy · Martinique · Reunion I. · Tromelin I. · Saint Martin |
| `3D2` | Fiji · Rotuma I. · Conway Reef |
| `VK0` | Heard I. · Macquarie I. |

A table lookup can only return **one** entity, so the tool has to choose — **but it
does not choose silently.**

**Whenever a prefix is ambiguous, the `DXCC_SOURCE` column names the alternatives:**

```text
CE0Z   →  Easter I.         PREFIX (CE0 shared with Juan Fernandez Is., San Felix & San Ambrosio)
VK0AA  →  Heard I.          PREFIX (VK0 shared with Macquarie I.)
3D2AA  →  Fiji              PREFIX (3D2 shared with Rotuma I., Conway Reef)
```

So a rare-island contact shows "**this could be Easter Island, or it could be Juan
Fernández**" rather than a wrong answer with nothing to warn you.

> **For a definite answer, have your logger write `DXCC` or `COUNTRY`** — both
> always outrank the prefix. LoTW, Club Log and N1MM all write `DXCC`, so a real
> log rarely reaches the prefix route at all.

Sub-entities still resolve normally through their **longer** prefixes: `VK9X` →
Christmas I., `VK9L` → Lord Howe I., `KH7K` → Kure I., `3B9` → Rodrigues I.,
`VK9` → Australia.

### Coverage and limits

`tests/test_dxcc.py` runs **48 checks**, including a 260-block automated audit and a
list of 40-odd real callsigns covering the Chinese B blocks, the Russian call areas, US
states and rare islands. Coverage cannot quietly regress.

**Stated honestly:** a few entity numbers in the ARRL list cannot be independently
verified in this environment. Those entities are **reported by name** — the report and
the postage use the name — and the number column shows the prefix rather than
**inventing a number**. A number that comes from the log itself always wins.

---

## QSL postage (China Post)

Computed as an ordinary **20 g letter (信函)** and written to `QSL_POSTAGE_AIR`.

| Destination | Rate (RMB) |
|-------------|-----------|
| Mainland China | **1.20** (local 0.80) |
| Hong Kong / Macao / Taiwan | air **2.00** · surface **1.50** |
| International zone 1 (Japan and others, reduced Asia-Pacific tariff) | air 5.00 · SAL 4.50 · surface 3.50 |
| International zone 2 | air 5.50 · SAL 5.00 · surface 4.00 |
| International zone 3 | air 6.00 · SAL 5.50 · surface 4.00 |
| International zone 4 | air 7.00 · SAL 6.50 · surface 4.00 |
| No postal service | the text **不通邮** plus the reason |

- **Letters only. Postcard prices are deliberately not offered.**
- Registration and return-receipt fees are **not** included.
- Surface rates appear only for destinations that actually offer surface mail.
- **All 340 DXCC entities have an answer**: 302 give a letter price and 38 say
  explicitly that there is no postal service, with the reason. Nothing is left blank
  for you to guess.

### A price always carries its provenance

The Summary sheet records:

- **Effective from**: 2018-12-07 (China Post international letter tariff)
- **Verified on**: 2026-10
- **Source links**

A stale price is worse than no price, so both dates stay in the file.

---

## Time handling (please read this)

- Everything is written as **UTC**, with **no timezone conversion whatsoever**.
- Column names carry `_UTC` (for example `TIME_ON_UTC`).
- The Chinese labels say `(UTC)` as well.
- The Summary sheet repeats it.

**Whatever time your log holds is what the workbook shows.** Nothing is guessed,
shifted or "corrected".

---

## Privacy

| Measure | Detail |
|---------|--------|
| Entirely local | The conversion makes no network calls |
| The browser edition uploads nothing | Your data never leaves the browser; there is no backend |
| Loopback only | The local service binds `127.0.0.1`, so other machines cannot reach it |
| Per-run token | A fresh token each run; requests without it are refused (403) |
| Path validation | Static file requests are prefix-checked against directory traversal |
| Temp files deleted | Uploads are removed as soon as the conversion finishes |
| No real data in the repository | The fixtures use synthetic callsigns |

**About the test data.** The six logs in `tests/fixtures/adi/` are **anonymised** real
exports: callsigns were replaced by synthetic ones of **the same length that resolve to
the same DXCC entity**, and personal fields became placeholders. Before committing,
`tools/audit_privacy.py` confirmed that **240 synthetic callsigns overlap the 240
originals in 0 cases**, and that no owner callsign, name, address, email or real grid
square remains.

The logs under `samples/` are **hand-written fiction** (`Bill`, `Honolulu` and so on)
and contain no real contacts at all.

---

## Requirements

| | |
|---|---|
| Operating system | Windows 10 / 11 (64-bit). The source is cross-platform; the packaging scripts target Windows |
| Python (source only) | **3.10 or newer** |
| Dependency (source only) | [`openpyxl`](https://openpyxl.readthedocs.io/) ≥ 3.1 |
| Packaged builds | **none** — no Python installation needed |
| Network | **not required** |
| Browser edition | A modern browser with WebAssembly; the first visit needs network access for the runtime |

Development toolchain (only needed to contribute): `pyinstaller` for packaging, `ruff`
for linting, `pypdf` only when regenerating the DXCC table.

---

## Command line

```text
adif2xlsx.exe [inputs...] [-o output.xlsx] [options]
```

Inputs may be **files, several files, or folders** (folders are searched for `.adi` /
`.adif`).

| Option | Meaning |
|--------|---------|
| `-o, --output PATH` | output xlsx path (default: Desktop `adif_export.xlsx`) |
| `-r, --recursive` | recurse into sub-folders when an input is a folder |
| `--columns NAME,NAME` | write only these extra columns; `required` means the required set only |
| `--list-fields` | list the accepted column names and exit |
| `--quiet` | print errors only |
| `--gui` | open the graphical interface (the default when double-clicked) |
| `--version` | show the version |

**Exit codes**

| Code | Meaning |
|------|---------|
| 0 | success |
| 1 | an input could not be parsed (damaged, not ADIF, …) |
| 2 | bad arguments, or the output path is not writable |

---

## Architecture

> **One implementation, four front ends.**

```
                      src/adif2xlsx.py
              (parsing · field mapping · writing xlsx)
                             │
        ┌────────────┬───────┴───────┬──────────────┐
        │            │               │              │
      CLI        desktop GUI    local HTTP      browser
   main()        gui.py          webapp.py      Pyodide
                                               (the same Python
                                                inside the page)
```

The important points:

- **The web front end does not parse ADIF.** It hands the files to the same
  `src/adif2xlsx.py`, so the DXCC table, the postage table, the column selection and
  the Summary fill report each exist in exactly one place.
- **The browser edition does not reimplement anything.** Pyodide runs the real Python
  modules in the page. To make that possible the core gained a few seams so the
  path-based and in-memory routes share one body of code: `_decode_adif()`,
  `parse_adif_bytes()`, `parse_adif_text()`, `build_workbook()` and `workbook_bytes()`.
- **The local service is local only.** It binds `127.0.0.1` and uses a per-run token.

> Why not rewrite it in JavaScript? Because **two implementations inevitably drift
> apart**, and avoiding exactly that is the point of this project.

---

## Language composition

Measured by `tools/lang_stats.py` over the repository's **non-blank code lines**,
excluding **generated files** (`src/dxcc_tables.py`, `web/browser.html` and its
byte-identical copy in `docs/`), third-party data and build output:

| Language | Lines | Share |
|----------|------:|------:|
| Python | 11,222 | **94.0 %** |
| HTML (interface shell) | 690 | **5.8 %** |
| Batchfile (launcher) | 32 | **0.3 %** |
| **Total** | **11,944** | 100 % |

Documentation and configuration (Markdown, TOML) and the one-off diagnostic
scripts under `tests/adversarial/` are listed separately and kept out of the code
mix.

Python dominating is deliberate: **the conversion, the DXCC table, the postage and
all four front ends are one body of Python.** HTML is only 5.8 % and is pure
interface shell — **it does not parse ADIF** — and the browser edition runs that
same Python directly in the page (see [Architecture](#architecture)). There is
therefore no second implementation to drift.

> This section previously read HTML **15.0 %**, which was a bug in the counting
> script: `web/browser.html` is generated from `web/index.html`, and
> `docs/web.html` is a byte-identical copy of it, so one file was counted twice
> and 1,798 lines were added twice over. Fixed.

Re-measure with `python tools/lang_stats.py`.

---

## Project layout

```text
ADIF-2-XLSX/
├── src/
│   ├── adif2xlsx.py       # core: ADIF parsing, field mapping, xlsx output, CLI
│   ├── dxcc.py            # DXCC resolution (the special rules live here)
│   ├── dxcc_tables.py     # GENERATED: ARRL entities and prefixes, do not edit
│   ├── postage.py         # China Post letter tariffs and zones
│   ├── gui.py             # desktop window (tkinter)
│   ├── webapp.py          # local HTTP service (standard library only)
│   └── pyi_rth_ui.py      # runtime hook used by the packaged build
├── web/
│   ├── browser.html       # browser edition page (generated; opens standalone)
│   ├── index.html         # local-service edition page
│   └── dist/              # assets the browser edition fetches (packed sources, wheels)
├── build_exe.py           # PyInstaller build (three variants × onefile/onedir)
├── tools/                 # DXCC table generation, ARRL PDF parsing, stats, privacy audit
│   └── data/              # the parsed ARRL list (reproducible, no network needed)
├── tests/                 # 10 suites plus the anonymised fixtures
│   └── fixtures/adi/      # real exports from six platforms, anonymised
├── samples/               # hand-written examples
├── docs/                  # landing page and screenshots (GitHub Pages publishes this)
└── .github/workflows/     # CI: Windows + Linux × Python 3.10 + 3.12
```

---

## Verify it yourself

```bash
python tests/run_all_tests.py          # the default 6 suites, about 2 minutes
python tests/run_all_tests.py --all    # all 9 suites, including the packaged build
```

| Suite | Checks | What it covers |
|-------|-------:|----------------|
| `test_enumerations.py` | 15 | The ADIF 3.1.7 enumerations and MODE/SUBMODE validity |
| `test_dxcc.py` | 48 | Table structure, callsign resolution, resolution order, Chinese/Russian/US special cases |
| `test_postage.py` | 56 | Tariff values, zones, not-mailable cases, name normalisation |
| `test_acceptance.py` | 240 | End-to-end conversion, column selection, path handling, Summary contents, exit codes |
| `test_frontend_parity.py` | 43 | All four front ends share the catalogue and labels and produce cell-identical workbooks |
| `test_browser_edition.py` | 47 | Packed sources byte-identical to `src/`; a real conversion in a headless browser |
| `test_gui.py` | 37 | The desktop UI and the no-console paths (skips itself with no display) |
| `test_web.py` | 69 | The HTTP API, token enforcement, directory-traversal defence |
| `test_exe.py` | packaged | The packaged exe produces a workbook **cell-identical** to the source's |

**Current state**: the default 6 suites and 449 checks pass; all 9 suites and
**552 checks** pass; `ruff check` is clean.

**CI** runs on **Windows + Linux × Python 3.10 + 3.12** — see the badge at the top.

**Fuzzing**: `python tests/test_fuzz.py 500 --seed 424242` — 200 malformed inputs,
0 failures.

---

## Known limitations

- **The black window**: the local-service edition opens a console window at start.
  **Do not close it while converting.** It is the service, not an error.
- **Package size**: about **22 MB** for the single-file exe and **49 MB** unpacked
  for the folder build. The whole Python runtime and openpyxl are embedded, so no
  Python installation is needed. The build explicitly **excludes numpy, pandas,
  matplotlib and scipy**, none of which the program uses — without that the
  download would be roughly 27 MB larger.
- **The single-file build starts slowly**: 8–60 s depending on disk and memory. The
  folder build is markedly faster.
- **A few DXCC numbers could not be independently verified**: those entities are
  reported by name and their number column shows the prefix rather than an invented
  number.
- **The fixtures are anonymised**, so they **cannot** be used to validate how the tool
  judges a real log.
- **Never rendered in real Excel**: the development environment has no Excel or
  LibreOffice. The workbook **contents** were checked cell by cell, including against
  the packaged build, but the **visual appearance** has not been confirmed by eye.

---

## Licence

**[GNU General Public License v3.0](LICENSE)** — free software: use, modify and
redistribute it freely.

When you distribute this program or a derivative of it, **you must also make the
complete source available** under the same GPL-3.0 terms. The program comes with
**no warranty at all**.

### Third-party data

| Source | Used for | Note |
|--------|----------|------|
| ARRL DXCC List | entity numbers and prefixes | published list, used as reference data |
| China Post tariffs | QSL letter postage | published tariffs; the Summary sheet records the effective and verification dates |
| ADIF 3.1.7 specification | field definitions, MODE/SUBMODE enumerations | public specification |

This project is not affiliated with ARRL, China Post or the ADIF maintainers.

---

## Credits

**The idea came from my best friend BA4JBN.**
Without it this tool would not exist — every line of code and documentation here
was built on that starting point.

**Every line of code and documentation was written by
[DeepSeek Harness](https://github.com/deepseek-ai) + DeepSeek-V4.1-Flash Max.**

Amateur radio · 73!

---

<div align="center">

**[🌐 简体中文版 →](README.md)**

<sub>GPL-3.0 · Made for Chinese hams</sub>

</div>
