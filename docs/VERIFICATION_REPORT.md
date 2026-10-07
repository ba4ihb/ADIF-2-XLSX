# Independent adversarial verification of `adif2xlsx.py`

**Revision verified (frozen by the Lead):**
`sha256 FC0F332B347E87351E24C874468F941C2097F0AAE1BD8D2010438A163C8FDA9B`
(suite `verify_adif2xlsx.py` = `44422C7D…`, 177 checks - independently reproduced: **177/177**).

**Verdict: 155 / 155 of my checks PASS, 0 FAIL. All four defects (A-D) are closed and I found
no new defect. I have nothing to hold the release on.**

The behaviour matrix I asked for now holds as an invariant: **every one of the 11 file shapes
parses identically with a banner, without a banner, and behind a leading blank line** - same
exit code, same CALL sequence, same row count.

---

## 1. The four defects: closed

| Defect | Check now | Evidence |
|---|---|---|
| **A** non-`<` first byte + no `<EOH>` consumed the whole file | **H2, H2b, H2c, H2d all PASS** | leading `\r\n`, leading space, banner+QSOs and banner+header+QSOs with no `<EOH>` each convert to the correct rows; H group 17/17 (was 12/17) |
| **B** LoTW-style header only recognised behind a banner | **H1b PASS** | `<PROGRAMID:4>LoTW<APP_LOTW_LASTQSL…><APP_LOTW_NUMREC:3>199<eoh>` at byte 0 gives 2 rows, identical to the banner-prefixed variant (H1) |
| **C** `<?xml?>` prologue aborted the file | **Q10b PASS** | prologue + header + QSOs → 1 row, rc=0 (Q group 26/26) |
| **D** diagnostic missed `TIME_ON_UTC` / `FREQ_MHZ` | **G3e PASS, G3 7/7** | `verification\probe_diagnostic.py`: invalid `TIME_ON` → `incomplete=[(1,'W1AW',['TIME_ON_UTC'])]`; unparseable `FREQ` with no BAND → `['FREQ_MHZ/BAND']`; with an explicit BAND → `[]` (correct); invalid `QSO_DATE` still reported |

Your question case (a record holding header fields **and** a full QSO, ending at `<EOH>`) is now
consistent: 2 rows both with and without a banner, and the shared record survives as a QSO -
see matrix rows 3 and 4.

## 2. Invariant confirmed: banner / no-banner / leading-blank-line (11/11)

`python verification\cases_matrix.py` - each shape run three ways (plain, `Saved by MyLogger…`
banner, leading `\r\n`); all three must agree:

| # | shape | result (identical in all 3 variants) |
|---|---|---|
| 1 | standard header + `<EOH>` | 2 rows W1AW, K2DEF |
| 2 | LoTW header (`APP_*` names) + lowercase `<eoh>` | 2 rows |
| 3 | header fields + full QSO **in one record ending at `<EOH>`** | 2 rows - the QSO survives |
| 4 | header fields + full QSO in one record ending at `<EOR>` | 2 rows |
| 5 | header with **no `<EOH>`** (terminated by `<EOR>`) | 2 rows |
| 6 | empty header block then `<EOH>` | 2 rows |
| 7 | headerless, no `<EOH>`, last record unterminated | 2 rows |
| 8 | single headerless record, no terminator | 1 row |
| 9 | header-only record **in the middle** of the file | 2 rows, no bogus row |
| 10 | `<?xml?>` prologue then header then QSOs | 1 row |
| 11 | **recorded** header block carrying `COMMENT` | consistent: 1 blank-ish row + the QSO (see §4) |

## 3. Real exports re-confirmed after the change (13/13)

Counts derived from the raw bytes (case-insensitive `<eor>`), never from the tool's output:

| file | rows | raw `<eor>` | blank CALL rows | diagnostics |
|---|---|---|---|---|
| `lotw.adi` | **199** | 199 (self-declared `APP_LOTW_NUMREC=199`) | 0 | none |
| `JTDX.ADI` | **7** | 7 | 0 | none |
| `QRZ.adi` | **15** | 15 | 0 | none |
| `n1MM.adi` | **14** | 14 | 0 | none |
| `CLUBLOG.adi` | **11** | 11 | 0 | none |
| `tqsl.adi` | **3** | 3 | 0 | none |

