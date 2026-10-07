#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for QSL postage (src/postage.py).

The published China Post tariffs are the contract: if a rate or a zone
assignment changes, a test fails rather than the user getting a wrong price.

Run directly (``python tests/test_postage.py``) or through pytest.
"""

from __future__ import annotations

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import dxcc       # noqa: E402
import postage    # noqa: E402

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


def q(entity, service):
    """The quoted price for one service, or None when not offered."""
    return postage.quote(entity).rates.get(service)


def test_domestic():
    print("=== domestic (国内平信 20 克) ===")
    p = postage.quote("China")
    check(p.zone == postage.DOMESTIC, "a mainland entity maps to the domestic zone",
          p.zone)
    check(p.cost(postage.DOMESTIC_LOCAL) == 0.80,
          "本埠 is RMB 0.80", str(p.cost(postage.DOMESTIC_LOCAL)))
    check(p.cost(postage.DOMESTIC) == 1.20,
          "外埠 is RMB 1.20", str(p.cost(postage.DOMESTIC)))
    # Mainland China is reported as ONE figure: 1.20.  The 本埠 rate exists and
    # stays available through the API, but a QSL card does not stay in the same
    # city, so the sheet does not make the user choose between two numbers.
    check(p.detail == "国内 1.20",
          "the detail text is the single domestic figure", repr(p.detail))
    check("本埠" not in p.detail and "航空" not in p.detail,
          "no home/air/surface split is shown for mainland China", p.detail)
    check(p.cost(postage.DOMESTIC) == 1.20,
          "the quoted domestic figure is the 外埠 rate", str(p.cost(postage.DOMESTIC)))


def test_hong_kong_macao_taiwan():
    print("\n=== 港澳台 ===")
    for entity in ("Hong Kong", "Macao", "Taiwan"):
        p = postage.quote(entity)
        check(p.zone == postage.HONG_KONG_MACAO_TAIWAN,
              f"{entity} uses the 港澳台 tariff", p.zone)
        check(p.cost("SURFACE") == 1.50,
              f"{entity} 水陆路 is RMB 1.50", str(p.cost("SURFACE")))
        check(p.cost("AIR") == 2.00,
              f"{entity} 航空 is RMB 2.00 (1.50 + 0.50 附加费)",
              str(p.cost("AIR")))


def test_no_postcard_tariff():
    print("\n=== 明信片 tariff is deliberately absent ===")
    check(not hasattr(postage, "postcard_rates"),
          "the module exposes no postcard lookup")
    for name in ("POSTCARD_RATES", "POSTCARD_NOTE", "CLASS_POSTCARD",
                 "CLASSES", "CLASS_LABELS", "HMT_POSTCARD_RATES",
                 "DOMESTIC_POSTCARD"):
        check(not hasattr(postage, name), f"{name} is gone")
    # Nothing the tool reports may mention it either.
    offenders = []
    for entity in ("China", "Hong Kong", "Taiwan", "Japan", "Germany",
                   "Brazil", "Kazakhstan"):
        try:
            p = postage.quote(entity)
        except postage.NotMailable:
            continue
        text = f"{p.detail} {p.note}"
        if "明信片" in text or "postcard" in text.lower():
            offenders.append(entity)
    check(not offenders, "no quoted detail mentions a postcard price",
          str(offenders))


def test_international_zones():
    print("\n=== international letter, 20 g ===")
    # Each entry: entity, zone, AIR, SURFACE, SAL (None when not offered)
    cases = [
        ("Japan", "1", 5.00, 3.50, 4.50),
        ("South Korea", "1", 5.00, 3.50, 4.50),
        ("Kazakhstan", "1", 5.00, 4.00, None),      # SAL not available
        ("Indonesia", "2", 5.50, 3.50, None),       # APUU surface, no SAL
        ("Turkey", "2", 5.50, 4.00, None),
        ("Germany", "3", 6.00, 4.00, 5.50),
        ("United States", "3", 6.00, 4.00, 5.50),
        ("United Kingdom", "3", 6.00, 4.00, 5.50),
        ("Australia", "3", 6.00, 3.50, 5.50),       # APUU surface
        ("Brazil", "4", 7.00, 4.00, 6.50),
        ("South Africa", "4", 7.00, 4.00, None),
        ("Fiji", "4", 7.00, 3.50, None),            # APUU surface
    ]
    for entity, zone, air, surface, sal in cases:
        p = postage.quote(entity)
        problems = []
        if p.zone != zone:
            problems.append(f"zone {p.zone} != {zone}")
        if p.cost("AIR") != air:
            problems.append(f"AIR {p.cost('AIR')} != {air}")
        if p.cost("SURFACE") != surface:
            problems.append(f"SURFACE {p.cost('SURFACE')} != {surface}")
        if p.cost("SAL") != sal:
            problems.append(f"SAL {p.cost('SAL')} != {sal}")
        check(not problems, f"{entity}: zone {zone}, 航空 {air:.2f}, "
                            f"水陆路 {surface:.2f}, SAL "
                            f"{'—' if sal is None else format(sal, '.2f')}",
              "; ".join(problems))

    print("\n=== SAL availability ===")
    check("SAL" not in postage.quote("Kazakhstan").rates,
          "a destination without SAL service has no SAL price")
    check("SAL" not in postage.quote("South Africa").rates,
          "South Africa has no SAL service")
    check("SAL" in postage.quote("Germany").rates,
          "Germany has SAL service")
    check("不通空运水陆路" in postage.quote("Kazakhstan").note,
          "the missing SAL service is stated in the note",
          postage.quote("Kazakhstan").note)


def test_not_mailable():
    print("\n=== 不通邮 ===")
    for entity in ("North Korea", "Antarctica", "Spratly Islands",
                   "Navassa Island", "Midway Island"):
        try:
            postage.quote(entity)
            check(False, f"{entity} is reported as 不通邮", "a price was returned")
        except postage.NotMailable as exc:
            check("不通邮" in str(exc), f"{entity} is reported as 不通邮", str(exc))

    check(postage.is_mailable("North Korea") is False,
          "is_mailable() is False for a non-served destination")
    check(postage.is_mailable("Japan") is True,
          "is_mailable() is True for a served destination")
    check(postage.is_mailable("Never Heard Of It") is None,
          "is_mailable() is None for an unknown entity")


def test_coverage():
    print("\n=== coverage and safety ===")
    names = sorted({e.name for e in dxcc.ENTITIES.values()})
    # An entity needs an ANSWER, not necessarily a price: remote islands with no
    # postal service map to the 不通邮 zone, which is the correct answer for them.
    unmapped = [n for n in names
                if not postage.destination_for_entity(n)
                and postage.is_mailable(n) is None]
    check(not unmapped,
          f"all {len(names)} DXCC entity names have a destination or 不通邮",
          str(unmapped[:8]))

    # A quoted price must be a plain positive number of RMB.
    bad = []
    for name in names:
        try:
            p = postage.quote(name)
        except postage.NotMailable:
            continue
        for service, value in p.rates.items():
            if not isinstance(value, float) or value <= 0:
                bad.append(f"{name}/{service}={value!r}")
    check(not bad, "every price is a positive RMB number", str(bad[:5]))

    # Every non-mailable name must carry an explanatory reason.
    thin = [n for n in postage.NOT_MAILABLE_ENTITIES
            if len(postage.NOT_MAILABLE_ENTITIES[n]) < 4]
    check(not thin, "every 不通邮 entry explains why", str(thin))

    # Provenance must be present, because a price without a date is unusable.
    check(postage.RATES_VERIFIED_ON, "the rate table carries a verification date")
    check(postage.SOURCES.get("domestic") and postage.SOURCES.get("international"),
          "both source tables are cited")


def test_zone_membership():
    print("\n=== zone membership spot checks ===")
    zone3 = ("Germany", "France", "Italy", "Spain", "Poland", "Sweden",
             "United States", "Canada", "Australia", "New Zealand",
             "England", "Scotland", "European Russia", "Asiatic Russia",
             "Kaliningrad")
    wrong = [e for e in zone3 if postage.destination_for_entity(e) != "3"]
    check(not wrong, "Europe / North America / Oceania are zone 3", str(wrong))

    zone1 = ("Japan", "South Korea", "Mongolia", "Vietnam", "Kazakhstan",
             "Kyrgyzstan", "Tajikistan", "Uzbekistan", "Turkmenistan")
    wrong = [e for e in zone1 if postage.destination_for_entity(e) != "1"]
    check(not wrong, "the neighbouring-Asia group is zone 1", str(wrong))

    zone4 = ("Brazil", "Argentina", "South Africa", "Kenya", "Fiji",
             "Mexico", "Peru", "Egypt", "Nigeria")
    wrong = [e for e in zone4 if postage.destination_for_entity(e) != "4"]
    check(not wrong, "the Americas/Africa/Pacific group is zone 4", str(wrong))


def main():
    test_domestic()
    test_hong_kong_macao_taiwan()
    test_no_postcard_tariff()
    test_international_zones()
    test_not_mailable()
    test_coverage()
    test_zone_membership()
    print(f"\n{'=' * 60}")
    print(f"checks: {CHECKS}   failures: {len(FAILURES)}")
    for item in FAILURES:
        print(f"  - {item}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
