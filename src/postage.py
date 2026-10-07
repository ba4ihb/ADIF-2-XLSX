#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QSL card postage from mainland China (China Post 中国邮政).

Answers, for a destination DXCC entity: what does it cost to mail a QSL card as
an ordinary letter (平信) at the reference weight, and which service classes are
available —

  * 航空        AIR      air mail
  * 水陆路      SURFACE  surface mail (sea and land)
  * 空运水陆路  SAL      surface air lifted

— or 不通邮 where China Post does not accept ordinary letters.

Only the LETTER tariff (信函) is reported.  China Post also publishes a separate
明信片 (postcard) tariff, which is deliberately not modelled: it is a flat price
with no published route list, so quoting it per destination would promise an
availability that cannot be verified.  A QSL card posted in an envelope is a
letter, which is the case this tool is built around.

Rates change
------------
Postal tariffs are set by published notice and revised occasionally.  Every
figure below cites the official table it came from in ``SOURCES``, and
``RATES_VERIFIED_ON`` records when this file was last checked.  The tool prints
that date next to every price.  Before trusting a number for anything that
matters, compare it with the current China Post notice and update ``DOMESTIC``,
``HONG_KONG_MACAO_TAIWAN`` and ``INTERNATIONAL`` below.

Historical rate tables, for reference when updating:
  * 国内 + 港澳台  国家邮政局《邮政基本资费表》 (see SOURCES["domestic"])
  * 国际函件       《国际函件资费表》 (see SOURCES["international"])
"""

from __future__ import annotations

import re

from typing import Dict, NamedTuple, Optional

__all__ = [
    "RATES_VERIFIED_ON", "SOURCES", "REFERENCE_WEIGHT_G", "SERVICES",
    "SERVICE_LABELS", "DOMESTIC", "DOMESTIC_LOCAL", "HONG_KONG_MACAO_TAIWAN",
    "NOT_MAILABLE", "DESTINATIONS", "Postage", "NotMailable", "quote",
    "is_mailable", "destination_for_entity", "describe_rates",
]

# ---------------------------------------------------------------------------
# Provenance.  Shown to the user beside every price.
# ---------------------------------------------------------------------------
RATES_VERIFIED_ON = "2026-10"
RATES_EFFECTIVE_FROM = "2018-12-07"

SOURCES = {
    "domestic":
        "国家邮政局《邮政基本资费表》(2016) — 甘肃省邮政管理局 table "
        "(https://gs.spb.gov.cn/gssyzglj/c103910/c103912/201612/"
        "fd532f490a3a44268a0bfbb13e2bb173.shtml)",
    "international":
        "中国邮政《国际函件资费表》 (2018-12-07 起执行, published 2019-10-29) "
        "(https://www.chinapost.com.cn/cn/report/1910/11959-1.html)",
}

# A QSL card plus its envelope sits inside the first weight step.
REFERENCE_WEIGHT_G = 20

SERVICES = ("AIR", "SURFACE", "SAL")
SERVICE_LABELS = {"AIR": "航空", "SURFACE": "水陆路", "SAL": "空运水陆路"}

DOMESTIC = "DOMESTIC"
DOMESTIC_LOCAL = "LOCAL"
HONG_KONG_MACAO_TAIWAN = "HMT"
NOT_MAILABLE = "NOT_MAILABLE"

NO_SERVICE = "—"


class NotMailable(Exception):
    """Raised for a destination China Post does not serve."""

    def __init__(self, message: str, reason: str = "") -> None:
        super().__init__(message)
        self.reason = reason or message


class Postage(NamedTuple):
    """One destination's postal answer at the reference weight."""

    destination: str                  # human-facing destination label
    zone: str                         # rate zone key, "" when unknown
    rates: Dict[str, float]           # service key -> RMB
    mailable: bool
    note: str = ""
    detail: str = ""                  # ready-to-display breakdown

    def cost(self, service: str = "AIR") -> Optional[float]:
        return self.rates.get(service)


# ---------------------------------------------------------------------------
# 1. Mainland China — 国内普通邮件资费, 信函 首重100克内每重20克
#    本埠（县）= within the city districts; 外埠 = elsewhere in mainland China.
# ---------------------------------------------------------------------------
DOMESTIC_RATES: Dict[str, float] = {
    DOMESTIC_LOCAL: 0.80,   # 本埠 0.8 元
    DOMESTIC: 1.20,         # 外埠 1.2 元
}
DOMESTIC_NOTE = "国内平信 20 克以内"
# Weight beyond the base step is charged per additional 20 g up to 100 g.
DOMESTIC_ADDITIONAL = {"LOCAL": (20, 0.80), "DOMESTIC": (20, 1.20)}

# ---------------------------------------------------------------------------
# 2. Hong Kong, Macao, Taiwan — 港澳台地区邮件资费, 信函
#    1.50 元 for the first 20 g by surface; air adds 航空附加费 0.50 元/10 g.
# ---------------------------------------------------------------------------
HMT_RATES: Dict[str, float] = {"SURFACE": 1.50, "AIR": 2.00}
HMT_NOTE = "港澳台信函 20 克及以下（航空含每 10 克航空附加费 0.50 元）"
# 寄达台湾只收取平常小包，暂不办理挂号业务 (registration not available to Taiwan).
HMT_REGISTRATION_NOTE = {
    "TW": "寄达台湾只收平常小包，暂不办理挂号业务",
}

