# -*- coding: utf-8 -*-
"""
SharkSMS Live OTP Forwarder Bot for Telegram
==============================================
API-only version: polls SharkSMS REST API and forwards new messages to Telegram.
"""

import hashlib
import html
import os
import queue
import random
import re
import sys
import threading
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ==============================================================================
# CONFIGURATION
# ======================================
SHARKSMS_API_TOKEN = os.environ.get(
    "SHARKSMS_API_TOKEN",
    "CMiMn9JlKNlxjfPoTdciC_I0U3DImGmqJowXhRGPn2g",
).strip()

BOT_TOKENS = [
    token.strip()
    for token in os.environ.get(
        "TELEGRAM_BOT_TOKENS",
        "8606184785:AAFtR9vvhqR_GwPpYYUibx4CblRe2lZolqc,PASTE_TELEGRAM_BOT_TOKEN_2_HERE",
    ).split(",")
    if token.strip()
]

# Chat IDs can safely remain in this file; bot credentials cannot.
TELEGRAM_CHAT_ID = [
    -1003713446342,
    -1003878606545,
]

POLL_INTERVAL = 2.0
PROCESSED_FILE = "processed_ids.txt"

# ==============================================================================
# LOCKS & GLOBALS
# ==============================================================================
file_lock = threading.Lock()
msg_queue = queue.Queue()
INITIAL_SYNC_DONE = False

# ==============================================================================
# PERSISTENT DEDUPLICATION
# ==============================================================================
def load_processed():
    try:
        if os.path.exists(PROCESSED_FILE):
            with open(PROCESSED_FILE, "r", encoding="utf-8") as file:
                return set(file.read().splitlines())
        return set()
    except Exception as error:
        print(f"[Bot] ⚠️ Could not load processed file: {error}")
        return set()


processed_ids = load_processed()


def save_processed(uid):
    with file_lock:
        try:
            with open(PROCESSED_FILE, "a", encoding="utf-8") as file:
                file.write(f"{uid}\n")
        except Exception as error:
            print(f"[Bot] ⚠️ Could not save processed ID: {error}")


def get_item_uids(item):
    """Generate unique identification keys for an SMS item."""
    uids = []
    item_id = item.get("id") or item.get("_id") or item.get("message_id")
    if item_id:
        uids.append(f"shark_{item_id}")

    number = str(
        item.get("number")
        or item.get("receivedNumber")
        or item.get("num")
        or item.get("destination")
        or ""
    ).strip()
    sms = str(
        item.get("content")
        or item.get("message")
        or item.get("sms")
        or item.get("text")
        or ""
    ).strip()
    received_at = str(
        item.get("time")
        or item.get("receivedAt")
        or item.get("received_at")
        or item.get("date")
        or item.get("created_at")
        or ""
    ).strip()

    if number or sms:
        key = f"{number}_{sms}_{received_at}" if received_at else f"{number}_{sms}"
        uids.append(hashlib.md5(key.encode("utf-8")).hexdigest())

    return uids


# ==============================================================================
# OTP EXTRACTION
# ==============================================================================
def extract_otp(text):
    if not text:
        return "N/A"

    clean = text.replace(" ", "")

    match = re.search(r"(?<!\d)(\d{6})(?!\d)", clean)
    if match:
        return match.group(1)

    match = re.search(r"(\d{3,4})-(\d{3,4})", clean)
    if match:
        return match.group(1) + match.group(2)

    match = re.search(r"(?<!\d)(\d{4,8})(?!\d)", clean)
    if match:
        return match.group(1)

    return "N/A"


