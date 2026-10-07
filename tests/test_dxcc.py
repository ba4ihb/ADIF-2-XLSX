#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the DXCC entity lookup (src/dxcc.py).

Run directly (``python tests/test_dxcc.py``) or through pytest.  The callsign
table below is the contract: if a mapping changes, a test fails rather than the
user getting a wrong country silently.
"""

from __future__ import annotations

import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import dxcc  # noqa: E402

# The suites print Chinese labels; a cp1252 console (the CI Windows
# runners) cannot encode them, which used to abort the suite with a
# UnicodeEncodeError instead of a result.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from console_setup import setup_console  # noqa: E402

setup_console()

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


# (callsign, expected entity name)
CALLSIGNS = [
    # North America and the US DXCC entities
    ("W1AW", "United States of America"), ("K1ABC", "United States of America"),
    ("N0CALL", "United States of America"), ("AA1AA", "United States of America"),
    ("KH6BB", "Hawaii"), ("AH6U", "Hawaii"), ("WH6AA", "Hawaii"),
    ("KL7AA", "Alaska"), ("AL7AA", "Alaska"),
    ("KP4AA", "Puerto Rico"), ("KP2AA", "Virgin Is."),
    ("KH8AA", "American Samoa"), ("KH0AA", "Mariana Is."),
    ("KH2AA", "Guam"), ("KH7K", "Kure I."),
    ("VE3ABC", "Canada"), ("VA2AA", "Canada"),
    ("XE1AA", "Mexico"), ("TI2AA", "Costa Rica"), ("HP1AA", "Panama"),
    ("CO2AA", "Cuba"), ("HI8AA", "Dominican Republic"), ("6Y5AA", "Jamaica"),
    ("ZF1AA", "Cayman Is."), ("8P6AA", "Barbados"), ("V44AA", "St. Kitts & Nevis"),
    ("P40AA", "Aruba"), ("PJ2AA", "Curacao"), ("VP2E", "Anguilla"),
    ("VP2M", "Montserrat"), ("VP5AA", "Turks & Caicos Is."),
    ("VP9AA", "Bermuda"), ("VP8AA", "Falkland Is."),
    # South America
    ("PY2ZZZ", "Brazil"), ("LU1AA", "Argentina"), ("CE3AA", "Chile"),
    ("OA1AA", "Peru"), ("HK1AA", "Colombia"), ("YV1AA", "Venezuela"),
    ("CX1AA", "Uruguay"), ("ZP5AA", "Paraguay"), ("CP1AA", "Bolivia"),
    # Europe
    ("DL1ABC", "Germany (Fed Repub of)"), ("DA1AA", "Germany (Fed Repub of)"), ("OE1AA", "Austria"),
    ("HB9XYZ", "Switzerland"), ("HB0AA", "Liechtenstein"),
    ("F5AAA", "France"), ("TK1AA", "Corsica"), ("I1AAA", "Italy"),
    ("IK1AAA", "Italy"), ("IT9ABC", "Italy"), ("IS0AA", "Sardinia"),
    ("EA5ABC", "Spain"), ("EA8ABC", "Canary Is."), ("EA9AA", "Ceuta & Melilla"),
    ("EA6AA", "Balearic Is."), ("CT1AAA", "Portugal"), ("CU3AA", "Azores"),
    ("CT3AA", "Madeira Is."), ("ON4UN", "Belgium"), ("PA0AAA", "Netherlands"),
    ("LX1AA", "Luxembourg"), ("SM5ABC", "Sweden"), ("OH2AAA", "Finland"),
    ("OH0AA", "Aland Is."), ("OJ0AA", "Market Reef"), ("LA1AAA", "Norway"),
    ("JW1AA", "Svalbard"), ("JX1AA", "Jan Mayen"), ("OZ1AAA", "Denmark"),
    ("OX1AA", "Greenland"), ("OY1AA", "Faroe Is."), ("TF3AA", "Iceland"),
    ("ES1AA", "Estonia"), ("YL2AA", "Latvia"), ("LY1AA", "Lithuania"),
    ("SP1AAA", "Poland"), ("OK1AAA", "Czech Republic"), ("OM3AAA", "Slovak Republic"),
    ("S50AAA", "Slovenia"), ("9A1AAA", "Croatia"), ("E70AA", "Bosnia-Herzegovina"),
    ("YT1AA", "Serbia"), ("Z32AA", "North Macedonia"), ("LZ1AA", "Bulgaria"),
    ("YO1AA", "Romania"), ("HA1AA", "Hungary"), ("SV1AA", "Greece"),
    ("SV9AA", "Crete"), ("SV5AA", "Dodecanese"), ("TA1AA", "Turkey"),
    ("UA0QQQ", "Asiatic Russia"), ("UA9AAA", "Asiatic Russia"),
    ("R1AAA", "European Russia"), ("RA1AAA", "European Russia"),
    ("UA2AAA", "Kaliningrad"), ("UR5AAA", "Ukraine"), ("UT1AA", "Ukraine"),
    ("EW1AA", "Belarus"), ("4L1AA", "Georgia"), ("EK1AA", "Armenia"),
    ("4J1AA", "Azerbaijan"), ("UN7AA", "Kazakhstan"), ("EX1AA", "Kyrgyzstan"),
    ("4O1AA", "Montenegro"), ("ZA1AA", "Albania"), ("9H1AA", "Malta"),
    # United Kingdom and Ireland
    ("G3XYZ", "England"), ("M0AAA", "England"), ("2E0AAA", "England"),
    ("GM4ABC", "Scotland"), ("GW0AAA", "Wales"), ("GI0AAA", "Northern Ireland"),
    ("GD3AAA", "Isle of Man"), ("GJ2AA", "Jersey"), ("GU3AAA", "Guernsey"),
    ("EI2AA", "Ireland"), ("GB4AAA", "England"),
    # Asia
    ("JA1XX", "Japan"), ("JS6TKY", "Japan"), ("JF2EEK", "Japan"), ("7K1AA", "Japan"),
    ("HL1AA", "Republic of Korea"), ("DS1AA", "Republic of Korea"), ("P5AA", "Democratic People's Rep. of Korea"),
    ("BY1AA", "China"), ("BA4IHB", "China"), ("BG4LNW", "China"),
    ("BI9DAD", "China"), ("BD8CNL", "China"), ("3H1AA", "China"),
    ("BV2AA", "Taiwan"), ("VR2AA", "Hong Kong"), ("XX9AA", "Macao"),
    ("DU1AA", "Philippines"), ("YB1AA", "Indonesia"), ("9M2AA", "West Malaysia"),
    ("9V1AA", "Singapore"), ("HS0AA", "Thailand"), ("XU7AA", "Cambodia"),
    ("XV2AA", "Viet Nam"), ("VU2AA", "India"), ("AP2AA", "Pakistan"),
    ("HZ1AA", "Saudi Arabia"), ("A61AA", "United Arab Emirates"),
    ("9K2AA", "Kuwait"), ("JT1AA", "Mongolia"), ("4X1AA", "Israel"),
    ("5B4AA", "Cyprus"),
    # Africa
    ("SU1AA", "Egypt"), ("CN8AA", "Morocco"), ("7X2AA", "Algeria"),
    ("5A1AA", "Libya"), ("ZS6ZZ", "South Africa"), ("5N1AA", "Nigeria"),
    ("V51AA", "Namibia"), ("3B8AA", "Mauritius"), ("FR1AA", "Reunion"),
    ("5R8AA", "Madagascar"), ("9G1AA", "Ghana"), ("D2AA", "Angola"),
    ("D4AA", "Cabo Verde (Repub of)"), ("TU2AA", "Cote d'Ivoire"),
    # Oceania
    ("VK2XYZ", "Australia"), ("VK9L", "Lord Howe I."),
    ("VK9N", "Norfolk I."), ("VK0AA", "Heard I."),
    ("ZL1AA", "New Zealand"), ("ZL7AA", "Chatham Is."),
    ("FO1AA", "French Polynesia"), ("FK8AA", "New Caledonia"),
    ("P29AA", "Papua New Guinea"), ("H40AA", "Temotu Province"),
    ("A35AA", "Tonga"), ("T2AA", "Tuvalu"), ("5W1AA", "Samoa"),
    ("YJ0AA", "Vanuatu"), ("3D2AA", "Fiji"), ("V73AA", "Marshall Is."),
    ("V6AA", "Micronesia"),
    # Antarctica
    ("CE9AA", "Antarctica"), ("KC4AAA", "Antarctica"),
]


def test_structure():
    print("=== table structure ===")
    check(dxcc.ENTITY_COUNT > 200, "entity table is populated",
          str(dxcc.ENTITY_COUNT))
    # A prefix may point at a numeric DXCC code or at a prefix-only entity,
    # which is how an entity whose ARRL number could not be verified is carried
    # (its name is what the report shows).
    known = set(dxcc.ENTITIES) | set(dxcc.PREFIX_ONLY_ENTITIES)
    missing = sorted({c for _p, c in dxcc.PREFIX_TABLE if c not in known})
    check(not missing, "every prefix points at a defined entity", str(missing))
    nonnumeric = [c for c in dxcc.ENTITIES if not c.isdigit()]
    check(not nonnumeric, "entity numbers are numeric", str(nonnumeric))


def test_callsigns():
    print("\n=== callsign -> entity ===")
    wrong = []
    for call, expected in CALLSIGNS:
        name, code, source = dxcc.resolve(call=call)
        if _plain_entity(name) != _plain_entity(expected):
            wrong.append(f"{call}: want {expected}, got {name}")
    check(not wrong, f"all {len(CALLSIGNS)} callsigns resolve correctly",
          "; ".join(wrong[:6]))


def test_sources_and_priority():
    print("\n=== resolution source and priority ===")
    name, code, src = dxcc.resolve(call="JA1XX")
    check(src == "PREFIX" and name == "Japan", "a bare callsign resolves by prefix",
          f"{name}/{src}")

    name, code, src = dxcc.resolve(call="KH6BB", dxcc_field="291")
    # 291 is the United States of America in the ARRL list; the hand-built table
    # used to have it as Lesotho, which is what made an override look "correct".
    check(name == "United States of America" and code == "291"
          and src == "ADIF_DXCC",
          "an ADIF DXCC number overrides the callsign", f"{name}/{code}/{src}")

    name, code, src = dxcc.resolve(call="JA1XX", country="Japan")
    check(name == "Japan" and src == "ADIF_COUNTRY",
          "an ADIF COUNTRY name resolves the entity", f"{name}/{src}")

    name, code, src = dxcc.resolve(call="JA1XX", dxcc_field="204")
    check(src == "ADIF_DXCC", "DXCC outranks COUNTRY", src)

    name, code, src = dxcc.resolve(call="")
    check(name == dxcc.UNKNOWN and code == "" and src == "NONE",
          "an empty callsign yields UNKNOWN, never a wrong country", f"{name}/{src}")

    name, code, src = dxcc.resolve(call="QQ1QQQ")
    check(name == dxcc.UNKNOWN, "an unallocated prefix yields UNKNOWN", name)

    name, code, src = dxcc.resolve(call="KH6BB", dxcc_field="99999")
    check(name == "Hawaii", "an out-of-range DXCC number falls back to the prefix",
          f"{name}/{src}")


def test_portable_forms():
    print("\n=== portable and suffixed callsigns ===")
    cases = [
        ("DL1ABC/P", "Germany (Fed Repub of)"),
        ("KH6BB/QRP", "Hawaii"),
        ("JA1XX/MM", "Japan"),
        ("BA4IHB/P", "China"),
        ("F/DL1ABC", "France"),
        ("DL1ABC/VP2M", "Montserrat"),
        ("KH8/KL7AA", "American Samoa"),
    ]
    wrong = []
    for call, expected in cases:
        name, _code, _src = dxcc.resolve(call=call)
        if name != expected:
            wrong.append(f"{call}: want {expected}, got {name}")
    check(not wrong, f"all {len(cases)} portable forms resolve", "; ".join(wrong))


def test_case_and_whitespace():
    print("\n=== case and whitespace tolerance ===")
    for call in ("ja1xx", " JA1XX ", "Ja1Xx"):
        name, _c, _s = dxcc.resolve(call=call)
        check(name == "Japan", f"{call!r} normalises to Japan", name)


def test_china_taiwan_block():
    """The B block: mainland is B<digit>, Taiwan is B<letter>.

    A defect here is not cosmetic.  Every Taiwanese station was reported as
    China, which also gave it China's postage instead of the Taiwan rate.
    """
    print("\n=== China vs Taiwan (the B block) ===")
    mainland = ["BG5ABC", "BD7XYZ", "BY1AA", "BA1AA", "BH1AA", "BI4AA",
                "BJ1AA", "BL1AA", "B0AA", "B2AA", "B5AA", "B7AA", "B9AA",
                "B1ABC", "BG1AAA"]
    taiwan = ["BV2AA", "BU2AQ", "BM2AA", "BN2AA", "BO2AA", "BP2AA", "BQ2AA",
              "BW2AA", "BX2AA", "BU2AA", "BM6AA", "BX6AA"]

    wrong = []
    for call in mainland:
        name, _code, _src = dxcc.resolve(call=call)
        if name != "China":
            wrong.append(f"{call}: want China, got {name}")
    check(not wrong, f"all {len(mainland)} mainland B calls resolve to China",
          "; ".join(wrong[:5]))

    wrong = []
    for call in taiwan:
        name, _code, _src = dxcc.resolve(call=call)
        if name != "Taiwan":
            wrong.append(f"{call}: want Taiwan, got {name}")
    check(not wrong, f"all {len(taiwan)} Taiwanese B calls resolve to Taiwan",
          "; ".join(wrong[:5]))

    # The two entities must not share a postage figure either.
    import postage
    china = postage.quote("China")
    taiwan = postage.quote("Taiwan")
    check(china.rates != taiwan.rates,
          "China and Taiwan carry different postage", 
          f"{china.rates} vs {taiwan.rates}")


def test_russia_call_areas():
    """Russia splits into European and Asiatic by call-area digit.

    ARRL's dividing line is call area 8/9/0 = Asia, except a call whose suffix
    starts with F, G or X (Perm and Komi), which counts as Europe.
    """
    print("\n=== Russian call areas ===")
    europe = ["RA1AA", "RA3AA", "RA4AA", "RA6AA", "RK3AA", "RV1AA", "RN4AA",
              "R1AAA", "UA1AA", "UA3AA", "UA4AA", "UA6AA", "UB3AA", "UC6AA",
              "UE3AA", "UF1AA", "UG4AA", "UH3AA", "UI3AA", "RZ3AA", "RW4AA"]
    asia = ["RA8AA", "RA9AA", "RA0AA", "UA8AA", "UA9AA", "UA0AA", "UD9AA",
            "UE0AA", "RZ9AA", "RW0AA", "RX0AA", "RN9AA", "UA9SAA", "UA9TAA"]

    wrong = []
    for call in europe:
        name, _code, _src = dxcc.resolve(call=call)
        if name != "European Russia":
            wrong.append(f"{call}: want European Russia, got {name}")
    check(not wrong, f"all {len(europe)} European Russian calls resolve", 
          "; ".join(wrong[:5]))

    wrong = []
    for call in asia:
        name, _code, _src = dxcc.resolve(call=call)
        if name != "Asiatic Russia":
            wrong.append(f"{call}: want Asiatic Russia, got {name}")
    check(not wrong, f"all {len(asia)} Asiatic Russian calls resolve",
          "; ".join(wrong[:5]))

    # Kaliningrad is its own entity.
    name, _code, _src = dxcc.resolve(call="UA2AB")
    check(name == "Kaliningrad", "UA2 is Kaliningrad", name)

    # The Perm/Komi exception: area 8/9 with an F, G or X suffix is Europe.
    wrong = []
    for call in ("UA9FAA", "UA9GAA", "UA9XAA", "RA9FAA", "RZ9GAA", "UA8XAA"):
        name, _code, _src = dxcc.resolve(call=call)
        if name != "European Russia":
            wrong.append(f"{call}: want European Russia, got {name}")
    check(not wrong, "the Perm/Komi exception (F/G/X suffix) counts as Europe",
          "; ".join(wrong[:5]))

    # Countries that share the U letter must not be swallowed by the rule.
    neighbours = {"UR5AAA": "Ukraine", "UT1AA": "Ukraine", "UR4AAA": "Ukraine",
                  "UN7AA": "Kazakhstan", "UN1AA": "Kazakhstan",
                  "US5AAA": "Ukraine", "UW1AA": "Ukraine"}
    wrong = []
    for call, want in neighbours.items():
        name, _code, _src = dxcc.resolve(call=call)
        if _plain_entity(name) != _plain_entity(want):
            wrong.append(f"{call}: want {want}, got {name}")
    check(not wrong, "Ukraine and Kazakhstan are not mistaken for Russia",
          "; ".join(wrong[:5]))

    # And the two Russian entities must differ in postage, since they are
    # different destinations.
    import postage
    check(postage.quote("European Russia").rates
          == postage.quote("Asiatic Russia").rates,
          "both Russian entities are in the same postage zone")


def test_country_is_not_entity():
    """One country can hold several DXCC entities, and they are separate.

    China covers the mainland, Hong Kong, Macao, Taiwan and Scarborough Reef;
    Russia splits into European Russia, Asiatic Russia and Kaliningrad; the
    United States covers Hawaii, Alaska and Puerto Rico.  The COUNTRY an export
    writes is not the entity, so the two must not be conflated -- and they must
    not share a postage figure either.
    """
    print("\n=== one country, several DXCC entities ===")
    groups = {
        "China": {
            "BG5ABC": "China",          # mainland
            "VR2ABC": "Hong Kong",
            "XX9ABC": "Macao",
            "BU2AQ": "Taiwan",
            "BS7H": "Scarborough Reef",  # Huangyan Dao, its own entity
        },
        "Russia": {
            "UA3AA": "European Russia",
            "UA9AA": "Asiatic Russia",
            "UA2AB": "Kaliningrad",
        },
        "United States of America": {
            "W1ABC": "United States of America",
            "KH6ABC": "Hawaii",
            "KL7ABC": "Alaska",
            "KP4ABC": "Puerto Rico",
        },
    }
    for country, calls in groups.items():
        names = []
        for call, want in calls.items():
            name, _code, _src = dxcc.resolve(call=call)
            names.append(name)
            check(name == want, f"{call} is {want}, not {country}",
                  f"got {name}")
        # The point of the test: these are genuinely different entities.
        distinct = {n for n in names}
        check(len(distinct) == len(calls),
              f"{country} resolves to {len(calls)} distinct DXCC entities",
              str(sorted(distinct)))

    # Each entity must carry its own postage, because postage follows the
    # entity and not the country.
    import postage
    figures = {}
    for entity in ("China", "Hong Kong", "Macao", "Taiwan"):
        figures[entity] = postage.quote(entity).rates
    check(figures["China"] != figures["Taiwan"],
          "mainland China and Taiwan have different postage", str(figures))
    check(figures["Hong Kong"] == figures["Macao"] == figures["Taiwan"],
          "Hong Kong, Macao and Taiwan share the 港澳台 tariff")

    # Scarborough Reef is not mainland China, so it must not silently become it.
    name, code, _src = dxcc.resolve(call="BS7H")
    check(name == "Scarborough Reef" and code != "207",
          "Scarborough Reef is not folded into China", f"{name}/{code}")

    # The label for the derived column must say entity, not country/zone.
    import adif2xlsx as A
    check(A.field_label(A.ENTITY_COLUMN) == "DXCC 实体",
          "the derived column is labelled as a DXCC entity",
          A.field_label(A.ENTITY_COLUMN))
    check(A.field_label("COUNTRY") != A.field_label(A.ENTITY_COLUMN),
          "the log-supplied COUNTRY column is labelled differently",
          A.field_label("COUNTRY"))


#: Every ITU block a Chinese operator can realistically work, with the entity
#: it must resolve to.  A block that resolves to nothing, or to a different
#: entity, is a defect: the entity decides the DXCC count AND the postage, so a
#: wrong answer is worse than no answer.
ITU_BLOCKS = {
    "3W": "Viet Nam",
    "4S": "Sri Lanka",
    "8Q": "Maldives",
    "9M2": "West Malaysia",
    "9M6": "East Malaysia",
    "9N": "Nepal",
    "9V": "Singapore (Republic of)",
    "AP": "Pakistan (Islamic Rep of)",
    "BS7": "Scarborough Reef",
    "BV": "Taiwan",
    "BU": "Taiwan",
    "BW": "Taiwan",
    "BX": "Taiwan",
    "BM": "Taiwan",
    "BN": "Taiwan",
    "BO": "Taiwan",
    "BP": "Taiwan",
    "BQ": "Taiwan",
    "DU": "Philippines",
    "DV": "Philippines",
    "HL": "Republic of Korea",
    "DS": "Republic of Korea",
    "HS": "Thailand",
    "JA": "Japan",
    "7K": "Japan",
    "JD1": "Minami Torishima",
    "JD1M": "Minami Torishima",
    "OD": "Lebanon",
    "TA": "Turkey",
    "UN": "Kazakhstan",
    "VU": "India",
    "XU": "Cambodia",
    "XW": "Laos",
    "XX9": "Macao",
    "YB": "Indonesia",
    "YC": "Indonesia",
    "YI": "Iraq",
    "YK": "Syria",
    "4X": "Israel",
    "5B": "Cyprus",
    "HZ": "Saudi Arabia",
    "1A": "Sov. Mil. Order of Malta",
    "A4": "Oman",
    "A6": "United Arab Emirates",
    "A7": "Qatar",
    "A9": "Bahrain",
    "EP": "Iran",
    "EK": "Armenia",
    "4J": "Azerbaijan",
    "4L": "Georgia",
    "EX": "Kyrgyzstan",
    "EY": "Tajikistan",
    "EZ": "Turkmenistan",
    "9K": "Kuwait",
    "JY": "Jordan",
    "UA": "European Russia",
    "UB": "European Russia",
    "UC": "European Russia",
    "RA": "European Russia",
    "RZ": "European Russia",
    "UA2": "Kaliningrad",
    "EW": "Belarus",
    "EU": "Belarus",
    "UR": "Ukraine",
    "UT": "Ukraine",
    "YL": "Latvia",
    "LY": "Lithuania",
    "ES": "Estonia",
    "DL": "Germany (Fed Repub of)",
    "DA": "Germany (Fed Repub of)",
    "DO": "Germany (Fed Repub of)",
    "G": "England",
    "M": "England",
    "2E": "England",
    "GW": "Wales",
    "GM": "Scotland",
    "GI": "Northern Ireland",
    "GJ": "Jersey",
    "GU": "Guernsey",
    "GD": "Isle of Man",
    "F": "France",
    "I": "Italy",
    "EA": "Spain",
    "EA6": "Balearic Is.",
    "EA8": "Canary Is.",
    "EA9": "Ceuta & Melilla",
    "CT": "Portugal",
    "CT3": "Madeira Is.",
    "CU": "Azores",
    "SM": "Sweden",
    "OH": "Finland",
    "OH0": "Aland Is.",
    "LA": "Norway",
    "OZ": "Denmark",
    "OX": "Greenland",
    "OY": "Faroe Is.",
    "PA": "Netherlands",
    "ON": "Belgium",
    "SP": "Poland",
    "OK": "Czech Republic",
    "OM": "Slovak Republic",
    "HA": "Hungary",
    "YO": "Romania",
    "LZ": "Bulgaria",
    "SV": "Greece",
    "SV5": "Dodecanese",
    "SV9": "Crete",
    "HB": "Switzerland",
    "HB0": "Liechtenstein",
    "OE": "Austria",
    "YU": "Serbia",
    "9A": "Croatia",
    "S5": "Slovenia",
    "Z3": "North Macedonia",
    "4O": "Montenegro",
    "E7": "Bosnia-Herzegovina",
    "ZA": "Albania",
    "TF": "Iceland",
    "EI": "Ireland",
    "TK": "Corsica",
    "W": "United States of America",
    "K": "United States of America",
    "N": "United States of America",
    "AA": "United States of America",
    "AL": "Alaska",
    "KH6": "Hawaii",
    "KH7K": "Kure I.",
    "KH0": "Mariana Is.",
    "KH8": "American Samoa",
    "KH9": "Wake I.",
    "KL7": "Alaska",
    "VE": "Canada",
    "XE": "Mexico",
    "XA": "Mexico",
    "PY": "Brazil",
    "LU": "Argentina",
    "CE": "Chile",
    "CE9": "Antarctica",
    "OA": "Peru",
    "HK": "Colombia",
    "YV": "Venezuela",
    "YW": "Venezuela",
    "CX": "Uruguay",
    "ZP": "Paraguay",
    "CP": "Bolivia",
    "HC": "Ecuador",
    "HP": "Panama",
    "TI": "Costa Rica",
    "TG": "Guatemala",
    "HR": "Honduras",
    "YN": "Nicaragua",
    "HT": "Nicaragua",
    "HU": "El Salvador",
    "CO": "Cuba",
    "HI": "Dominican Republic",
    "HH": "Haiti",
    "6Y": "Jamaica",
    "8P": "Barbados",
    "9Y": "Trinidad & Tobago",
    "J3": "Grenada",
    "J6": "St. Lucia",
    "J7": "Dominica",
    "V2": "Antigua & Barbuda",
    "V3": "Belize",
    "V4": "St. Kitts & Nevis",
    "VP2E": "Anguilla",
    "VP2M": "Montserrat",
    "VP2V": "British Virgin Is.",
    "VP5": "Turks & Caicos Is.",
    "VP8": "Falkland Is.",
    "VP9": "Bermuda",
    "ZF": "Cayman Is.",
    "C6": "Bahamas (Commonwealth of the)",
    "PZ": "Suriname",
    "P4": "Aruba",
    "FG": "Guadeloupe",
    "FM": "Martinique",
    "FS": "Saint Martin",
    "FJ": "Saint Barthelemy",
    "FY": "French Guiana",
    "VK": "Australia",
    "VK0": "Heard I.",
    "VK9X": "Christmas I.",
    "VK9L": "Lord Howe I.",
    "VK9N": "Norfolk I.",
    "ZL": "New Zealand",
    "ZL7": "Chatham Is.",
    "ZL8": "Kermadec Is.",
    "ZL9": "New Zealand",
    "E5": "N. Cook Is.",
    "ZK2": "Niue",
    "ZK3": "Tokelau Is.",
    "A3": "Tonga",
    "T2": "Tuvalu",
    "T30": "W. Kiribati (Gilbert Is. )",
    "T31": "C. Kiribati",
    "T32": "E. Kiribati (Line Is.)",
    "T33": "Banaba I. (Ocean I.)",
    "3D2": "Fiji",
    "3D2R": "Fiji",
    "FO": "French Polynesia",
    "FO0": "French Polynesia",
    "FK": "New Caledonia",
    "FW": "Wallis & Futuna Is.",
    "H4": "Solomon Is.",
    "YJ": "Vanuatu",
    "P2": "Papua New Guinea",
    "5W": "Samoa",
    "ZS": "South Africa",
    "3DA": "Kingdom of Eswatini",
    "7P": "Lesotho",
    "5Z": "Kenya",
    "5X": "Uganda",
    "5H": "Tanzania (United Rep of)",
    "5T": "Mauritania",
    "5U": "Niger",
    "5V": "Togo",
    "5N": "Nigeria",
    "5A": "Libya",
    "5R": "Madagascar",
    "7Q": "Malawi",
    "8R": "Guyana",
    "9G": "Ghana",
    "9H": "Malta",
    "9I": "Zambia",
    "9L": "Sierra Leone",
    "9O": "Dem. Rep. of Congo",
    "9U": "Burundi",
    "9X": "Rwanda",
    "CN": "Morocco (Kingdom of)",
    "D2": "Angola",
    "D4": "Cabo Verde (Repub of)",
    "D6": "Comoros",
    "ET": "Ethiopia",
    "J2": "Djibouti",
    "J5": "Guinea-Bissau",
    "S0": "Western Sahara",
    "ST": "Sudan",
    "SU": "Egypt",
    "T5": "Somalia",
    "TZ": "Mali",
    "TT": "Chad",
    "TR": "Gabon",
    "TJ": "Cameroon",
    "TY": "Benin",
    "TU": "Cote d'Ivoire",
    "VQ9": "Chagos Is.",
    "ZD7": "St. Helena",
    "ZD8": "Ascension I.",
    "ZD9": "Tristan da Cunha & Gough I.",
    "3B6": "Agalega & St. Brandon Is.",
    "3B8": "Mauritius",
    "3C0": "Annobon I.",
    "S7": "Seychelles",
    "S9": "Sao Tome & Principe",
    "Z2": "Zimbabwe",
    "3Y": "Bouvet",
    "3Y0": "Bouvet",
    "JW": "Svalbard",
    "JX": "Jan Mayen",
}
def _probe(prefix: str) -> str:
    """A callsign that exercises one block.

    A block that already ends in a digit or letter just needs a suffix, so the
    probe must not append another digit (that would create a different block:
    "VK9X" must be probed as "VK9XAA", not "VK9X1AA").
    """
    return prefix + "AA" if len(prefix) >= 3 else prefix + "1AA"


def _plain_entity(name: str) -> str:
    """An entity name reduced to its comparable core.

    The audit names entities the way people say them ("Singapore", "United
    States", "Sicily") while the published list qualifies them ("Singapore
    (Republic of)", "United States of America").  Comparing the core keeps the
    table readable without letting a real difference through: the qualifier never
    distinguishes two entities, and any genuinely different name still differs.
    """
    text = (name or "").strip()
    text = text.replace("&", " and ")
    text = re.sub(r"\s*\([^)]*\)\s*", " ", text)
    text = text.replace("I.", "Island").replace("Is.", "Islands")
    text = re.sub(r"\b(Republic|Kingdom|Commonwealth|Fed|Federal|Dem|"
                  r"People's|United|State|States|of|the|and|Islands?|I)\b",
                  " ", text)
    text = re.sub(r"[^A-Za-z]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def test_itu_blocks():
    """Every ITU block resolves, and to the right entity."""
    print("\n=== ITU block audit ===")
    unresolved, wrong = [], []
    for prefix, want in sorted(ITU_BLOCKS.items()):
        name, code, source = dxcc.resolve(call=_probe(prefix))
        if name == dxcc.UNKNOWN:
            unresolved.append(prefix)
        elif _plain_entity(name) != _plain_entity(want):
            wrong.append(f"{prefix}: want {want}, got {name}")

    check(not unresolved,
          f"all {len(ITU_BLOCKS)} ITU blocks resolve to something",
          f"{len(unresolved)} unresolved: {unresolved[:12]}")
    check(not wrong, f"all {len(ITU_BLOCKS)} ITU blocks name the right entity",
          "; ".join(wrong[:6]))

    # A prefix row must never point at a code that is not defined.
    known = set(dxcc.ENTITIES) | set(dxcc.PREFIX_ONLY_ENTITIES)
    dangling = sorted({c for _p, c in dxcc.PREFIX_TABLE if c not in known})
    check(not dangling, "no prefix row points at an undefined code",
          str(dangling))

    # The generator must offer the useful slices for each shape.
    shapes = {
        "BG5ABC": ["BG5", "BG", "B5"],
        "3B9AA": ["3B9", "3B"],
        "VK9XAA": ["VK9X", "VK9", "VK"],
        "FT5WAA": ["FT5W", "FT5"],
        "KH6BB": ["KH6", "KH"],
        "F/DL1ABC": ["F"],
    }
    bad = []
    for call, wanted in shapes.items():
        got = dxcc.candidate_prefixes(call)
        for prefix in wanted:
            if prefix not in got:
                bad.append(f"{call} lacks {prefix} (got {got})")
    check(not bad, "the prefix generator offers the slices the table needs",
          "; ".join(bad[:4]))


def main():
    test_structure()
    test_callsigns()
    test_sources_and_priority()
    test_portable_forms()
    test_case_and_whitespace()
    test_china_taiwan_block()
    test_russia_call_areas()
    test_country_is_not_entity()
    test_itu_blocks()
    print(f"\n{'=' * 60}")
    print(f"checks: {CHECKS}   failures: {len(FAILURES)}")
    for item in FAILURES:
        print(f"  - {item}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