# ---------------------------------------------------------------------------
# 3. International — 《国际函件资费表》信函, 20 克和 20 克以内, 单位: 元
#
#    Zone 1 部分亚洲邻国（朝鲜、蒙古、越南、日本、韩国、哈萨克斯坦、
#                        吉尔吉斯斯坦、塔吉克斯坦、乌兹别克斯坦、土库曼斯坦）
#    Zone 2 其他亚洲国家或地区
#    Zone 3 欧洲各国或地区、美国、加拿大、澳大利亚、新西兰
#    Zone 4 美洲其他国家或地区、非洲各国或地区、太平洋岛屿
#
# The zone is the rating mechanism behind the price; it is reported separately
# as Postage.zone and deliberately kept out of the price breakdown.
# ---------------------------------------------------------------------------
INTERNATIONAL_RATES: Dict[str, Dict[str, float]] = {
    "1": {"AIR": 5.00, "SAL": 4.50, "SURFACE": 4.00},
    "2": {"AIR": 5.50, "SAL": 5.00, "SURFACE": 4.00},
    "3": {"AIR": 6.00, "SAL": 5.50, "SURFACE": 4.00},
    "4": {"AIR": 7.00, "SAL": 6.50, "SURFACE": 4.00},
}
# 水陆路 has a reduced tariff for 27 Asia-Pacific routes.
SURFACE_APPU_RATE = 3.50

# Continuation per additional 10 g (20 克以上每续重 10 克或其零数加收).
INTERNATIONAL_ADDITIONAL: Dict[str, Dict[str, float]] = {
    "1": {"AIR": 1.00, "SAL": 0.50},
    "2": {"AIR": 1.50, "SAL": 0.60},
    "3": {"AIR": 1.80, "SAL": 0.70},
    "4": {"AIR": 2.30, "SAL": 0.80},
}
INTERNATIONAL_SURFACE_ADDITIONAL = 0.50

# 水陆路亚太地区减低资费 applies to these Asia-Pacific Postal Union members.
APPU_REDUCED_SURFACE = frozenset({
    "Afghanistan", "Australia", "Bhutan", "Bangladesh", "Brunei Darussalam",
    "Cambodia", "Fiji", "India", "Indonesia", "Iran", "Japan", "South Korea",
    "Laos", "Malaysia", "Maldives", "Myanmar", "Nauru", "Nepal",
    "New Zealand", "Pakistan", "Papua New Guinea", "Philippines", "Singapore",
    "Solomon Islands", "Sri Lanka", "Thailand", "Vietnam",
})

# 空运水陆路 (SAL) is not offered everywhere.  Only these destinations are
# served; anything absent is reported as "not available" rather than priced.
SAL_AVAILABLE = frozenset({
    # 第一组
    "South Korea", "Japan",
    # 第二组
    "Cyprus",
    # 第三组
    "Armenia", "Azerbaijan", "Georgia", "Albania", "Germany", "Andorra",
    "Austria", "Belarus", "Belgium", "Bosnia and Herzegovina", "Bulgaria",
    "Croatia", "Denmark", "Spain", "Estonia", "Faroe Islands", "Finland",
    "France", "Gibraltar", "United Kingdom", "England", "Scotland", "Wales",
    "Northern Ireland", "Isle of Man", "Jersey", "Guernsey", "Greece",
    "Hungary", "Ireland", "Iceland", "Italy", "Latvia", "Liechtenstein",
    "Lithuania", "Luxembourg", "North Macedonia", "Malta", "Moldova",
    "Monaco", "Norway", "Netherlands", "Poland", "Portugal", "San Marino",
    "Romania", "European Russia", "Asiatic Russia", "Kaliningrad",
    "Slovak Republic", "Slovenia", "Sweden", "Switzerland", "Czech Republic",
    "Ukraine", "Vatican City", "Serbia", "Montenegro", "United States",
    "Canada", "Australia",
    # 第四组
    "Comoros", "Azores", "Madeira Islands", "Lesotho",
    "Sao Tome and Principe", "Anguilla", "Ascension Island", "Bolivia",
    "Brazil", "Greenland", "Bermuda", "Tristan da Cunha and Gough Islands",
    "United States Virgin Islands", "Paraguay", "Puerto Rico",
    # Russia is one postal destination; SAL covers it in full.
    "Russia",
})