# ==============================================================================
# COUNTRY & SERVICE MAPPINGS
# ==============================================================================
COUNTRY_MAP = {
    "Venezuela": ("VE", "🇻🇪"),
    "Zimbabwe": ("ZW", "🇿🇼"),
    "Switzerland": ("CH", "🇨🇭"),
    "Bolivia": ("BO", "🇧🇴"),
    "Ivory Coast": ("CI", "🇨🇮"),
    "Guatemala": ("GT", "🇬🇹"),
    "Vietnam": ("VN", "🇻🇳"),
    "Afghanistan": ("AF", "🇦🇫"),
    "Albania": ("AL", "🇦🇱"),
    "Algeria": ("DZ", "🇩🇿"),
    "Andorra": ("AD", "🇦🇩"),
    "Angola": ("AO", "🇦🇴"),
    "Antigua and Barbuda": ("AG", "🇦🇬"),
    "Argentina": ("AR", "🇦🇷"),
    "Armenia": ("AM", "🇦🇲"),
    "Australia": ("AU", "🇦🇺"),
    "Austria": ("AT", "🇦🇹"),
    "Azerbaijan": ("AZ", "🇦🇿"),
    "Bahamas": ("BS", "🇧🇸"),
    "Bahrain": ("BH", "🇧🇭"),
    "Bangladesh": ("BD", "🇧🇩"),
    "Barbados": ("BB", "🇧🇧"),
    "Belarus": ("BY", "🇧🇾"),
    "Belgium": ("BE", "🇧🇪"),
    "Belize": ("BZ", "🇧🇿"),
    "Benin": ("BJ", "🇧🇯"),
    "Bhutan": ("BT", "🇧🇹"),
    "Bosnia and Herzegovina": ("BA", "🇧🇦"),
    "Botswana": ("BW", "🇧🇼"),
    "Brazil": ("BR", "🇧🇷"),
    "Brunei": ("BN", "🇧🇳"),
    "Bulgaria": ("BG", "🇧🇬"),
    "Burkina Faso": ("BF", "🇧🇫"),
    "Burundi": ("BI", "🇧🇮"),
    "Cabo Verde": ("CV", "🇨🇻"),
    "Cambodia": ("KH", "🇰🇭"),
    "Cameroon": ("CM", "🇨🇲"),
    "Canada": ("CA", "🇨🇦"),
    "Central African Republic": ("CF", "🇨🇫"),
    "Chad": ("TD", "🇹🇩"),
    "Chile": ("CL", "🇨🇱"),
    "China": ("CN", "🇨🇳"),
    "Colombia": ("CO", "🇨🇴"),
    "Comoros": ("KM", "🇰🇲"),
    "Congo": ("CG", "🇨🇬"),
    "Costa Rica": ("CR", "🇨🇷"),
    "Croatia": ("HR", "🇭🇷"),
    "Cuba": ("CU", "🇨🇺"),
    "Cyprus": ("CY", "🇨🇾"),
    "Czechia": ("CZ", "🇨🇿"),
    "Denmark": ("DK", "🇩🇰"),
    "Djibouti": ("DJ", "🇩🇯"),
    "Dominica": ("DM", "🇩🇲"),
    "Dominican Republic": ("DO", "🇩🇴"),
    "Ecuador": ("EC", "🇪🇨"),
    "Egypt": ("EG", "🇪🇬"),
    "El Salvador": ("SV", "🇸🇻"),
    "Equatorial Guinea": ("GQ", "🇬🇶"),
    "Eritrea": ("ER", "🇪🇷"),
    "Estonia": ("EE", "🇪🇪"),
    "Eswatini": ("SZ", "🇸🇿"),
    "Ethiopia": ("ET", "🇪🇹"),
    "Fiji": ("FJ", "🇫🇯"),
    "Finland": ("FI", "🇫🇮"),
    "France": ("FR", "🇫🇷"),
    "Gabon": ("GA", "🇬🇦"),
    "Gambia": ("GM", "🇬🇲"),
    "Georgia": ("GE", "🇬🇪"),
    "Germany": ("DE", "🇩🇪"),
    "Ghana": ("GH", "🇬🇭"),
    "Greece": ("GR", "🇬🇷"),
    "Grenada": ("GD", "🇬🇩"),
    "Guinea": ("GN", "🇬🇳"),
    "Guinea-Bissau": ("GW", "🇬🇼"),
    "Guyana": ("GY", "🇬🇾"),
    "Haiti": ("HT", "🇭🇹"),
    "Honduras": ("HN", "🇭🇳"),
    "Hungary": ("HU", "🇭🇺"),
    "Iceland": ("IS", "🇮🇸"),
    "India": ("IN", "🇮🇳"),
    "Indonesia": ("ID", "🇮🇩"),
    "Iran": ("IR", "🇮🇷"),
    "Iraq": ("IQ", "🇮🇶"),
    "Ireland": ("IE", "🇮🇪"),
    "Israel": ("IL", "🇮🇱"),
    "Italy": ("IT", "🇮🇹"),
    "Jamaica": ("JM", "🇯🇲"),
    "Japan": ("JP", "🇯🇵"),
    "Jordan": ("JO", "🇯🇴"),
    "Kazakhstan": ("KZ", "🇰🇿"),
    "Kenya": ("KE", "🇰🇪"),
    "Kiribati": ("KI", "🇰🇮"),
    "Korea, North": ("KP", "🇰🇵"),
    "Korea, South": ("KR", "🇰🇷"),
    "Kuwait": ("KW", "🇰🇼"),
    "Kyrgyzstan": ("KG", "🇰🇬"),
    "Laos": ("LA", "🇱🇦"),
    "Latvia": ("LV", "🇱🇻"),
    "Lebanon": ("LB", "🇱🇧"),
    "Lesotho": ("LS", "🇱🇸"),
    "Liberia": ("LR", "🇱🇷"),
    "Libya": ("LY", "🇱🇾"),
    "Liechtenstein": ("LI", "🇱🇮"),
    "Lithuania": ("LT", "🇱🇹"),
    "Luxembourg": ("LU", "🇱🇺"),
    "Madagascar": ("MG", "🇲🇬"),
    "Malawi": ("MW", "🇲🇼"),
    "Malaysia": ("MY", "🇲🇾"),
    "Maldives": ("MV", "🇲🇻"),
    "Mali": ("ML", "🇲🇱"),
    "Malta": ("MT", "🇲🇹"),
    "Marshall Islands": ("MH", "🇲🇭"),
    "Mauritania": ("MR", "🇲🇷"),
    "Mauritius": ("MU", "🇲🇺"),
    "Mexico": ("MX", "🇲🇽"),
    "Micronesia": ("FM", "🇫🇲"),
    "Moldova": ("MD", "🇲🇩"),
    "Monaco": ("MC", "🇲🇨"),
    "Mongolia": ("MN", "🇲🇳"),
    "Montenegro": ("ME", "🇲🇪"),
    "Morocco": ("MA", "🇲🇦"),
    "Mozambique": ("MZ", "🇲🇿"),
    "Myanmar": ("MM", "🇲🇲"),
    "Namibia": ("NA", "🇳🇦"),
    "Nauru": ("NR", "🇳🇷"),
    "Nepal": ("NP", "🇳🇵"),
    "Netherlands": ("NL", "🇳🇱"),
    "New Zealand": ("NZ", "🇳🇿"),
    "Nicaragua": ("NI", "🇳🇮"),
    "Niger": ("NE", "🇳🇪"),
    "Nigeria": ("NG", "🇳🇬"),
    "North Macedonia": ("MK", "🇲🇰"),
    "Norway": ("NO", "🇳🇴"),
    "Oman": ("OM", "🇴🇲"),
    "Pakistan": ("PK", "🇵🇰"),
    "Palau": ("PW", "🇵🇼"),
    "Panama": ("PA", "🇵🇦"),
    "Papua New Guinea": ("PG", "🇵🇬"),
    "Paraguay": ("PY", "🇵🇾"),
    "Peru": ("PE", "🇵🇪"),
    "Philippines": ("PH", "🇵🇭"),
    "Poland": ("PL", "🇵🇱"),
    "Portugal": ("PT", "🇵🇹"),
    "Qatar": ("QA", "🇶🇦"),
    "Romania": ("RO", "🇷🇴"),
    "Russia": ("RU", "🇷🇺"),
    "Rwanda": ("RW", "🇷🇼"),
    "Saint Kitts and Nevis": ("KN", "🇰🇳"),
    "Saint Lucia": ("LC", "🇱🇨"),
    "Saint Vincent and the Grenadines": ("VC", "🇻🇨"),
    "Samoa": ("WS", "🇼🇸"),
    "San Marino": ("SM", "🇸🇲"),
    "Sao Tome and Principe": ("ST", "🇸🇹"),
    "Saudi Arabia": ("SA", "🇸🇦"),
    "Senegal": ("SN", "🇸🇳"),
    "Serbia": ("RS", "🇷🇸"),
    "Seychelles": ("SC", "🇸🇨"),
    "Sierra Leone": ("SL", "🇸🇱"),
    "Singapore": ("SG", "🇸🇬"),
    "Slovakia": ("SK", "🇸🇰"),
    "Slovenia": ("SI", "🇸🇮"),
    "Solomon Islands": ("SB", "🇸🇧"),
    "Somalia": ("SO", "🇸🇴"),
    "South Africa": ("ZA", "🇿🇦"),
    "South Sudan": ("SS", "🇸🇸"),
    "Spain": ("ES", "🇪🇸"),
    "Sri Lanka": ("LK", "🇱🇰"),
    "Sudan": ("SD", "🇸🇩"),
    "Suriname": ("SR", "🇸🇷"),
    "Sweden": ("SE", "🇸🇪"),
    "Syria": ("SY", "🇸🇾"),
    "Taiwan": ("TW", "🇹🇼"),
    "Tajikistan": ("TJ", "🇹🇯"),
    "Tanzania": ("TZ", "🇹🇿"),
    "Thailand": ("TH", "🇹🇭"),
    "Timor-Leste": ("TL", "🇹🇱"),
    "Togo": ("TG", "🇹🇬"),
    "Tonga": ("TO", "🇹🇴"),
    "Trinidad and Tobago": ("TT", "🇹🇹"),
    "Tunisia": ("TN", "🇹🇳"),
    "Turkey": ("TR", "🇹🇷"),
    "Turkmenistan": ("TM", "🇹🇲"),
    "Tuvalu": ("TV", "🇹🇻"),
    "Uganda": ("UG", "🇺🇬"),
    "Ukraine": ("UA", "🇺🇦"),
    "United Arab Emirates": ("AE", "🇦🇪"),
    "United Kingdom": ("GB", "🇬🇧"),
    "United States": ("US", "🇺🇸"),
    "Uruguay": ("UY", "🇺🇾"),
    "Uzbekistan": ("UZ", "🇺🇿"),
    "Vanuatu": ("VU", "🇻🇺"),
    "Vatican City": ("VA", "🇻🇦"),
    "Yemen": ("YE", "🇾🇪"),
    "Zambia": ("ZM", "🇿🇲"),
}

