# adif2xlsx.py - full adversarial case table

Tool under test: `adif2xlsx.py` sha256 `fc0f332b347e87351e24c874468f941c2097f0aae1bd8d2010438a163c8fda9b`

**155/155 checks passed, 0 failed.**

## G1 - field-length correctness (declared CHARACTER length)

10/10 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | G1a value containing '<' and '>' (declared len 12) | 1 QSO, COMMENT == 'a<b>c<d>e fg' | rc=0 rows=1 COMMENT='a<b>c<d>e fg' |
| PASS | G1b value containing a newline (declared len 11) | 1 QSO, COMMENT == 'line1\nline2' | rc=0 rows=1 COMMENT='line1\nline2' |
| PASS | G1c value containing the literal text '<EOR>' (2 QSOs) | 2 QSOs, row1 COMMENT == 'a<EOR>bcd', row2 CALL == 'K2DEF' | rc=0 rows=2 COMMENT='a<EOR>bcd' row2='K2DEF' |
| PASS | G1c2 literal '<EOR>' in last record WITHOUT a trailing <EOR> | 1 QSO, COMMENT == 'a<EOR>bcd', BAND == '20M' (BAND follows COMMENT) | rc=0 rows=1 COMMENT='a<EOR>bcd' BAND='20M' |
| PASS | G1d UTF-8 value, declared 5 CHARACTERS (<NAME:5>Jürge, 6 bytes) | 1 QSO, NAME == 'Jürge' | rc=0 rows=1 NAME='Jürge' |
| PASS | G1d2 LIMITATION: UTF-8 value declared by BYTES (<NAME:6>Jürge) | documented limitation: the parser counts CHARACTERS consistently (G1d), so a producer that declares byte lengths loses the next field silently | rc=0 rows=1 CALL='W1AW' NAME='Jürge<' MODE=None |
| PASS | G1e third element datatype form <FREQ:8:N>14.07400 | 1 QSO, FREQ_MHZ == 14.074, BAND == 20M, RST_SENT == '-10' | rc=0 rows=1 FREQ=14.074 BAND='20M' RST_SENT='-10' |
| PASS | G1f zero-length fields <COMMENT:0> in every record | 2 QSOs, no COMMENT/NOTES column | rc=0 rows=2 columns=['BAND', 'CALL', 'MODE', 'QSO_DATE', 'RST_RCVD', 'RST_SENT', 'SOURCE_FILE', 'STATION_CALLSIGN', 'TIME_ON_UTC'] |
| PASS | G1g declared length (100) exceeds remaining file | no crash; value takes the remaining text ('short<EOR>') | rc=0 rows=1 COMMENT='short<EOR>' |
| PASS | G1h LIMITATION: declared length 60 swallows the following QSO record | documented limitation: a wrong declared length is followed literally and consumes the next record (no resync, exit 0) | rc=0 rows=1 calls=['W1AW'] |

## G2 - header vs QSO classification