Merged: **249 rows**, per-file `SOURCE_FILE` counts exact. Reads only - the originals in
`C:\Users\Administrator\Desktop\ADI` were copied into `verification\cases\real\` and hashed.

## 4. One residual trade-off worth knowing (NOT counted as a defect)

By design, a pre-`<EOH>` record that carries a `QSO_FIELDS` name is a QSO. So a **header block**
that happens to include one becomes a bogus QSO row. Measured with
`verification\probe_header_collision.py` (header `ADIF_VER` + `<FIELD>` + `<EOH>`, then one QSO;
correct output is 1 row):

- **header-safe (1 row):** `ADIF_VER`, `PROGRAMID`, `PROGRAMVERSION`, `CREATED_TIMESTAMP`,
  `APP_LOTW_NUMREC`, `APP_LOTW_LASTQSL`, `MY_CALL`, `MY_GRIDSQUARE` → **8/18**
- **becomes a QSO row (2 rows):** `OPERATOR`, `NAME`, `QTH`, `EMAIL`, `COMMENT`, `NOTES`,
  `GRIDSQUARE`, `STATION_CALLSIGN`, `CONTEST_ID`, `QSL_SENT` → **10/18**

This is the accepted cost of the content-aware rule (which I recommended), it is
banner-invariant, and **none of the six real exports hits it** - their headers carry only
`ADIF_VER`/`PROGRAMID`/`PROGRAMVERSION`/`CREATED_TIMESTAMP`/`APP_LOTW_*`. Mentioning it only so
the trade-off is on the record; I do not consider it a defect.

Related observation (benign): in the header branch, fields that are in `KNOWN_FIELDS` are not
copied into the header dict (`if key not in KNOWN_FIELDS or key in HEADER_FIELDS`). That means
`res.header` may omit e.g. `APP_LOTW_NUMREC`, but nothing reads header keys except
`ADIF_VER` / `PROGRAMID` / `PROGRAMVERSION`, all of which are in `HEADER_FIELDS` and therefore
always kept. No output is affected.

## 5. Coverage

| Group | Checks | Result |
|---|---|---|
| G1 field-length correctness | 10 | 10 PASS |
| G2 header vs QSO | 8 | 8 PASS |
| G3 required fields / Excel types / diagnostics | 7 | 7 PASS |
| G4 BAND/FREQ (22 frequencies incl. corrected edges) | 4 | 4 PASS |
| G5 optional auto-detection / SOURCE_FILE | 5 | 5 PASS |
| G6 multi-file / folders / `--recursive` / paths | 6 | 6 PASS |
| B1 terminator text inside values | 9 | 9 PASS |
| H header classification (regression group) | 17 | 17 PASS |
| **M banner-invariance matrix (new)** | **11** | **11 PASS** |
| P parser control-flow probes | 14 | 14 PASS |
| Q sanitize / markup / vocabulary / injection | 26 | 26 PASS |
| G7 robustness / hostile inputs | 20 | 20 PASS |
| FID fixture record-count cross-check | 5 | 5 PASS |
| REAL six genuine exports | 13 | 13 PASS |
| **total** | **155** | **155 PASS, 0 FAIL** |

Also carried forward and re-confirmed: control bytes are neutralised instead of aborting,
32 767-char cap, `=`-only formula neutralisation with 0 `<f>` elements in the package,
`-10`/`+12` RST values byte-identical to the source (2044/2044 RST cells), exit code 1 when an
input is skipped, `</EOR>`/`<EOD>`/`<EOR/>` terminators, rc=1 + no workbook for non-ADIF input.

Re-run: `python verification\run_all.py`. Case table: `verification\CASES.md`.
Logs: `verification\run_log.txt`, `verification\results_*.json`.
Fixtures lint clean (0 problems) - a bad declared length in a fixture cannot masquerade as a
pass.

## 6. What I still could NOT verify

1. **Real Excel/LibreOffice behaviour** - the bundled LibreOffice helper fails to launch in this
   environment (`0xC0000135`, DLL missing) and I did not substitute another office binary. All
   cell-level claims come from openpyxl plus raw OOXML inspection.
2. The ADIF spec wording for the header rule (`adif.org` unreachable from here); I verified
   behaviour and internal consistency, not spec fidelity.
3. Wild prevalence of a header carrying no `<EOH>`, a header at byte 0 with `APP_*` fields, or a
   header block carrying operator/comment fields - all constructed by me, not observed.
4. No random fuzzing, no >1000-record input, no `EXCEL_MAX_ROWS` boundary, no permission/symlink
   or concurrent-run cases.
5. The 155 checks above are the complete set I ran; I claim nothing beyond them.

## 7. Scope

All my writes are under `verification\`. I did not modify `adif2xlsx.py`,
`verify_adif2xlsx.py`, `make_*.py`, `samples\`, `perf_1000.adi`, any root `.xlsx`, or the
`C:\Users\Administrator\Desktop\ADI` originals. `verification\` contents were wiped once by
something outside this session between earlier rounds; everything has been regenerated, and
`REPORT_24E51902.md` holds the previous round's report.