COUNTRY_CODES = {code.upper() for code, _ in COUNTRY_MAP.values()}
PREFIX_COUNTRY_MAP = {
    "1": "US",
    "7": "RU",
    "20": "EG",
    "27": "ZA",
    "30": "GR",
    "31": "NL",
    "32": "BE",
    "33": "FR",
    "34": "ES",
    "36": "HU",
    "39": "IT",
    "40": "RO",
    "41": "CH",
    "43": "AT",
    "44": "GB",
    "45": "DK",
    "46": "SE",
    "47": "NO",
    "48": "PL",
    "49": "DE",
    "51": "PE",
    "52": "MX",
    "53": "CU",
    "54": "AR",
    "55": "BR",
    "56": "CL",
    "57": "CO",
    "58": "VE",
    "60": "MY",
    "61": "AU",
    "62": "ID",
    "63": "PH",
    "64": "NZ",
    "65": "SG",
    "66": "TH",
    "81": "JP",
    "82": "KR",
    "84": "VN",
    "86": "CN",
    "90": "TR",
    "91": "IN",
    "92": "PK",
    "93": "AF",
    "94": "IR",
    "95": "MM",
    "98": "IR",
}

FLAG_IDS = {
    "RU": "5433865586356531140",
    "CN": "5433827537241258614",
    "ZA": "5431855966863766753",
    "BR": "5431769908604056769",
    "IN": "5433601609076586221",
    "NO": "5434147542369579483",
    "GB": "5435996255207567113",
    "AF": "5433636707549331311",
    "AL": "5433845881046578644",
    "DZ": "5433627189901801019",
    "AD": "5433946537900128161",
    "AO": "5433750193470191473",
    "AG": "5431752174684092934",
    "AR": "5433754239329383923",
    "AM": "5433804400252434985",
    "AU": "5431556723607352698",
    "AT": "5431640943621060829",
    "BS": "5431375858239550223",
    "BH": "5433682092468746953",
    "BD": "5433854239052935880",
    "BB": "5434027579638035690",
    "BY": "5431739800883312139",
    "BE": "5433598052843665552",
    "BZ": "5431431529605642522",
    "BJ": "5433838931789492934",
    "BO": "5433609855413794108",
    "BA": "5433991338703991663",
    "BW": "5433895109961725692",
    "BN": "5433789964867352475",
    "BG": "5431663303220804322",
    "BF": "5434013938821902926",
    "MM": "5433666360003540231",
    "BI": "5433792911214917126",
    "KH": "5433696429069580735",
    "CM": "5433774971136521802",
    "CA": "5433960238845802718",
    "CV": "5431865097964237519",
    "CF": "5431374711483282830",
    "TD": "5433825269498525925",
    "CL": "5431561302042488884",
    "CO": "5433630999537792332",
    "KM": "5431790266749046991",
    "CD": "5431703839122141424",
    "CG": "5433861570562111275",
    "HR": "5431489619038320862",
    "CU": "5431551436502611633",
    "CY": "5434096943359866241",
    "CZ": "5433958877341169005",
    "DK": "5433708502222649633",
    "DM": "5433614889115464671",
    "DO": "5434140679011842196",
    "EC": "5431462560744353934",
    "EG": "5431619494554383246",
    "SV": "5434134189316257066",
    "ER": "5433723401464198287",
    "EE": "5433727662071755290",
    "ET": "5433804408842368654",
    "FJ": "5433640560134994324",
    "FI": "5431380440969654931",
    "FR": "5434067424049639550",
    "DE": "5431695798943363996",
    "GH": "5434041611296192616",
    "GR": "5434054805435724481",
    "ID": "5433884376838454074",
    "IQ": "5433749102548496991",
    "IT": "5434067655977874913",
    "JP": "5431626087329182684",
    "KE": "5433792670696748414",
    "MY": "5434150334098327966",
    "NG": "5433836092816108548",
    "PK": "5431434686406604479",
    "PH": "5433855712226718930",
    "SA": "5434125517777286321",
    "SG": "5431588626624427422",
    "ZW": "5433735143904786332",
    "US": "5434076031164103400",
}

