# -*- coding: utf-8 -*-
r"""Render every results_*.json into verification\CASES.md (full case table).

Run: python verification\make_report.py
"""
from __future__ import annotations

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["g1_length", "g2_header", "g3_mapping", "g4_band", "g5_optional",
         "g6_paths", "b1_terminator", "p_parser", "g7_robust", "fidelity"]
TITLES = {
    "g1_length": "G1 - field-length correctness (declared CHARACTER length)",
    "g2_header": "G2 - header vs QSO classification",
    "g3_mapping": "G3 - required-field mapping, real Excel types, no timezone shift",
    "g4_band": "G4 - BAND/FREQ derivation",
    "g5_optional": "G5 - optional-field auto-detection and SOURCE_FILE",
    "g6_paths": "G6 - multi-file, folders, --recursive, output paths",
    "b1_terminator": "B1 - terminator text inside values (finding 1 quantification)",
    "p_parser": "P - parser control-flow probes (post-rewrite)",
    "g7_robust": "G7 - robustness / hostile inputs",
    "fidelity": "FID - independent record-count cross-check on the real fixtures",
}


def cell(text: str, limit: int = 300) -> str:
    text = str(text).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[:limit - 1] + "\u2026"


def main() -> None:
    data = {}
    sha = "?"
    for path in sorted(glob.glob(os.path.join(HERE, "results_*.json"))):
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        data[blob["tag"]] = blob
        sha = blob.get("tool_sha256", sha)

    total = sum(len(d["results"]) for d in data.values())
    passed = sum(1 for d in data.values() for r in d["results"] if r["verdict"] == "PASS")
    fails = [(d["tag"], r) for d in data.values() for r in d["results"] if r["verdict"] != "PASS"]

    lines = [
        "# adif2xlsx.py - full adversarial case table",
        "",
        f"Tool under test: `adif2xlsx.py` sha256 `{sha}`",
        "",
        f"**{passed}/{total} checks passed, {len(fails)} failed.**",
        "",
    ]
    for tag in ORDER:
        blob = data.get(tag)
        if not blob:
            continue
        rs = blob["results"]
        n_ok = sum(1 for r in rs if r["verdict"] == "PASS")
        lines += [f"## {TITLES.get(tag, tag)}", "",
                  f"{n_ok}/{len(rs)} passed", "",
                  "| verdict | case | expected | observed |", "|---|---|---|---|"]
        for r in rs:
            lines.append("| {} | {} | {} | {} |".format(
                r["verdict"], cell(r["case"], 120), cell(r["expected"], 220),
                cell(r["observed"], 340)))
        lines.append("")
    out = os.path.join(HERE, "CASES.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {out}: {passed}/{total} pass, {len(fails)} fail")


if __name__ == "__main__":
    main()