# ---------------------------------------------------------------------------
# Destinations China Post does not serve with ordinary letters.
#
# Kept deliberately short and evidence-based: only well-established cases are
# listed, because wrongly declaring a destination unreachable is worse than
# leaving its price blank.  Countries that China Post serves only intermittently
# are reported through their zone instead.
# ---------------------------------------------------------------------------
NOT_MAILABLE_ENTITIES: Dict[str, str] = {
    "4U_ITU ITU HQ": "无法投递：国际电信联盟总部，属外交机构而非邮政目的地",
    "4U_ITU#* ITU HQ": "无法投递：国际电信联盟总部，属外交机构而非邮政目的地",
    "ITU HQ": "无法投递：国际电信联盟总部，属外交机构而非邮政目的地",
    "Antarctica": "不通邮：南极无普通邮政投递服务，QSL 须经本国管理机构转递",
    "Aves I.": "不通邮：阿维斯岛无常住人口与邮政服务",
    "Aves Island": "不通邮：阿维斯岛无常住人口与邮政服务",
    "Baker and Howland Islands": "不通邮：无人岛，无邮政服务",
    "Bear Island": "不通邮：无常住人口和邮政服务",
    "Bouvet": "不通邮：南极布韦岛无常住人口与邮政服务",
    "Bouvet Island": "不通邮：南极布韦岛无常住人口与邮政服务",
    "Chesterfield Is.": "不通邮：切斯特菲尔德群岛无常住人口与邮政服务",
    "Chesterfield Islands": "不通邮：切斯特菲尔德群岛无常住人口与邮政服务",
    "Clipperton Island": "不通邮：无人岛，无邮政服务",
    "Conway Reef": "不通邮：康韦礁为无人珊瑚礁，无邮政服务",
    "Desecheo I.": "不通邮：德塞切奥岛为无人岛，无邮政服务",
    "Desecheo Island": "不通邮：德塞切奥岛为无人岛，无邮政服务",
    "Ducie I.": "不通邮：迪西岛无常住人口与邮政服务",
    "Ducie Island": "不通邮：迪西岛无常住人口与邮政服务",
    "Franz Josef Land": "不通邮：无常住人口和邮政服务",
    "Guantanamo Bay": "不通邮：军事基地，无民用邮政服务",
    "Heard I.": "不通邮：南极赫德岛无常住人口与邮政服务",
    "Heard Island": "不通邮：南极赫德岛无常住人口与邮政服务",
    "Johnston Atoll": "不通邮：无常住人口和邮政服务",
    "Johnston I.": "不通邮：约翰斯顿环礁无常住人口与邮政服务",
    "Johnston Island": "不通邮：约翰斯顿环礁无常住人口与邮政服务",
    "K1 South Shetland Is.": "不通邮：南设得兰群岛为南极科考区，无邮政服务",
    "K1* South Shetland Is.": "不通邮：南设得兰群岛为南极科考区，无邮政服务",
    "Kingman Reef": "不通邮：金曼礁为无人珊瑚礁，无邮政服务",
    "Kure Atoll": "不通邮：无人礁，无邮政服务",
    "Kure I.": "不通邮：库雷环礁无常住人口与邮政服务",
    "Macquarie I.": "不通邮：麦夸里岛为南极科考保护区，无邮政服务",
    "Macquarie Island": "不通邮：麦夸里岛为南极科考保护区，无邮政服务",
    "Malpelo I.": "不通邮：马尔佩洛岛为无人岛，无邮政服务",
    "Malpelo Island": "不通邮：马尔佩洛岛为无人岛，无邮政服务",
    "Market Reef": "不通邮：无人礁，无邮政服务",
    "Mellish Reef": "不通邮：梅利什礁为无人珊瑚礁，无邮政服务",
    "Midway I.": "不通邮：中途岛无常住人口与邮政服务",
    "Midway Island": "不通邮：仅野生动物保护区，无邮政服务",
    "Mount Athos": "不通邮：修道院自治体，邮件须经希腊转递",
    "Navassa I.": "不通邮：纳瓦萨岛为无人岛，无邮政服务",
    "Navassa Island": "不通邮：无人岛，无邮政服务",
    "North Korea": "不通邮：中国邮政不办理寄往朝鲜的平常函件业务",
    "Palmyra & Jarvis Is.": "不通邮：帕尔迈拉与贾维斯岛无常住人口与邮政服务",
    "Palmyra and Jarvis Islands": "不通邮：无常住人口和邮政服务",
    "Peter 1 I.": "不通邮：南极彼得一世岛无常住人口与邮政服务",
    "Peter 1 Island": "不通邮：南极彼得一世岛无常住人口与邮政服务",
    "Pratas I.": "不通邮：东沙群岛无常住人口与邮政服务",
    "Pratas Island": "不通邮：东沙群岛无常住人口与邮政服务",
    "Prince Edward & Marion Is.": "不通邮：爱德华王子群岛无常住人口与邮政服务",
    "Prince Edward and Marion Islands": "不通邮：爱德华王子群岛无常住人口与邮政服务",
    "Sable I.": "不通邮：塞布尔岛无常住人口与邮政服务",
    "Sable Island": "不通邮：塞布尔岛无常住人口与邮政服务",
    "San Felix & San Ambrosio": "不通邮：圣费利克斯与圣安布罗西奥岛无常住人口",
    "San Felix and San Ambrosio": "不通邮：圣费利克斯与圣安布罗西奥岛无常住人口",
    "Scarborough Reef": "不通邮：黄岩岛为无人珊瑚礁，无邮政服务",
    "Scarborough Shoal": "不通邮：无常住人口和邮政设施",
    "South Shetland Is.": "不通邮：南设得兰群岛为南极科考区，无邮政服务",
    "South Shetland Islands": "不通邮：南设得兰群岛为南极科考区，无邮政服务",
    "Sov. Mil. Order of Malta": "无法投递：马耳他骑士团为外交实体，按意大利/马耳他投递",
    "Spratly Is.": "不通邮：南沙群岛无常住人口与邮政服务",
    "Spratly Islands": "不通邮：无常住人口和邮政设施",
    "St Peter and St Paul Rocks": "不通邮：圣彼得和圣保罗岩为无人岛礁，无邮政服务",
    "St. Paul I.": "不通邮：圣保罗岛无常住人口与邮政服务",
    "St. Peter & St. Paul Rocks": "不通邮：圣彼得和圣保罗岩为无人岛礁，无邮政服务",
    "Swains I.": "不通邮：斯温斯岛无常住人口与邮政服务",
    "Swains Island": "不通邮：斯温斯岛无常住人口与邮政服务",
    "Temotu Province": "不通邮：泰莫图省偏远外岛无常规邮政服务",
    "Trindade & Martim Vaz Is.": "不通邮：特林达迪与马丁瓦斯群岛无常住人口",
    "Trindade and Martim Vaz": "不通邮：特林达迪与马丁瓦斯群岛无常住人口",
    "United Nations HQ": "无法投递：联合国总部，属外交机构而非邮政目的地",
    "Wake I.": "不通邮：威克岛无常住人口与邮政服务",
    "Wake Island": "不通邮：无常住人口和邮政服务",
    "Willis I.": "不通邮：威利斯岛仅有气象站，无邮政服务",
    "Willis Island": "不通邮：威利斯岛仅有气象站，无邮政服务",
}