SERVICE_MAP = [
    (["WHATSAPP", "WS"], "5393189591773630465", "💬", "WS"),
    (["FACEBOOK", "FB"], "5393310276059678201", "📩", "FB"),
    (["TELEGRAM"], "5364125616801073577", "✨", "TG"),
    (["GOOGLE", "GMAIL"], "5393197447268813836", "🔍", "GG"),
    (["INSTAGRAM"], "5393603871434099925", "📷", "IG"),
    (["WECHAT"], "6113767082636087326", "💬", "WC"),
    (["TIKTOK"], "5393189789342123585", "🎵", "TT"),
    (["TWITTER", "X"], "5393608179286297620", "🐦", "TW"),
    (["LINE"], "6244519961734156213", "💬", "LN"),
    (["VIBER"], "5463060437572528782", "📞", "VB"),
    (["SIGNAL"], "6089079919856325971", "📡", "SG"),
    (["DISCORD"], "5300896830551254527", "💬", "DC"),
    (["SNAPCHAT"], "5330248916224983855", "📸", "SC"),
    (["MICROSOFT", "HOTMAIL"], "5979047775470358891", "💾", "MS"),
    (["APPLE", "ICLOUD"], "5318795767454923927", "🍏", "AP"),
    (["AMAZON"], "5323624199753842832", "🛍️", "AM"),
    (["NETFLIX"], "5418026554422750284", "🎬", "NF"),
    (["UBER"], "5298715455316303708", "🚖", "UB"),
    (["PAYPAL"], "5776103539872896061", "💳", "PP"),
    (["LINKEDIN"], "6224222994265279792", "💼", "LI"),
]