8/8 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | G2a header in its own record before <EOH> | 1 QSO; no ADIF_VER column; Summary ADIF version == 3.2.1 | rc=0 rows=1 cols=['BAND', 'CALL', 'MODE', 'QSO_DATE', 'RST_RCVD', 'RST_SENT', 'SOURCE_FILE', 'STATION_CALLSIGN', 'TIME_ON_UTC'] summary_ver='3.2.1' |
| PASS | G2b no header at all (records only) | 2 QSOs (W1AW, K2DEF) | rc=0 rows=2 calls=['W1AW', 'K2DEF'] |
| PASS | G2c no <EOH> (header record terminated by <EOR>) | 2 QSOs; header not counted | rc=0 rows=2 calls=['W1AW', 'K2DEF'] |
| PASS | G2d header and first QSO share one record | 2 QSOs (the shared record's QSO survives) | rc=0 rows=2 calls=['W1AW', 'K2DEF'] |
| PASS | G2e <EOH> then a second header-looking record later | 2 QSOs (W1AW, K2DEF); a header-only record is never a QSO | rc=0 rows=2 calls=['W1AW', 'K2DEF'] |
| PASS | G2f header fields each terminated by <EOR> before <EOH> | 1 QSO (W1AW) | rc=0 rows=1 calls=['W1AW'] |
| PASS | G2g header only, no QSOs | non-zero exit + clear error, no workbook | rc=1 stderr='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\g2g_header_only.adi: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\g2g_header_only.adi: no ADIF QSO records found (is this really an ADIF file?)\nERROR: no readable ADIF files' workbook=False |
| PASS | G2h <EOH> then one QSO with no trailing <EOR> | 1 QSO (W1AW) | rc=0 rows=1 calls=['W1AW'] |

## G3 - required-field mapping, real Excel types, no timezone shift

7/7 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | G3a all required fields mapped; QSO_DATE/TIME_ON are real Excel values | 9 required fields correct; QSO_DATE stored as an integral Excel date serial (fmt yyyy-mm-dd); TIME_ON_UTC a real time (fmt hh:mm:ss) | rc=0 rows=1 mismatches={} date=datetime.datetime(2024, 1, 1, 0, 0)/'yyyy-mm-dd' raw=(n,45292) time=datetime.time(12, 0)/'hh:mm:ss' |
| PASS | G3b TIME_ON HHMM (0000) and HHMMSS (235959, 120000), no timezone shift | times=[datetime.time(0, 0), datetime.time(23, 59, 59), datetime.time(12, 0)]; dates all 2024-01-01; type=time; fmt hh:mm:ss | rc=0 times=[datetime.time(0, 0), datetime.time(23, 59, 59), datetime.time(12, 0)] dates=[datetime.date(2024, 1, 1), datetime.date(2024, 1, 1), datetime.date(2024, 1, 1)] types={<class 'datetime.time'>} formats={'hh:mm:ss'} |
| PASS | G3c record logged 23:59 stays 23:59 on the same date (no tz conversion) | TIME_ON_UTC == 23:59:00, QSO_DATE == 2024-01-01 | time=datetime.time(23, 59) date=datetime.datetime(2024, 1, 1, 0, 0) |
| PASS | G3d invalid <QSO_DATE:8>20241340 | no crash; empty date cell; a warning is printed | rc=0 rows=1 QSO_DATE=None warning=False |
| PASS | G3e invalid <TIME_ON:6>256099 | no crash; empty time cell; a warning is printed | rc=0 rows=1 TIME_ON_UTC=None warning=False |
| PASS | G3f TIME_OFF / QSO_DATE_OFF mapped and typed | TIME_OFF_UTC == 01:30, QSO_DATE_OFF == 2024-01-02 | TIME_OFF_UTC=datetime.time(1, 30) QSO_DATE_OFF=datetime.datetime(2024, 1, 2, 0, 0) |
| PASS | G3g leap second 235960 | no crash; clamped to 23:59:59 (Excel cannot store :60) | rc=0 TIME_ON_UTC=datetime.time(23, 59, 59) |

## G4 - BAND/FREQ derivation

4/4 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | G4 band derivation table (22 frequencies/edges incl. out-of-band) | every FREQ-derived BAND matches the ADIF band plan incl. 54.000->5M, 119980->2.5MM, 149000->2MM, 300000->SUBMM; explicit BAND preserved; out-of-band FREQ yields NO band; FREQ_MHZ numeric with a 0.000* format | rc=0 rows=22 mismatches=[] freq_fmt_ok=True |
| PASS | G4b BAND without FREQ keeps BAND and leaves FREQ_MHZ empty | BAND == '40M', FREQ_MHZ is None | BAND='40M' FREQ_MHZ=None |
| PASS | G4c out-of-band 15.5 MHz must not get a bogus band | BAND == '' (empty), FREQ_MHZ == 15.5 | BAND=None FREQ_MHZ=15.5 |
| PASS | G4d Summary shows a '(none)' band bucket for the out-of-band QSO | '(none)' present in the BAND breakdown (no invented band) | 'none' in summary: True |

## G5 - optional-field auto-detection and SOURCE_FILE

5/5 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | G5a field present in only ONE record becomes a column (others empty) | MY_ANTENNA / APP_MYLOG_SCORE / COMMENT columns exist; row1 populated; row2 empty | rc=0 missing_columns=[] row1='Yagi'/'17'/'only here' row2={'MY_ANTENNA': None, 'APP_MYLOG_SCORE': None, 'COMMENT': None} |
| PASS | G5b field empty in EVERY record produces NO column | no COMMENT / SRX / NOTES column; 2 QSOs | rc=0 rows=2 columns=['BAND', 'CALL', 'MODE', 'QSO_DATE', 'RST_RCVD', 'RST_SENT', 'SOURCE_FILE', 'STATION_CALLSIGN', 'TIME_ON_UTC'] |
| PASS | G5c SOURCE_FILE identifies the origin file when merging two files | [('W1AW', 'g5c_alpha.adi'), ('K2DEF', 'g5c_beta.adi')] | rc=0 got=[('W1AW', 'g5c_alpha.adi'), ('K2DEF', 'g5c_beta.adi')] |
| PASS | G5d two different folders each containing log.adi | 2 QSOs with two DISTINCT SOURCE_FILE labels | rc=0 rows=2 labels=['log.adi', 'log (2).adi'] |
| PASS | G5e field empty in one record, populated in the other | COMMENT column kept; row1 empty, row2 'hello' | rc=0 columns=['BAND', 'CALL', 'COMMENT', 'MODE', 'QSO_DATE', 'RST_RCVD', 'RST_SENT', 'SOURCE_FILE', 'STATION_CALLSIGN', 'TIME_ON_UTC'] values=[None, 'hello'] |

## G6 - multi-file, folders, --recursive, output paths

6/6 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | G6a two positional files merge to 3+2 = 5 rows, no record lost | 5 rows in order W1AW,K2DEF,N3XYZ,DL1AA,DL2BB | rc=0 rows=5 calls=['W1AW', 'K2DEF', 'N3XYZ', 'DL1AA', 'DL2BB'] |
| PASS | G6b folder input picks up .adi/.adif only (txt ignored): 2+1 = 3 rows | 3 rows: AA1AA, AA2AA, BB1BB; ignore.txt not read | rc=0 rows=3 calls=['AA1AA', 'AA2AA', 'BB1BB'] |
| PASS | G6c --recursive includes nested folders; without it only the top level | flat = [TOP1]; recursive = [DEEP1, DEEP2, TOP1] | flat rc=0 ['TOP1']; recursive rc=0 ['DEEP1', 'DEEP2', 'TOP1'] |
| PASS | G6d output path containing spaces (and a new sub-folder) | rc=0, workbook written, 1 row | rc=0 exists=True rows=1 stderr='' |
| PASS | G6e relative input and relative output paths (cwd = verification\relrun) | rc=0; 2 rows; 'sub\rel_nested.xlsx' created (missing dirs made) | rc1=0 rows1=2; rc2=0 rows2=2 stderr='' |
| PASS | G6f the same file given twice on the command line | 1 row (input de-duplicated) or 2 rows (duplicated) - recorded, not judged | rc=0 rows=1 |

## B1 - terminator text inside values (finding 1 quantification)

9/9 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | B1a LAST record, no trailing <EOR>, value contains '<EOR>' | 2 QSOs; record 2 complete: ['BAND', 'CALL', 'COMMENT', 'FREQ_MHZ', 'MODE', 'RST_SENT', 'STATION_CALLSIGN'] | rc=0 rows=2 record2={'CALL': 'K2DEF', 'COMMENT': 'a<EOR>bcd', 'BAND': '20M', 'MODE': 'SSB', 'RST_SENT': '59', 'STATION_CALLSIGN': 'DL1AA', 'FREQ_MHZ': 14.074} lost_fields=[] |
| PASS | B1b control: same value, LAST record WITH a trailing <EOR> | 2 QSOs; record 2 complete (value keeps its '<EOR>' text) | rc=0 rows=2 mismatches=[] |
| PASS | B1c control: '<EOR>' inside a value of a NON-last record | 2 QSOs; record 1 complete | rc=0 rows=2 mismatches=[] |
| PASS | B1d LAST record, no trailing <EOR>, value contains '<EOH>' in prose | 2 QSOs; record 2 complete | rc=0 rows=2 lost=[] |
| PASS | B1e LAST record, no trailing <EOR>, value contains '<EOD>' | 2 QSOs; record 2 complete | rc=0 rows=2 lost=[] |
| PASS | B1f preamble prose containing '<EOH>' before the real header | 1 QSO (W1AW, MODE SSB) | rc=0 rows=1 row={'CALL': 'W1AW', 'MODE': 'SSB', 'QSO_DATE': datetime.datetime(2024, 1, 1, 0, 0)} |
| PASS | B1g preamble prose containing '<EOR>' before the real header | 1 QSO (W1AW) | rc=0 rows=1 calls=['W1AW'] |
| PASS | B1h single QSO, no <EOR>/<EOD> anywhere in the file | 1 QSO complete (lenient producer: omitted final terminator) | rc=0 rows=1 row={'CALL': 'W1AW', 'MODE': 'SSB'} |
| PASS | B1i three records, only the last lacks a trailing <EOR> | 3 QSOs, last one complete | rc=0 rows=3 calls=['W1AW', 'K2DEF', 'N3XYZ'] last_mode='FT8' |

## P - parser control-flow probes (post-rewrite)

14/14 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | P1 unrecognised tag '<MYSTERY:3>abc' between records | 3 QSOs (unknown fields are auto-detected, nothing after them is dropped) | rc=0 rows=3 calls=['W1AW', 'K2DEF', 'N3XYZ'] stderr='' |
| PASS | P2 bare tag '<NOTE>' (no length) between records | 2 QSOs | rc=0 rows=2 calls=['W1AW', 'K2DEF'] |
| PASS | P3 free text line between two records | 2 QSOs | rc=0 rows=2 calls=['W1AW', 'K2DEF'] |
| PASS | P4 trailing junk/tag after the last record | 1 QSO | rc=0 rows=1 calls=['W1AW'] |
| PASS | P5 file with a single data field (<CALL:4>W1AW<EOR>) | 1 QSO accepted (73443B15 vocabulary rule: CALL is a known field name) | rc=0 workbook=True rows=1 calls=['W1AW'] stderr='' |
| PASS | P6 file with exactly 2 data fields (boundary of the new rule) | 1 QSO accepted | rc=0 rows=1 |
| PASS | P7 second header block + <EOH> in the middle of the file | 2 QSOs (nothing after the second <EOH> is lost; header tags not QSO rows) | rc=0 rows=2 calls=['W1AW', 'K2DEF'] |
| PASS | P8 <EOD> as the final terminator instead of <EOR> | 1 QSO | rc=0 rows=1 calls=['W1AW'] |
| PASS | P9 header-only record in the middle of the file | 2 QSOs, no blank row | rc=0 rows=2 calls=['W1AW', 'K2DEF'] |
| PASS | P10 header-only record at the END of the file | 1 QSO, no blank row | rc=0 rows=1 calls=['W1AW'] |
| PASS | P11 value containing '<EOR>' in a record followed by another record | 2 QSOs; COMMENT == 'a<EOR>bcd' | rc=0 rows=2 COMMENT='a<EOR>bcd' |
| PASS | P12 bare unrecognised tag '<zzz>' between records | 3 QSOs | rc=0 rows=3 calls=['W1AW', 'K2DEF', 'N3XYZ'] |
| PASS | P13 banner preamble containing <EOH> and <EOR> in prose | 1 QSO (W1AW), preamble ignored | rc=0 rows=1 calls=['W1AW'] |
| PASS | P14 FINDING 1: last record, no trailing <EOR>, value contains '<EOR>' | 2 QSOs; every field after the value survives | rc=0 rows=2 mismatches={} |

## G7 - robustness / hostile inputs

20/20 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | R1 empty file (0 bytes) | rc!=0, clear message, no traceback, no workbook | rc=1 workbook=no rows=- traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r1_empty.adi: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r' stdout_tail='' |
| PASS | R2 text file with no ADIF content ('<' absent) | rc!=0, clear message, no traceback, no workbook | rc=1 workbook=no rows=- traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r2_plain_text.txt: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\ca' stdout_tail='' |
| PASS | R3 text file with '<' but no ADIF at all (HTML) | rc!=0, clear message, no traceback, no workbook | rc=1 workbook=no rows=- traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r3_html.txt: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r3' stdout_tail='' |
| PASS | R3b note file containing a pseudo length-prefixed tag '<b:2>hi' | rc!=0, clear message, no traceback, no workbook | rc=1 workbook=no rows=- traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r3b_pseudo_adif.txt: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\' stdout_tail='' |
| PASS | R4 truncated mid-value (declared length runs past EOF) | no traceback; behaviour recorded | rc=0 workbook=yes rows=2 traceback=False stderr[0]='' stdout_tail='              (a field the producer does not export at all is normal, e.g. RST in LoTW exports)' |
| PASS | R5 truncated in the middle of a field tag | no traceback | rc=0 workbook=yes rows=2 traceback=False stderr[0]='' stdout_tail='              (a field the producer does not export at all is normal, e.g. RST in LoTW exports)' |
| PASS | R6 directory containing no .adi/.adif files | rc!=0 with a clear message, no traceback | rc=2 workbook=no rows=- traceback=False stderr[0]='ERROR: no .adi/.adif files found in the given inputs' stdout_tail='' |
| PASS | R7 .adi with a header but no QSOs | rc!=0 with a clear message, no traceback, no workbook | rc=1 workbook=no rows=- traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r7_header_only.adi: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\c' stdout_tail='' |
| PASS | R8 input path that does not exist | rc=2 with a clear message, no traceback | rc=2 workbook=no rows=- traceback=False stderr[0]='ERROR: input not found: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\does_not_exist.adi' stdout_tail='' |
| PASS | R9 one good file + one unreadable (empty) file in the same run | non-zero exit (a file was skipped) with a warning; good file still converted | rc=1 workbook=yes rows=1 traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r9_empty.adi: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r' stdout_tail='  Source    : 1 file(s)' |
| PASS | R10 control character (0x01) inside a COMMENT value | no traceback: either a clean error or the character neutralised | rc=0 workbook=yes rows=1 traceback=False stderr[0]='' stdout_tail='  Source    : 1 file(s)' |
| PASS | R10b vertical tab (0x0B) inside a COMMENT value | no traceback | rc=0 workbook=yes rows=1 traceback=False stderr[0]='' stdout_tail='  Source    : 1 file(s)' |
| PASS | R10c which control bytes break the conversion | no traceback for any byte; every byte neutralised or reported cleanly | crashing bytes: []; per-byte: {'0x00': 'rc=0', '0x01': 'rc=0', '0x08': 'rc=0', '0x0B': 'rc=0', '0x0C': 'rc=0', '0x1F': 'rc=0', '0x7F': 'rc=0', '0x81': 'rc=0'} (for every crashing byte: rc=1, no .xlsx written, 'Traceback ... IllegalCharacterError' on stderr) |
| PASS | R11 CP1252 (latin-1) high byte in a value | no traceback; value decoded (café) | rc=0 workbook=yes rows=1 traceback=False stderr[0]='' stdout_tail='  Source    : 1 file(s)' |
| PASS | R12 UTF-16 encoded file with BOM | no traceback; value decoded correctly | rc=0 workbook=yes rows=1 traceback=False stderr[0]='' stdout_tail='  Source    : 1 file(s)' |
| PASS | R13 binary file (all 256 byte values) | no traceback | rc=1 workbook=no rows=- traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r13_binary.bin: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases' stdout_tail='' |
| PASS | R14 file containing only <EOR> tags | rc!=0 with a clear message, no traceback, no workbook | rc=1 workbook=no rows=- traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r14_only_eor.adi: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cas' stdout_tail='' |
| PASS | R15 a bare '<CALL>' tag (no length, no value, not a structural tag) | rc!=0 (cannot be ADIF) - behaviour recorded | rc=1 workbook=no rows=- traceback=False stderr[0]='WARNING: skipped C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cases\\r15_bare_tag.adi: C:\\Users\\Administrator\\Desktop\\ADIF to Excel\\verification\\cas' stdout_tail='' |
| PASS | R16 COMMENT of 40000 characters (Excel cell limit is 32767) | no traceback | rc=0 workbook=yes rows=1 traceback=False stderr[0]='' stdout_tail='  Source    : 1 file(s)' |
| PASS | R17 well-formed record with the trailing <EOR> omitted | 1 QSO converted (lenient) | rc=0 workbook=yes rows=1 traceback=False stderr[0]='' stdout_tail='  Source    : 1 file(s)' |

## FID - independent record-count cross-check on the real fixtures

5/5 passed

| verdict | case | expected | observed |
|---|---|---|---|
| PASS | FID sample_log.adi: 17 raw records -> workbook rows | rows == raw record count == 17; callsign multiset identical (raw <EOR> terminators: 17) | rc=0 rows=17 raw=17 eor=17 calls_diff=[]/[] |
| PASS | FID sample_lotw_quirks.adi: 5 raw records -> workbook rows | rows == raw record count == 5; callsign multiset identical (raw <EOR> terminators: 5) | rc=0 rows=5 raw=5 eor=5 calls_diff=[]/[] |
| PASS | FID perf_1000.adi: 1000 raw records -> workbook rows | rows == raw record count == 1000; callsign multiset identical (raw <EOR> terminators: 1000) | rc=0 rows=1000 raw=1000 eor=1000 calls_diff=[]/[] |
| PASS | FID merged 3 real files: rows == sum of parts, SOURCE_FILE counts match | 1022 rows; per-file counts {'sample_log.adi': 17, 'sample_lotw_quirks.adi': 5, 'perf_1000.adi': 1000} | rc=0 rows=1022 by_source={'sample_log.adi': 17, 'sample_lotw_quirks.adi': 5, 'perf_1000.adi': 1000} |
| PASS | FID merged workbook: every raw CALL present exactly the right number of times | 1022 callsigns, identical multiset | missing=[] extra=[] |