# ---------------------------------------------------------------------------
# DXCC entity -> rate zone.
#
# A DXCC entity is finer than a postal destination: Hawaii and Alaska are US
# states, the Russian entities share one postal system, and the European
# islands are part of their parent country's post.
# ---------------------------------------------------------------------------
DESTINATIONS: Dict[str, str] = {}


def _assign(zone: str, *entities: str) -> None:
    for name in entities:
        DESTINATIONS[name] = zone


# --- mainland China ---------------------------------------------------------
_assign(DOMESTIC, "China", "Hainan Island", "Scarborough Shoal")

# --- Hong Kong, Macao, Taiwan ----------------------------------------------
_assign(HONG_KONG_MACAO_TAIWAN, "Hong Kong", "Macao", "Taiwan")

# --- Zone 1: neighbouring Asian countries ----------------------------------
_assign("1",
        "North Korea", "Mongolia", "Vietnam", "Japan", "South Korea",
        "Kazakhstan", "Kyrgyzstan", "Tajikistan", "Uzbekistan", "Turkmenistan")

# --- Zone 2: the rest of Asia ----------------------------------------------
_assign("2",
        "Afghanistan", "Andaman and Nicobar Islands", "Armenia", "Azerbaijan",
        "Bahrain", "Bangladesh", "Bhutan", "Brunei Darussalam", "Cambodia",
        "Cyprus", "Georgia", "India", "Indonesia", "Iran", "Iraq", "Israel",
        "Jordan", "Kuwait", "Laos", "Lebanon", "Malaysia", "Maldives",
        "Myanmar", "Nepal", "Northern Cyprus", "Oman", "Pakistan", "Palestine",
        "Philippines", "Qatar", "Saudi Arabia", "Singapore", "Sri Lanka",
        "Syria", "Thailand", "Turkey", "United Arab Emirates", "Yemen")

# --- Zone 3: Europe, USA, Canada, Australia, New Zealand -------------------
_assign("3",
        "Aland Islands", "Albania", "Andorra", "Austria", "Azores", "Belarus",
        "Belgium", "Bosnia and Herzegovina", "Bulgaria", "Corsica", "Crete",
        "Croatia", "Czech Republic", "Denmark", "Dodecanese", "England",
        "Estonia", "European Russia", "Asiatic Russia", "Kaliningrad",
        "Faroe Islands", "Finland", "France", "Germany", "Gibraltar",
        "Greece", "Guernsey", "Hungary", "Iceland", "Ireland", "Isle of Man",
        "Italy", "Jan Mayen", "Jersey", "Kosovo", "Latvia", "Liechtenstein",
        "Lithuania", "Luxembourg", "Madeira Islands", "Malta", "Market Reef",
        "Moldova", "Monaco", "Montenegro", "Mount Athos", "Netherlands",
        "North Macedonia", "Northern Ireland", "Norway", "Poland", "Portugal",
        "Romania", "San Marino", "Sardinia", "Scotland", "Serbia", "Sicily",
        "Slovak Republic", "Slovenia", "Spain", "Svalbard", "Sweden",
        "Switzerland", "Ukraine", "United Kingdom", "Vatican City", "Wales",
        "Australia", "New Zealand", "United States", "Canada", "Hawaii",
        "Alaska", "Puerto Rico", "United States Virgin Islands", "Guam",
        "Northern Mariana Islands", "American Samoa", "Wake Island")

# --- Zone 4: the rest of the Americas, Africa, Pacific islands -------------
_assign("4",
        # Americas
        "Anguilla", "Antigua and Barbuda", "Argentina", "Aruba", "Bahamas",
        "Barbados", "Belize", "Bermuda", "Bolivia", "Bonaire", "Brazil",
        "British Virgin Islands", "Cayman Islands",
        "Chile", "Clipperton Island", "Colombia", "Costa Rica", "Cuba",
        "Curacao", "Dominica", "Dominican Republic", "Ecuador", "El Salvador",
        "Falkland Islands", "French Guiana", "Greenland", "Grenada",
        "Guantanamo Bay", "Guatemala", "Guyana", "Haiti", "Honduras",
        "Jamaica", "Mexico", "Montserrat", "Navassa Island", "Nicaragua",
        "Panama", "Paraguay", "Peru", "Revillagigedo", "Saba and St. Eustatius",
        "Sint Maarten, Saba, St. Eustatius",
        "Saint Kitts and Nevis", "Saint Lucia",
        "Saint Vincent and the Grenadines", "Sint Maarten",
        "South Georgia Island", "Suriname", "Trinidad and Tobago",
        "Turks and Caicos Islands", "Uruguay", "Venezuela",
        # Africa
        "Algeria", "Angola", "Ascension Island", "Benin", "Botswana",
        "Burkina Faso", "Burundi", "Cameroon", "Canary Islands", "Cape Verde",
        "Central African Republic", "Ceuta and Melilla", "Chad",
        "Chagos Islands", "Comoros", "Democratic Republic of the Congo",
        "Djibouti", "Egypt", "Equatorial Guinea", "Eritrea", "Eswatini",
        "Ethiopia", "Gabon", "Gambia", "Ghana", "Guinea", "Guinea-Bissau",
        "Ivory Coast", "Kenya", "Lesotho", "Liberia", "Libya", "Madagascar",
        "Malawi", "Mali", "Mauritania", "Mauritius", "Mayotte", "Morocco",
        "Mozambique", "Namibia", "Niger", "Nigeria",
        "Republic of the Congo", "Reunion", "Rwanda", "Saint Helena",
        "Sao Tome and Principe", "Senegal", "Seychelles", "Sierra Leone",
        "Somalia", "South Africa", "South Sudan", "Sudan", "Tanzania", "Togo",
        "Tristan da Cunha and Gough Islands", "Tunisia", "Uganda",
        "Western Sahara", "Zambia", "Zimbabwe",
        # Pacific islands
        "Antarctica", "Auckland and Campbell Islands",
        "Baker and Howland Islands", "Chatham Islands", "Cook Islands",
        "East Timor", "Fiji", "French Polynesia", "Johnston Atoll",
        "Kermadec Islands", "Kingman Reef", "Kiribati (Western)",
        "Kure Atoll", "Lord Howe Island", "Marshall Islands", "Micronesia",
        "Midway Island", "New Caledonia", "Norfolk Island", "Palau",
        "Palmyra and Jarvis Islands", "Papua New Guinea", "Samoa",
        "Solomon Islands", "Tonga", "Tuvalu", "Vanuatu",
        "Wallis and Futuna Islands")

