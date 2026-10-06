# -*- coding: utf-8 -*-
"""
SharkSMS Live OTP Forwarder Bot for Telegram
=============================================
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
        print(f"[Bot] âš ï¸ Could not load processed file: {error}")
        return set()


processed_ids = load_processed()


def save_processed(uid):
    with file_lock:
        try:
            with open(PROCESSED_FILE, "a", encoding="utf-8") as file:
                file.write(f"{uid}\n")
        except Exception as error:
            print(f"[Bot] âš ï¸ Could not save processed ID: {error}")


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
    "Venezuela": ("VE", "ðŸ‡»ðŸ‡ª"),
    "Zimbabwe": ("ZW", "ðŸ‡¿ðŸ‡¼"),
    "Switzerland": ("CH", "ðŸ‡¨ðŸ‡­"),
    "Bolivia": ("BO", "ðŸ‡§ðŸ‡´"),
    "Ivory Coast": ("CI", "ðŸ‡¨ðŸ‡®"),
    "Guatemala": ("GT", "ðŸ‡¬ðŸ‡¹"),
    "Vietnam": ("VN", "ðŸ‡»ðŸ‡³"),
    "Afghanistan": ("AF", "ðŸ‡¦ðŸ‡«"),
    "Albania": ("AL", "ðŸ‡¦ðŸ‡±"),
    "Algeria": ("DZ", "ðŸ‡©ðŸ‡¿"),
    "Andorra": ("AD", "ðŸ‡¦ðŸ‡©"),
    "Angola": ("AO", "ðŸ‡¦ðŸ‡´"),
    "Antigua and Barbuda": ("AG", "ðŸ‡¦ðŸ‡¬"),
    "Argentina": ("AR", "ðŸ‡¦ðŸ‡·"),
    "Armenia": ("AM", "ðŸ‡¦ðŸ‡²"),
    "Australia": ("AU", "ðŸ‡¦ðŸ‡º"),
    "Austria": ("AT", "ðŸ‡¦ðŸ‡¹"),
    "Azerbaijan": ("AZ", "ðŸ‡¦ðŸ‡¿"),
    "Bahamas": ("BS", "ðŸ‡§ðŸ‡¸"),
    "Bahrain": ("BH", "ðŸ‡§ðŸ‡­"),
    "Bangladesh": ("BD", "ðŸ‡§ðŸ‡©"),
    "Barbados": ("BB", "ðŸ‡§ðŸ‡§"),
    "Belarus": ("BY", "ðŸ‡§ðŸ‡¾"),
    "Belgium": ("BE", "ðŸ‡§ðŸ‡ª"),
    "Belize": ("BZ", "ðŸ‡§ðŸ‡¿"),
    "Benin": ("BJ", "ðŸ‡§ðŸ‡¯"),
    "Bhutan": ("BT", "ðŸ‡§ðŸ‡¹"),
    "Bosnia and Herzegovina": ("BA", "ðŸ‡§ðŸ‡¦"),
    "Botswana": ("BW", "ðŸ‡§ðŸ‡¼"),
    "Brazil": ("BR", "ðŸ‡§ðŸ‡·"),
    "Brunei": ("BN", "ðŸ‡§ðŸ‡³"),
    "Bulgaria": ("BG", "ðŸ‡§ðŸ‡¬"),
    "Burkina Faso": ("BF", "ðŸ‡§ðŸ‡«"),
    "Burundi": ("BI", "ðŸ‡§ðŸ‡®"),
    "Cabo Verde": ("CV", "ðŸ‡¨ðŸ‡»"),
    "Cambodia": ("KH", "ðŸ‡°ðŸ‡­"),
    "Cameroon": ("CM", "ðŸ‡¨ðŸ‡²"),
    "Canada": ("CA", "ðŸ‡¨ðŸ‡¦"),
    "Central African Republic": ("CF", "ðŸ‡¨ðŸ‡«"),
    "Chad": ("TD", "ðŸ‡¹ðŸ‡©"),
    "Chile": ("CL", "ðŸ‡¨ðŸ‡±"),
    "China": ("CN", "ðŸ‡¨ðŸ‡³"),
    "Colombia": ("CO", "ðŸ‡¨ðŸ‡´"),
    "Comoros": ("KM", "ðŸ‡°ðŸ‡²"),
    "Congo": ("CG", "ðŸ‡¨ðŸ‡¬"),
    "Costa Rica": ("CR", "ðŸ‡¨ðŸ‡·"),
    "Croatia": ("HR", "ðŸ‡­ðŸ‡·"),
    "Cuba": ("CU", "ðŸ‡¨ðŸ‡º"),
    "Cyprus": ("CY", "ðŸ‡¨ðŸ‡¾"),
    "Czechia": ("CZ", "ðŸ‡¨ðŸ‡¿"),
    "Denmark": ("DK", "ðŸ‡©ðŸ‡°"),
    "Djibouti": ("DJ", "ðŸ‡©ðŸ‡¯"),
    "Dominica": ("DM", "ðŸ‡©ðŸ‡²"),
    "Dominican Republic": ("DO", "ðŸ‡©ðŸ‡´"),
    "Ecuador": ("EC", "ðŸ‡ªðŸ‡¨"),
    "Egypt": ("EG", "ðŸ‡ªðŸ‡¬"),
    "El Salvador": ("SV", "ðŸ‡¸ðŸ‡»"),
    "Equatorial Guinea": ("GQ", "ðŸ‡¬ðŸ‡¶"),
    "Eritrea": ("ER", "ðŸ‡ªðŸ‡·"),
    "Estonia": ("EE", "ðŸ‡ªðŸ‡ª"),
    "Eswatini": ("SZ", "ðŸ‡¸ðŸ‡¿"),
    "Ethiopia": ("ET", "ðŸ‡ªðŸ‡¹"),
    "Fiji": ("FJ", "ðŸ‡«ðŸ‡¯"),
    "Finland": ("FI", "ðŸ‡«ðŸ‡®"),
    "France": ("FR", "ðŸ‡«ðŸ‡·"),
    "Gabon": ("GA", "ðŸ‡¬ðŸ‡¦"),
    "Gambia": ("GM", "ðŸ‡¬ðŸ‡²"),
    "Georgia": ("GE", "ðŸ‡¬ðŸ‡ª"),
    "Germany": ("DE", "ðŸ‡©ðŸ‡ª"),
    "Ghana": ("GH", "ðŸ‡¬ðŸ‡­"),
    "Greece": ("GR", "ðŸ‡¬ðŸ‡·"),
    "Grenada": ("GD", "ðŸ‡¬ðŸ‡©"),
    "Guinea": ("GN", "ðŸ‡¬ðŸ‡³"),
    "Guinea-Bissau": ("GW", "ðŸ‡¬ðŸ‡¼"),
    "Guyana": ("GY", "ðŸ‡¬ðŸ‡¾"),
    "Haiti": ("HT", "ðŸ‡­ðŸ‡¹"),
    "Honduras": ("HN", "ðŸ‡­ðŸ‡³"),
    "Hungary": ("HU", "ðŸ‡­ðŸ‡º"),
    "Iceland": ("IS", "ðŸ‡®ðŸ‡¸"),
    "India": ("IN", "ðŸ‡®ðŸ‡³"),
    "Indonesia": ("ID", "ðŸ‡®ðŸ‡©"),
    "Iran": ("IR", "ðŸ‡®ðŸ‡·"),
    "Iraq": ("IQ", "ðŸ‡®ðŸ‡¶"),
    "Ireland": ("IE", "ðŸ‡®ðŸ‡ª"),
    "Israel": ("IL", "ðŸ‡®ðŸ‡±"),
    "Italy": ("IT", "ðŸ‡®ðŸ‡¹"),
    "Jamaica": ("JM", "ðŸ‡¯ðŸ‡²"),
    "Japan": ("JP", "ðŸ‡¯ðŸ‡µ"),
    "Jordan": ("JO", "ðŸ‡¯ðŸ‡´"),
    "Kazakhstan": ("KZ", "ðŸ‡°ðŸ‡¿"),
    "Kenya": ("KE", "ðŸ‡°ðŸ‡ª"),
    "Kiribati": ("KI", "ðŸ‡°ðŸ‡®"),
    "Korea, North": ("KP", "ðŸ‡°ðŸ‡µ"),
    "Korea, South": ("KR", "ðŸ‡°ðŸ‡·"),
    "Kuwait": ("KW", "ðŸ‡°ðŸ‡¼"),
    "Kyrgyzstan": ("KG", "ðŸ‡°ðŸ‡¬"),
    "Laos": ("LA", "ðŸ‡±ðŸ‡¦"),
    "Latvia": ("LV", "ðŸ‡±ðŸ‡»"),
    "Lebanon": ("LB", "ðŸ‡±ðŸ‡§"),
    "Lesotho": ("LS", "ðŸ‡±ðŸ‡¸"),
    "Liberia": ("LR", "ðŸ‡±ðŸ‡·"),
    "Libya": ("LY", "ðŸ‡±ðŸ‡¾"),
    "Liechtenstein": ("LI", "ðŸ‡±ðŸ‡®"),
    "Lithuania": ("LT", "ðŸ‡±ðŸ‡¹"),
    "Luxembourg": ("LU", "ðŸ‡±ðŸ‡º"),
    "Madagascar": ("MG", "ðŸ‡²ðŸ‡¬"),
    "Malawi": ("MW", "ðŸ‡²ðŸ‡¼"),
    "Malaysia": ("MY", "ðŸ‡²ðŸ‡¾"),
    "Maldives": ("MV", "ðŸ‡²ðŸ‡»"),
    "Mali": ("ML", "ðŸ‡²ðŸ‡±"),
    "Malta": ("MT", "ðŸ‡²ðŸ‡¹"),
    "Marshall Islands": ("MH", "ðŸ‡²ðŸ‡­"),
    "Mauritania": ("MR", "ðŸ‡²ðŸ‡·"),
    "Mauritius": ("MU", "ðŸ‡²ðŸ‡º"),
    "Mexico": ("MX", "ðŸ‡²ðŸ‡½"),
    "Micronesia": ("FM", "ðŸ‡«ðŸ‡²"),
    "Moldova": ("MD", "ðŸ‡²ðŸ‡©"),
    "Monaco": ("MC", "ðŸ‡²ðŸ‡¨"),
    "Mongolia": ("MN", "ðŸ‡²ðŸ‡³"),
    "Montenegro": ("ME", "ðŸ‡²ðŸ‡ª"),
    "Morocco": ("MA", "ðŸ‡²ðŸ‡¦"),
    "Mozambique": ("MZ", "ðŸ‡²ðŸ‡¿"),
    "Myanmar": ("MM", "ðŸ‡²ðŸ‡²"),
    "Namibia": ("NA", "ðŸ‡³ðŸ‡¦"),
    "Nauru": ("NR", "ðŸ‡³ðŸ‡·"),
    "Nepal": ("NP", "ðŸ‡³ðŸ‡µ"),
    "Netherlands": ("NL", "ðŸ‡³ðŸ‡±"),
    "New Zealand": ("NZ", "ðŸ‡³ðŸ‡¿"),
    "Nicaragua": ("NI", "ðŸ‡³ðŸ‡®"),
    "Niger": ("NE", "ðŸ‡³ðŸ‡ª"),
    "Nigeria": ("NG", "ðŸ‡³ðŸ‡¬"),
    "North Macedonia": ("MK", "ðŸ‡²ðŸ‡°"),
    "Norway": ("NO", "ðŸ‡³ðŸ‡´"),
    "Oman": ("OM", "ðŸ‡´ðŸ‡²"),
    "Pakistan": ("PK", "ðŸ‡µðŸ‡°"),
    "Palau": ("PW", "ðŸ‡µðŸ‡¼"),
    "Panama": ("PA", "ðŸ‡µðŸ‡¦"),
    "Papua New Guinea": ("PG", "ðŸ‡µðŸ‡¬"),
    "Paraguay": ("PY", "ðŸ‡µðŸ‡¾"),
    "Peru": ("PE", "ðŸ‡µðŸ‡ª"),
    "Philippines": ("PH", "ðŸ‡µðŸ‡­"),
    "Poland": ("PL", "ðŸ‡µðŸ‡±"),
    "Portugal": ("PT", "ðŸ‡µðŸ‡¹"),
    "Qatar": ("QA", "ðŸ‡¶ðŸ‡¦"),
    "Romania": ("RO", "ðŸ‡·ðŸ‡´"),
    "Russia": ("RU", "ðŸ‡·ðŸ‡º"),
    "Rwanda": ("RW", "ðŸ‡·ðŸ‡¼"),
    "Saint Kitts and Nevis": ("KN", "ðŸ‡°ðŸ‡³"),
    "Saint Lucia": ("LC", "ðŸ‡±ðŸ‡¨"),
    "Saint Vincent and the Grenadines": ("VC", "ðŸ‡»ðŸ‡¨"),
    "Samoa": ("WS", "ðŸ‡¼ðŸ‡¸"),
    "San Marino": ("SM", "ðŸ‡¸ðŸ‡²"),
    "Sao Tome and Principe": ("ST", "ðŸ‡¸ðŸ‡¹"),
    "Saudi Arabia": ("SA", "ðŸ‡¸ðŸ‡¦"),
    "Senegal": ("SN", "ðŸ‡¸ðŸ‡³"),
    "Serbia": ("RS", "ðŸ‡·ðŸ‡¸"),
    "Seychelles": ("SC", "ðŸ‡¸ðŸ‡¨"),
    "Sierra Leone": ("SL", "ðŸ‡¸ðŸ‡±"),
    "Singapore": ("SG", "ðŸ‡¸ðŸ‡¬"),
    "Slovakia": ("SK", "ðŸ‡¸ðŸ‡°"),
    "Slovenia": ("SI", "ðŸ‡¸ðŸ‡®"),
    "Solomon Islands": ("SB", "ðŸ‡¸ðŸ‡§"),
    "Somalia": ("SO", "ðŸ‡¸ðŸ‡´"),
    "South Africa": ("ZA", "ðŸ‡¿ðŸ‡¦"),
    "South Sudan": ("SS", "ðŸ‡¸ðŸ‡¸"),
    "Spain": ("ES", "ðŸ‡ªðŸ‡¸"),
    "Sri Lanka": ("LK", "ðŸ‡±ðŸ‡°"),
    "Sudan": ("SD", "ðŸ‡¸ðŸ‡©"),
    "Suriname": ("SR", "ðŸ‡¸ðŸ‡·"),
    "Sweden": ("SE", "ðŸ‡¸ðŸ‡ª"),
    "Syria": ("SY", "ðŸ‡¸ðŸ‡¾"),
    "Taiwan": ("TW", "ðŸ‡¹ðŸ‡¼"),
    "Tajikistan": ("TJ", "ðŸ‡¹ðŸ‡¯"),
    "Tanzania": ("TZ", "ðŸ‡¹ðŸ‡¿"),
    "Thailand": ("TH", "ðŸ‡¹ðŸ‡­"),
    "Timor-Leste": ("TL", "ðŸ‡¹ðŸ‡±"),
    "Togo": ("TG", "ðŸ‡¹ðŸ‡¬"),
    "Tonga": ("TO", "ðŸ‡¹ðŸ‡´"),
    "Trinidad and Tobago": ("TT", "ðŸ‡¹ðŸ‡¹"),
    "Tunisia": ("TN", "ðŸ‡¹ðŸ‡³"),
    "Turkey": ("TR", "ðŸ‡¹ðŸ‡·"),
    "Turkmenistan": ("TM", "ðŸ‡¹ðŸ‡²"),
    "Tuvalu": ("TV", "ðŸ‡¹ðŸ‡»"),
    "Uganda": ("UG", "ðŸ‡ºðŸ‡¬"),
    "Ukraine": ("UA", "ðŸ‡ºðŸ‡¦"),
    "United Arab Emirates": ("AE", "ðŸ‡¦ðŸ‡ª"),
    "United Kingdom": ("GB", "ðŸ‡¬ðŸ‡§"),
    "United States": ("US", "ðŸ‡ºðŸ‡¸"),
    "Uruguay": ("UY", "ðŸ‡ºðŸ‡¾"),
    "Uzbekistan": ("UZ", "ðŸ‡ºðŸ‡¿"),
    "Vanuatu": ("VU", "ðŸ‡»ðŸ‡º"),
    "Vatican City": ("VA", "ðŸ‡»ðŸ‡¦"),
    "Yemen": ("YE", "ðŸ‡¾ðŸ‡ª"),
    "Zambia": ("ZM", "ðŸ‡¿ðŸ‡²"),
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
    (["WHATSAPP", "WS"], "5393189591773630465", "ðŸ’¬", "WS"),
    (["FACEBOOK", "FB"], "5393310276059678201", "ðŸ‘¤", "FB"),
    (["TELEGRAM"], "5364125616801073577", "âœˆï¸", "TG"),
    (["GOOGLE", "GMAIL"], "5393197447268813836", "ðŸ”", "GG"),
    (["INSTAGRAM"], "5393603871434099925", "ðŸ“¸", "IG"),
    (["WECHAT"], "6113767082636087326", "ðŸŸ¢", "WC"),
    (["TIKTOK"], "5393189789342123585", "ðŸŽµ", "TT"),
    (["TWITTER", "X"], "5393608179286297620", "ðŸ¦", "TW"),
    (["LINE"], "6244519961734156213", "ðŸ’š", "LN"),
    (["VIBER"], "5463060437572528782", "ðŸ’œ", "VB"),
    (["SIGNAL"], "6089079919856325971", "ðŸ”’", "SG"),
    (["DISCORD"], "5300896830551254527", "ðŸŽ®", "DC"),
    (["SNAPCHAT"], "5330248916224983855", "ðŸ‘»", "SC"),
    (["MICROSOFT", "HOTMAIL"], "5979047775470358891", "ðŸªŸ", "MS"),
    (["APPLE", "ICLOUD"], "5318795767454923927", "ðŸŽ", "AP"),
    (["AMAZON"], "5323624199753842832", "ðŸ“¦", "AM"),
    (["NETFLIX"], "5418026554422750284", "ðŸŽ¬", "NF"),
    (["UBER"], "5298715455316303708", "ðŸš—", "UB"),
    (["PAYPAL"], "5776103539872896061", "ðŸ’³", "PP"),
    (["LINKEDIN"], "6224222994265279792", "ðŸ’¼", "LI"),
]


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

    country_name_raw = (
        range_value.split("-")[0].strip()
        if "-" in range_value
        else range_value
    )
    country_code, flag = "UN", "ðŸŒ"

    for name, (code, country_flag) in COUNTRY_MAP.items():
        if name.lower() in country_name_raw.lower():
            country_code = code
            flag = country_flag
            break

    formatted_number = (
        f"{number_raw[:3]}XXX{number_raw[-4:]}"
        if len(number_raw) >= 7
        else number_raw
    )

    emoji_id, service_emoji, service_short = (
        "5462933547058749789",
        "ðŸ‘¤",
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
                                f"[Bot] âœ… OTP dispatched successfully to "
                                f"{clean_chat_id}"
                            )
                            chat_success = True
                            break

                        attempts += 1
                        description = response_json.get("description", "Unknown")
                        print(f"[Bot] âŒ Telegram API error: {description}")
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
                        print("[Bot] âš ï¸ Telegram flood control; waiting 2s")
                        time.sleep(2)
                    else:
                        attempts += 1
                        print(
                            f"[Bot] âŒ Telegram HTTP {response.status_code}: "
                            f"{response.text[:200]}"
                        )
                        time.sleep(2)
                except Exception as error:
                    attempts += 1
                    print(f"[Bot] âŒ Send attempt {attempts} error: {error}")
                    time.sleep(2)

            if not chat_success:
                overall_success = False

        return overall_success
    except Exception as error:
        print(f"[Bot] âŒ Format/send error: {error}")
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
                print(f"[Bot] ðŸš€ Forwarded to Telegram: {number_display}")
                for uid in uids:
                    save_processed(uid)
            else:
                number_display = (
                    item.get("receivedNumber")
                    or item.get("number")
                    or item.get("num")
                )
                print(f"[Bot] âŒ Failed to forward: {number_display}")
                with file_lock:
                    for uid in uids:
                        processed_ids.discard(uid)

            msg_queue.task_done()
            time.sleep(0.05)
        except Exception as error:
            print(f"[Bot] âŒ Worker error: {error}")
            time.sleep(1)


# ==============================================================================
# SHARKSMS REST API POLLING
# ==============================================================================
def run_rest_api_mode():
    """Poll the official SharkSMS REST API using a Bearer token."""
    print("[Engine] âš¡ Starting SharkSMS REST API mode...")
    print(
        f"[Engine] ðŸ”‘ Bearer token: {SHARKSMS_API_TOKEN[:6]}..."
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
                print("[Engine] â„¹ï¸ /messages returned 404; switching to /cdrs...")
                active_url = endpoints[1]
                continue
            elif response.status_code == 401:
                print("[Engine] âŒ 401 Unauthorized: invalid API token")
                time.sleep(10)
            elif response.status_code == 429:
                print("[Engine] âš ï¸ Rate limit reached; backing off for 5s...")
                time.sleep(5)
            else:
                print(
                    f"[Engine] âš ï¸ SharkSMS API HTTP {response.status_code}: "
                    f"{response.text[:150]}"
                )
        except Exception as error:
            print(f"[Engine] âš ï¸ Polling error: {error}")

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
            print(f"[Bot] âš ï¸ Row parse error: {error}")

    if not valid_rows:
        return

    if not INITIAL_SYNC_DONE:
        print(
            f"[Bot] ðŸ”„ Initial sync: recording {len(valid_rows)} existing items..."
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
            f"[Bot] ðŸ§ª Sending latest SMS as startup test to Telegram: "
            f"{test_number}"
        )

        if send_sms_to_telegram(recent_item):
            print(f"[Bot] âœ… Startup test delivered successfully â†’ {test_number}")
        else:
            print("[Bot] âš ï¸ Startup test failed to send.")

        INITIAL_SYNC_DONE = True
        print("[Bot] ðŸŸ¢ Live OTP monitoring is active.")
    else:
        for item in valid_rows:
            uids = get_item_uids(item)
            if not any(uid in processed_ids for uid in uids):
                number_display = (
                    item.get("receivedNumber")
                    or item.get("number")
                    or item.get("num")
                )
                print(f"[Bot] ðŸ†• New live OTP received â†’ {number_display}")

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
    print("ðŸ¦ˆ SharkSMS Telegram Live OTP Forwarder Bot")
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
        print(f"[Bot] âŒ Fatal error: {error}")