def normalize_country_tokens(value):
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [token for token in re.split(r"[^A-Za-z0-9]+", text) if token]


def detect_country_from_prefix(raw_prefix):
    if raw_prefix is None:
        return None
    prefix_text = str(raw_prefix).strip()
    if not prefix_text:
        return None
    prefix_text = prefix_text.replace("+", "").replace("00", "")
    if not prefix_text or not prefix_text.isdigit():
        return None

    for length in (2, 3, 1):
        if length > len(prefix_text):
            continue
        candidate = prefix_text[:length]
        if candidate in PREFIX_COUNTRY_MAP:
            return PREFIX_COUNTRY_MAP[candidate]
    return None


def detect_country_from_value(raw_value):
    if raw_value is None:
        return None

    raw_text = str(raw_value).strip()
    if not raw_text:
        return None

    for token in normalize_country_tokens(raw_text):
        normalized = token.upper()
        if normalized in COUNTRY_CODES:
            return normalized

        candidate = token.lower()
        for country_name, (country_code, _) in COUNTRY_MAP.items():
            if candidate == country_name.lower() or candidate in country_name.lower().replace(" ", ""):
                return country_code

    digits_only = re.sub(r"\D", "", raw_text)
    if digits_only:
        return detect_country_from_prefix(digits_only)

    return None