# --- the far north is not served by China Post -----------------------------
_assign(NOT_MAILABLE, "Bear Island", "Franz Josef Land", "Market Reef",
        "Mount Athos", "Navigator Islands", "Spratly Islands")

# Postal destinations that are whole countries in their own right get a label.
# --- overseas territories and island nations, rated with the parent country
#     or by their own postal administration -------------------------------
_assign('4', "Agalega & St. Brandon Is.")  # 与毛里求斯同费率
_assign('4', "Aland Is.")  # 与芬兰同费率
_assign('4', "Alaska")  # 与美国同费率
_assign('4', "Amsterdam & St. Paul Is.")  # 与法属南方领地同费率
_assign('4', "Andaman & Nicobar Is.")  # 与印度同费率
_assign('4', "Annobon I.")  # 与赤道几内亚同费率
_assign('4', "Aruba")  # 与荷属加勒比同费率
_assign('4', "Azores")  # 与葡萄牙同费率
_assign('4', "Balearic Is.")  # 与西班牙同费率
_assign('4', "Bear Island")  # 与挪威同费率
_assign('4', "Bonaire")  # 与荷属加勒比同费率
_assign('4', "Canary Is.")  # 与西班牙同费率
_assign('4', "Ceuta & Melilla")  # 与西班牙同费率
_assign('4', "Chatham Is.")  # 与新西兰同费率
_assign('4', "Christmas I.")  # 与澳大利亚同费率
_assign('4', "Cocos (Keeling) Is.")  # 与澳大利亚同费率
_assign('4', "Cocos I.")  # 与哥斯达黎加同费率
_assign('4', "Corsica")  # 与法国同费率
_assign('4', "Crete")  # 与希腊同费率
_assign('4', "Crozet I.")  # 与法属南方领地同费率
_assign('4', "Curacao")  # 与荷属加勒比同费率
_assign('4', "Dodecanese")  # 与希腊同费率
_assign('4', "Easter I.")  # 与智利同费率
_assign('4', "Falkland Is.")  # 与福克兰群岛同费率
_assign('4', "Faroe Is.")  # 与丹麦同费率
_assign('4', "Fernando de Noronha")  # 与巴西同费率
_assign('4', "Galapagos Is.")  # 与厄瓜多尔同费率
_assign('4', "Glorioso Is.")  # 与法属南方领地同费率
_assign('4', "Greenland")  # 与丹麦同费率
_assign('4', "Guadeloupe")  # 与法属西印度群岛同费率
_assign('4', "Guam")  # 与美国同费率
_assign('4', "Hawaii")  # 与美国同费率
_assign('4', "Jan Mayen")  # 与挪威同费率
_assign('4', "Juan Fernandez Is.")  # 与智利同费率
_assign('4', "Juan de Nova, Europa")  # 与法属南方领地同费率
_assign('4', "Kerguelen Is.")  # 与法属南方领地同费率
_assign('4', "Kermadec Is.")  # 与新西兰同费率
_assign('4', "Lakshadweep Is.")  # 与印度同费率
_assign('4', "Lord Howe I.")  # 与澳大利亚同费率
_assign('4', "Madeira Is.")  # 与葡萄牙同费率
_assign('4', "Mariana Is.")  # 与美国同费率
_assign('4', "Market Reef")  # 与芬兰/瑞典共管礁石，无常规邮政
_assign('4', "Martinique")  # 与法属西印度群岛同费率
_assign('4', "Mayotte")  # 与马约特同费率
_assign('4', "Minami Torishima")  # 与日本同费率
_assign('4', "Mount Athos")  # 与希腊同费率
_assign('4', "New Zealand Subantarctic Islands")  # 与新西兰同费率
_assign('4', "Norfolk I.")  # 与澳大利亚同费率
_assign('4', "Ogasawara")  # 与日本同费率
_assign('4', "Puerto Rico")  # 与美国同费率
_assign('4', "Reunion I.")  # 与留尼汪同费率
_assign('4', "Rodrigues I.")  # 与毛里求斯同费率
_assign('4', "Saba & St. Eustatius")  # 与荷属加勒比同费率
_assign('4', "Sable I.")  # 与加拿大同费率（无常规邮政）
_assign('4', "Saint Barthelemy")  # 与法属西印度群岛同费率
_assign('4', "Saint Martin")  # 与法属西印度群岛同费率
_assign('4', "San Andres & Providencia")  # 与哥伦比亚同费率
_assign('4', "San Felix & San Ambrosio")  # 与智利同费率
_assign('4', "Sardinia")  # 与意大利同费率
_assign('4', "Sicily")  # 与意大利同费率
_assign('4', "Socotra")  # 与也门同费率
_assign('4', "South Georgia I.")  # 与福克兰群岛同费率
_assign('4', "South Orkney Is.")  # 与南极属地同费率
_assign('4', "South Sandwich Is.")  # 与福克兰群岛同费率
_assign('4', "St Maarten")  # 与荷属加勒比同费率
_assign('4', "Svalbard")  # 与挪威同费率
_assign('4', "Trindade & Martim Vaz Is.")  # 与巴西同费率
_assign('4', "Tromelin I.")  # 与法属南方领地同费率
_assign('4', "Virgin Is.")  # 与美属维尔京群岛同费率
_assign("4", "Anguilla")
_assign("4", "Antigua & Barbuda")
_assign("4", "Ascension I.")
_assign("4", "Austral I.")
_assign("4", "Bahamas")
_assign("4", "Banaba I. (Ocean I.)")
_assign("4", "Barbados")
_assign("4", "Bermuda")
_assign("4", "British Virgin Is.")
_assign("2", "Brunei Darussalam")
_assign("4", "C. Kiribati (British Phoenix Is.)")
_assign("4", "Cape Verde")
_assign("4", "Cayman Is.")
_assign("4", "Central Africa")
_assign("4", "Comoros")
_assign("4", "Cote d'Ivoire")
_assign("4", "Dominica")
_assign("4", "E. Kiribati (Line Is.)")
_assign("2", "East Malaysia")
_assign("4", "French Polynesia")
_assign("4", "Grenada")
_assign("3", "Macedonia")
_assign("2", "Maldives")
_assign("4", "Marquesas Is.")
_assign("4", "Montserrat")
_assign("4", "Nauru")
_assign("4", "New Caledonia")
_assign("4", "Niue")
_assign("4", "North Cook Is.")
_assign("4", "Papua New Guinea")
_assign("4", "Pitcairn I.")
_assign("3", "Republic of Kosovo")
_assign("4", "Rotuma I.")
_assign("4", "Samoa")
_assign("4", "Sao Tome & Principe")
_assign("4", "Solomon Is.")
_assign("4", "South Cook Is.")
_assign("4", "South Sudan (Republic of)")
_assign("3", "Sovereign Military Order of Malta")
_assign("2", "Sri Lanka")
_assign("4", "St. Helena")
_assign("4", "St. Kitts & Nevis")
_assign("4", "St. Lucia")
_assign("4", "St. Pierre & Miquelon")
_assign("4", "St. Vincent")
_assign("4", "Swaziland")
_assign("4", "The Gambia")
_assign("4", "Timor-Leste")
_assign("4", "Tokelau Is.")
_assign("4", "Tonga")
_assign("4", "Trinidad & Tobago")
_assign("4", "Tristan da Cunha & Gough I.")
_assign("4", "Turks & Caicos Is.")
_assign("4", "Tuvalu")
_assign("3", "UK Sovereign Base Areas on Cyprus")
_assign("4", "Vanuatu")
_assign("3", "Vatican")
_assign("4", "W. Kiribati (Gilbert Is. )")
_assign("4", "Wallis & Futuna Is.")
_assign("2", "West Malaysia")

_assign("4", "C. Kiribati")
_assign("4", "Cabo Verde (Repub of)")
_assign("4", "Congo (Republic of the)")
_assign("4", "N. Cook Is.")
_assign("4", "New Zealand Subantarctic Islands")
_assign("4", "S. Cook Is.")
_assign("4", "Timor - Leste")

DESTINATION_LABELS: Dict[str, str] = {
    DOMESTIC: "中国大陆 (mainland China)",
    DOMESTIC_LOCAL: "中国大陆·本埠 (same city)",
    HONG_KONG_MACAO_TAIWAN: "港澳台 (Hong Kong / Macao / Taiwan)",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
#: ARRL DXCC name -> the name used by the destination table below.  Only names
#: that differ are listed; everything else matches directly.
ENTITY_ALIASES: Dict[str, str] = {
    "4U_ITU ITU HQ": "ITU HQ",
    "Agalega & St. Brandon Is.": "Agalega and St Brandon",
    "Aland Is.": "Aland Islands",
    "Algeria (People's Dem Republic of)": "Algeria",
    "Amsterdam & St. Paul Is.": "Amsterdam and St Paul Islands",
    "Andaman & Nicobar Is.": "Andaman Islands",
    "Annobon I.": "Annobon Island",
    "Ascension I.": "Ascension Island",
    "Auckland & Campbell Is.": "Auckland and Campbell Islands",
    "Aves I.": "Aves Island",
    "Bahamas (Commonwealth of the)": "Bahamas",
    "Baker & Howland Is.": "Baker and Howland Islands",
    "Balearic Is.": "Balearic Islands",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Botswana (Republic of)": "Botswana",
    "Bouvet": "Bouvet Island",
    "British Virgin Is.": "British Virgin Islands",
    "Canary Is.": "Canary Islands",
    "Cayman Is.": "Cayman Islands",
    "Central Africa": "Central African Republic",
    "Ceuta & Melilla": "Ceuta and Melilla",
    "Chatham Is.": "Chatham Islands",
    "Chesterfield Is.": "Chesterfield Islands",
    "Christmas I.": "Christmas Island",
    "Clipperton I.": "Clipperton Island",
    "Cocos I.": "Cocos Island",
    "Congo (Republic of the)": "Republic of the Congo",
    "Cote d'Ivoire": "Ivory Coast",
    "Crozet I.": "Crozet Island",
    "Dem. Rep. of Congo": "Democratic Republic of the Congo",
    "Democratic People's Rep. of Korea": "North Korea",
    "Desecheo I.": "Desecheo Island",
    "Ducie I.": "Ducie Island",
    "Easter I.": "Easter Island",
    "Faroe Is.": "Faroe Islands",
    "Federal Republic of Germany": "Germany",
    "Galapagos Is.": "Galapagos Islands",
    "Germany (Fed Repub of)": "Germany",
    "Heard I.": "Heard Island",
    "Johnston I.": "Johnston Island",
    "Juan Fernandez Is.": "Juan Fernandez Islands",
    "Kerguelen Is.": "Kerguelen Islands",
    "Kermadec Is.": "Kermadec Islands",
    "Kingdom of Eswatini": "Eswatini",
    "Kure I.": "Kure Atoll",
    "Lakshadweep Is.": "Lakshadweep",
    "Lord Howe I.": "Lord Howe Island",
    "Macquarie I.": "Macquarie Island",
    "Madeira Is.": "Madeira Islands",
    "Malpelo I.": "Malpelo Island",
    "Mariana Is.": "Northern Mariana Islands",
    "Marshall Is.": "Marshall Islands",
    "Midway I.": "Midway Island",
    "N. Cook Is.": "North Cook Islands",
    "Navassa I.": "Navassa Island",
    "Norfolk I.": "Norfolk Island",
    "Pakistan (Islamic Rep of)": "Pakistan",
    "Palmyra & Jarvis Is.": "Palmyra and Jarvis Islands",
    "Peter 1 I.": "Peter 1 Island",
    "Pratas I.": "Pratas Island",
    "Republic of Korea": "South Korea",
    "Republic of Kosovo": "Kosovo",
    "Rodrigues I.": "Rodrigues Island",
    "Rotuma I.": "Rotuma Island",
    "S. Cook Is.": "South Cook Islands",
    "Sable I.": "Sable Island",
    "San Andres & Providencia": "San Andres and Providencia",
    "San Felix & San Ambrosio": "San Felix and San Ambrosio",
    "Sao Tome & Principe": "Sao Tome and Principe",
    "Singapore (Republic of)": "Singapore",
    "Solomon Is.": "Solomon Islands",
    "South Georgia I.": "South Georgia Island",
    "South Sandwich Is.": "South Sandwich Islands",
    "South Sudan (Rep of)": "South Sudan",
    "Sov. Base Areas on Cyprus": "UK Sovereign Base Areas on Cyprus",
    "Spratly Is.": "Spratly Islands",
    "St. Helena": "Saint Helena",
    "St. Kitts & Nevis": "Saint Kitts and Nevis",
    "St. Lucia": "Saint Lucia",
    "St. Peter & St. Paul Rocks": "St Peter and St Paul Rocks",
    "St. Pierre & Miquelon": "Saint Pierre and Miquelon",
    "St. Vincent": "Saint Vincent and the Grenadines",
    "Swains I.": "Swains Island",
    "Tanzania (United Rep of)": "Tanzania",
    "The Gambia": "Gambia",
    "Timor-Leste": "Timor Leste",
    "Trindade & Martim Vaz Is.": "Trindade and Martim Vaz",
    "Trinidad & Tobago": "Trinidad and Tobago",
    "Tristan da Cunha & Gough I.": "Tristan da Cunha and Gough Islands",
    "Turks & Caicos Is.": "Turks and Caicos Islands",
    "UK Sov. Base Areas": "UK Sovereign Base Areas on Cyprus",
    "United States of America": "United States",
    "Vatican": "Vatican City",
    "Viet Nam": "Vietnam",
    "Virgin Is.": "US Virgin Islands",
    "Wake I.": "Wake Island",
    "Willis I.": "Willis Island",

    # Wording the ARRL list uses
    "Macedonia": "North Macedonia",
    "Swaziland": "Eswatini",
    "Sovereign Military Order of Malta": "Malta",
    "South Sudan (Republic of)": "South Sudan",
    "St Maarten": "Sint Maarten",
    "Saba & St. Eustatius": "Saba and St Eustatius",
    "Antigua & Barbuda": "Antigua and Barbuda",
    "Prince Edward & Marion Is.": "Prince Edward and Marion Islands",
    "Juan de Nova, Europa": "Juan de Nova and Europa",
    "W. Kiribati (Gilbert Is. )": "Kiribati (Western)",
    "C. Kiribati (British Phoenix Is.)": "Central Kiribati",
    "E. Kiribati (Line Is.)": "Eastern Kiribati",
    "Banaba I. (Ocean I.)": "Banaba Island",
    # Places with no ordinary postal service: reported as 不通邮 by name.
    "ITU HQ": "ITU HQ",
    "United Nations HQ": "United Nations HQ",
    "UK Sovereign Base Areas on Cyprus": "UK Sovereign Base Areas on Cyprus",
    "K1* South Shetland Is.": "South Shetland Islands",
}

#: Trailing "Is." / "I." and "&" are the ARRL list's abbreviations; expanding
#: them covers most of the remaining names without listing each one.
# Order matters: "Is." must be tried before "I.", or "Islands" gains an
# extra "s" and becomes "Islandses".
_ABBREVIATIONS = (
    ("Is.", "Islands"), ("I.", "Island"), (" & ", " and "),
)


def clean_entity_name(name: str) -> str:
    """An entity name without the list's footnote markers.

    The published list marks footnotes with */#/^ and they can end up inside the
    entity name when the prefix column overflows: the ITU HQ row arrives as
    "4U_ITU#* ITU HQ".
    """
    name = re.sub(r"[*#^]+", " ", name or "")
    name = re.sub(r"^[A-Z0-9_]+\s+(?=[A-Z])", "", name)
    return re.sub(r"\s{2,}", " ", name).strip()


def _raw_zone(name: str) -> str:
    """Zone for an exact key, with no normalisation.

    Kept separate so normalisation can test a candidate spelling without calling
    back into destination_for_entity, which would recurse.
    """
    return DESTINATIONS.get(name, "")


def canonical_entity_name(name: str) -> str:
    """The destination-table name for a published ARRL entity name.

    The list abbreviates and qualifies its names -- "Wallis & Futuna Is.",
    "Germany (Fed Repub of)", "C. Kiribati" -- so the name is normalised before
    it is looked up:

      * footnote markers are dropped;
      * a parenthetical qualifier is removed ("Germany (Fed Repub of)" ->
        "Germany"), which is safe because the qualifier never distinguishes two
        entities;
      * the list's abbreviations are expanded ("Is." -> "Islands", "&" -> "and");
      * the explicit aliases below cover the wording that differs for real.
    """
    name = re.sub(r"[*#^]+", " ", name or "")
    name = re.sub(r"\s*\([^)]*\)\s*", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    if not name:
        return ""
    direct = ENTITY_ALIASES.get(name)
    if direct:
        return direct
    candidate = name
    for short, full in _ABBREVIATIONS:
        candidate = candidate.replace(short, full)
    candidate = re.sub(r"\s{2,}", " ", candidate).strip()
    for variant in (candidate, name):
        if _raw_zone(variant):
            return variant
    return name


def destination_for_entity(entity_name: str) -> str:
    """Rate zone for a DXCC entity name, or "" when not in the table.

    The name is normalised first, so a caller may pass either the published ARRL
    spelling ("Wallis & Futuna Is.", "Germany (Fed Repub of)") or the plain one.
    """
    name = (entity_name or "").strip()
    if not name:
        return ""
    zone = DESTINATIONS.get(name)
    if zone:
        return zone
    return DESTINATIONS.get(canonical_entity_name(name), "")


def is_mailable(entity_name: str) -> Optional[bool]:
    """True / False, or None when the entity is not in the table at all."""
    name = (entity_name or "").strip()
    if name in NOT_MAILABLE_ENTITIES:
        return False
    zone = destination_for_entity(name)
    if not zone:
        return None
    return zone != NOT_MAILABLE


def describe_rates(rates: Dict[str, float]) -> str:
    """A compact, displayable breakdown such as ``航空 6.00 / 水陆路 4.00``."""
    parts = []
    for key in SERVICES:
        if key in rates:
            parts.append(f"{SERVICE_LABELS[key]} {rates[key]:.2f}")
    return " / ".join(parts)


def quote(entity_name: str, weight_g: int = REFERENCE_WEIGHT_G) -> Postage:
    """Postage for mailing an ordinary LETTER (信函) to ``entity_name``.

    Only the letter tariff is ever returned.  ``Postage.detail`` is a pure price
    breakdown of the form ``航空 6.00 / 水陆路 4.00`` — no zone names, because
    the zone is a rating mechanism rather than a price.  The zone is still
    available on ``Postage.zone`` for callers that want it.

    Raises :class:`NotMailable` when China Post does not serve the destination.
    Returns a Postage with an empty rate map when the entity is not in the
    table, so the caller writes nothing rather than inventing a price.
    """
    # A destination China Post will not accept mail for is refused before any
    # zone is consulted, so a zone assignment can never override it.
    if entity_name in NOT_MAILABLE_ENTITIES:
        reason = NOT_MAILABLE_ENTITIES[entity_name]
        raise NotMailable(reason, reason)

    zone = destination_for_entity(entity_name)
    if not zone:
        return Postage(entity_name or "", "", {}, False, "destination not in table")

    if zone == NOT_MAILABLE:
        reason = "不通邮：该地区无普通邮政投递服务"
        raise NotMailable(reason, reason)

    # --- mainland China ----------------------------------------------------
    if zone == DOMESTIC:
        local = DOMESTIC_RATES[DOMESTIC_LOCAL]
        non_local = DOMESTIC_RATES[DOMESTIC]
        # Mainland China is reported as one figure: 1.20, the ordinary letter
        # rate.  The 本埠 0.80 rate exists, but a QSL card goes to another
        # station rather than staying in the same city, and splitting the two
        # only adds a choice the user does not need.  本埠 is still available
        # programmatically through Postage.cost(DOMESTIC_LOCAL).
        rates = {DOMESTIC: non_local, DOMESTIC_LOCAL: local}
        return Postage("中国大陆 (mainland China)", zone, rates, True,
                       DOMESTIC_NOTE, f"国内 {non_local:.2f}")

    # --- Hong Kong, Macao, Taiwan -----------------------------------------
    if zone == HONG_KONG_MACAO_TAIWAN:
        rates = dict(HMT_RATES)
        detail = describe_rates(rates)
        note = HMT_REGISTRATION_NOTE.get(entity_name, "") or HMT_NOTE
        return Postage("港澳台 (Hong Kong / Macao / Taiwan)", zone, rates, True,
                       note, detail)

    # --- international -----------------------------------------------------
    rates = dict(INTERNATIONAL_RATES[zone])
    if entity_name not in SAL_AVAILABLE:
        rates.pop("SAL", None)
    if entity_name in APPU_REDUCED_SURFACE:
        rates["SURFACE"] = SURFACE_APPU_RATE

    # Prices only.  The zone name is not a price, so it stays off the detail
    # line; it remains available as Postage.zone.
    detail = describe_rates(rates)
    notes = []
    if entity_name not in SAL_AVAILABLE:
        notes.append("不通空运水陆路")
    if entity_name in APPU_REDUCED_SURFACE:
        notes.append("水陆路适用亚太减低资费")

    return Postage(entity_name, zone, rates, True, "；".join(notes), detail)