def resolve_country_from_item(item):
    explicit_field_names = [
        "country_code",
        "countryCode",
        "countrycode",
        "iso_code",
        "isoCode",
        "country",
        "country_name",
        "countryName",
        "code",
        "cc",
    ]

    for field_name in explicit_field_names:
        candidate = item.get(field_name)
        resolved = detect_country_from_value(candidate)
        if resolved:
            return resolved

    for field_name in ["range", "rangeName", "range_name", "UID", "uid", "uid_range", "uidRange"]:
        candidate = item.get(field_name)
        resolved = detect_country_from_value(candidate)
        if resolved:
            return resolved

    number_candidate = (
        item.get("number")
        or item.get("receivedNumber")
        or item.get("num")
        or item.get("destination")
        or ""
    )
    prefix_candidate = (
        item.get("prefix")
        or item.get("number_prefix")
        or item.get("prefix_code")
        or item.get("country_prefix")
    )

    if prefix_candidate:
        resolved = detect_country_from_value(prefix_candidate)
        if resolved:
            return resolved

    if number_candidate:
        final_guess = detect_country_from_value(number_candidate)
        if final_guess:
            return final_guess

    return "UN"


def format_item(item):
    range_value = str(
        item.get("range")
        or item.get("rangeName")
        or item.get("range_name")
        or item.get("country")
        or ""
    ).strip()
    number_raw = str(
        item.get("number")
        or item.get("receivedNumber")
        or item.get("num")
        or item.get("destination")
        or ""
    ).replace("+", "").strip()
    platform_raw = str(
        item.get("cli")
        or item.get("senderCli")
        or item.get("platform")
        or item.get("sender")
        or ""
    ).upper().strip()

    country_code = resolve_country_from_item(item)
    flag = COUNTRY_MAP.get(next((name for name, (code, _) in COUNTRY_MAP.items() if code == country_code), ""), ("UN", "🌍"))[1]
    if country_code == "UN":
        flag = "🌍"

    if range_value and country_code == "UN":
        range_raw = range_value.strip()
        if "-" in range_raw:
            range_raw = range_raw.split("-")[0].strip()
        if range_raw:
            fallback_code = detect_country_from_value(range_raw)
            if fallback_code:
                country_code = fallback_code
                flag = COUNTRY_MAP.get(
                    next((name for name, (code, _) in COUNTRY_MAP.items() if code == country_code), ""),
                    (country_code, "🌍"),
                )[1]

    formatted_number = (
        f"{number_raw[:3]}XXX{number_raw[-4:]}"
        if len(number_raw) >= 7
        else number_raw
    )

    emoji_id, service_emoji, service_short = (
        "5462933547058749789",
        "📩",
        "N/N",
    )
    for keywords, service_id, emoji, short_name in SERVICE_MAP:
        if any(keyword in platform_raw for keyword in keywords):
            emoji_id, service_emoji, service_short = (
                service_id,
                emoji,
                short_name,
            )
            break

    logo = f'<tg-emoji emoji-id="{emoji_id}">{service_emoji}</tg-emoji>'
    flag_id = FLAG_IDS.get(country_code)
    flag_html = (
        f'<tg-emoji emoji-id="{flag_id}">{flag}</tg-emoji>'
        if flag_id
        else flag
    )

    return (
        f"{flag_html} #{country_code} {logo} #{service_short} "
        f"<code>{html.escape(formatted_number)}</code>"
    )


# ==============================================================================
# TELEGRAM DISPATCHER
# ==============================================================================
def send_sms_to_telegram(row):
    try:
        header = format_item(row)
        sms_text = str(
            row.get("content")
            or row.get("message")
            or row.get("sms")
            or row.get("text")
            or ""
        ).strip()
        otp = (
            row.get("code")
            or row.get("extracted_code")
            or row.get("otp")
            or extract_otp(sms_text)
        )

        if not otp or str(otp).strip() == "N/A":
            otp = extract_otp(sms_text)

        if otp and str(otp).strip() != "N/A":
            otp_button = [
                {
                    "text": f" {otp}",
                    "copy_text": {"text": str(otp)},
                    "style": "success",
                    "icon_custom_emoji_id": "5253742260054409879",
                }
            ]
        else:
            otp_button = [
                {
                    "text": " Waiting for OTP...",
                    "callback_data": "no_otp",
                    "style": "success",
                    "icon_custom_emoji_id": "5253742260054409879",
                }
            ]

        buttons = {
            "inline_keyboard": [
                otp_button,
                [
                    {
                        "text": " Get NUMBER",
                        "url": "https://t.me/RDX_NUMBER100_BOT?start=auto",
                        "style": "danger",
                        "icon_custom_emoji_id": "5467539229468793355",
                    },
                    {
                        "text": " News CHANNEL",
                        "url": "https://t.me/RDX_MARKETING",
                        "style": "danger",
                        "icon_custom_emoji_id": "5841276284155467413",
                    },
                ],
            ]
        }

        overall_success = True

        for chat_id in TELEGRAM_CHAT_ID:
            clean_chat_id = str(chat_id).strip()
            if not clean_chat_id:
                continue

            payload = {
                "chat_id": clean_chat_id,
                "text": header,
                "parse_mode": "HTML",
                "reply_markup": buttons,
            }

            chat_success = False
            attempts = 0

            while attempts < 10:
                bot_token = random.choice(BOT_TOKENS)
                try:
                    response = requests.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json=payload,
                        timeout=15,
                    )
                    if response.status_code == 200:
                        response_json = response.json()
                        if response_json.get("ok"):
                            print(
                                f"[Bot] ✅ OTP dispatched successfully to "
                                f"{clean_chat_id}"
                            )
                            chat_success = True
                            break

                        attempts += 1
                        description = response_json.get("description", "Unknown")
                        print(f"[Bot] ❌ Telegram API error: {description}")
                        if "copy_text" in str(description):
                            payload["reply_markup"]["inline_keyboard"][0] = [
                                {
                                    "text": f" OTP: {otp}",
                                    "callback_data": f"otp_{otp}",
                                    "style": "primary",
                                    "icon_custom_emoji_id": "5330115548900501467",
                                }
                            ]
                            continue
                        time.sleep(2)
                    elif response.status_code == 429:
                        print("[Bot] ⚠️ Telegram flood control; waiting 2s")
                        time.sleep(2)
                    else:
                        attempts += 1
                        print(
                            f"[Bot] ❌ Telegram HTTP {response.status_code}: "
                            f"{response.text[:200]}"
                        )
                        time.sleep(2)
                except Exception as error:
                    attempts += 1
                    print(f"[Bot] ❌ Send attempt {attempts} error: {error}")
                    time.sleep(2)

            if not chat_success:
                overall_success = False

        return overall_success
    except Exception as error:
        print(f"[Bot] ❌ Format/send error: {error}")
        return False


# ==============================================================================
# QUEUE WORKER
# ==============================================================================
def telegram_queue_worker():
    while True:
        try:
            task = msg_queue.get()
            if task is None:
                break

            item, uids = task
            if send_sms_to_telegram(item):
                number_display = (
                    item.get("receivedNumber")
                    or item.get("number")
                    or item.get("num")
                )
                print(f"[Bot] 🚀 Forwarded to Telegram: {number_display}")
                for uid in uids:
                    save_processed(uid)
            else:
                number_display = (
                    item.get("receivedNumber")
                    or item.get("number")
                    or item.get("num")
                )
                print(f"[Bot] ❌ Failed to forward: {number_display}")
                with file_lock:
                    for uid in uids:
                        processed_ids.discard(uid)

            msg_queue.task_done()
            time.sleep(0.05)
        except Exception as error:
            print(f"[Bot] ❌ Worker error: {error}")
            time.sleep(1)


# ==============================================================================
# SHARKSMS REST API POLLING
# ==============================================================================
def run_rest_api_mode():
    """Poll the official SharkSMS REST API using a Bearer token."""
    print("[Engine] 🔧 Starting SharkSMS REST API mode...")
    print(
        f"[Engine] 🧾 Bearer token: {SHARKSMS_API_TOKEN[:6]}..."
        f"{SHARKSMS_API_TOKEN[-4:] if len(SHARKSMS_API_TOKEN) > 10 else ''}"
    )

    headers = {
        "Authorization": f"Bearer {SHARKSMS_API_TOKEN}",
        "Accept": "application/json",
    }
    endpoints = [
        "https://sharksms.org/api/v1/messages?limit=50",
        "https://sharksms.org/api/v1/cdrs?limit=50&offset=0",
    ]
    active_url = endpoints[0]

    while True:
        try:
            response = requests.get(active_url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    rows = data
                elif isinstance(data, dict):
                    rows = (
                        data.get("records")
                        or data.get("messages")
                        or data.get("rows")
                        or data.get("items")
                        or data.get("cdrs")
                        or data.get("data")
                        or []
                    )
                else:
                    rows = []
                process_incoming_rows(rows)
            elif response.status_code == 404 and active_url == endpoints[0]:
                print("[Engine] ℹ️ /messages returned 404; switching to /cdrs...")
                active_url = endpoints[1]
                continue
            elif response.status_code == 401:
                print("[Engine] ❌ 401 Unauthorized: invalid API token")
                time.sleep(10)
            elif response.status_code == 429:
                print("[Engine] ⚠️ Rate limit reached; backing off for 5s...")
                time.sleep(5)
            else:
                print(
                    f"[Engine] ⚠️ SharkSMS API HTTP {response.status_code}: "
                    f"{response.text[:150]}"
                )
        except Exception as error:
            print(f"[Engine] ⚠️ Polling error: {error}")

        time.sleep(POLL_INTERVAL)


# ==============================================================================
# INCOMING ROWS PROCESSOR
# ==============================================================================
def process_incoming_rows(records):
    global INITIAL_SYNC_DONE, processed_ids

    if not records or not isinstance(records, list):
        return

    valid_rows = []
    for row in records:
        try:
            if isinstance(row, dict):
                number = str(
                    row.get("number")
                    or row.get("receivedNumber")
                    or row.get("num")
                    or row.get("destination")
                    or ""
                ).strip()
                if number and len(number) > 5 and number != "0":
                    valid_rows.append(row)
        except Exception as error:
            print(f"[Bot] ⚠️ Row parse error: {error}")

    if not valid_rows:
        return

    if not INITIAL_SYNC_DONE:
        print(
            f"[Bot] 📈 Initial sync: recording {len(valid_rows)} existing items..."
        )
        for item in valid_rows:
            uids = get_item_uids(item)
            for uid in uids:
                if uid not in processed_ids:
                    processed_ids.add(uid)
                    save_processed(uid)

        recent_item = valid_rows[0]
        test_number = (
            recent_item.get("number")
            or recent_item.get("receivedNumber")
            or recent_item.get("num")
        )
        print(
            f"[Bot] 🧪 Sending latest SMS as startup test to Telegram: "
            f"{test_number}"
        )

        if send_sms_to_telegram(recent_item):
            print(f"[Bot] ✅ Startup test delivered successfully → {test_number}")
        else:
            print("[Bot] ⚠️ Startup test failed to send.")

        INITIAL_SYNC_DONE = True
        print("[Bot] 🟢 Live OTP monitoring is active.")
    else:
        for item in valid_rows:
            uids = get_item_uids(item)
            if not any(uid in processed_ids for uid in uids):
                number_display = (
                    item.get("receivedNumber")
                    or item.get("number")
                    or item.get("num")
                )
                print(f"[Bot] 📥 New live OTP received → {number_display}")

                for uid in uids:
                    processed_ids.add(uid)
                    save_processed(uid)

                msg_queue.put((item, uids))
                time.sleep(0.05)


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("=" * 65)
    print("📨 SharkSMS Telegram Live OTP Forwarder Bot")
    print("=" * 65)

    if not SHARKSMS_API_TOKEN or SHARKSMS_API_TOKEN.startswith("PASTE_"):
        raise ValueError("Replace PASTE_SHARKSMS_API_TOKEN_HERE in bot.py.")
    if not BOT_TOKENS or any(token.startswith("PASTE_") for token in BOT_TOKENS):
        raise ValueError("Replace the Telegram bot token placeholders in bot.py.")
    for index in range(5):
        threading.Thread(
            target=telegram_queue_worker,
            daemon=True,
            name=f"Worker-{index + 1}",
        ).start()

    run_rest_api_mode()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Bot] Exiting on user request...")
    except Exception as error:
        print(f"[Bot] ❌ Fatal error: {error}")
