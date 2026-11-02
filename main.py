import os
import re
import html
import json
import requests
from datetime import datetime, timezone, timedelta

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STORAGE_FILE = "last_ids.json"

# กำหนดหมวดหมู่ตามลิงก์ที่ให้มา
CATEGORIES = [
    {
        "board_id": "8",
        "name": "공지사항 (ประกาศอัปเดต)",
        "color": 0x3498DB
    },
    {
        "board_id": "11",
        "name": "이벤트 (คูปอง / กิจกรรม)",
        "color": 0xF1C40F
    },
    {
        "board_id": "31",
        "name": "개발자 노트 (Dev Note)",
        "color": 0x9E6649
    }
]

def load_last_ids():
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_last_ids(data):
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def format_kst_time(timestamp_val):
    if not timestamp_val:
        return ""
    try:
        kst = timezone(timedelta(hours=9))
        if isinstance(timestamp_val, (int, float)) or (isinstance(timestamp_val, str) and timestamp_val.isdigit()):
            dt = datetime.fromtimestamp(int(timestamp_val) / 1000, tz=kst)
        else:
            dt = datetime.now(tz=kst)
        return f"{dt.year}년 {dt.month}월 {dt.day}일 {dt.hour}시 {dt.minute}분"
    except Exception:
        return ""

def parse_html_to_sections(raw_html):
    if not raw_html:
        return []

    def img_replacer(match):
        tag = match.group(0)
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if m:
            img_url = m.group(1).strip()
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            if img_url.startswith("http"):
                return f"\n\n[[IMG_TOKEN:{img_url}]]\n\n"
        return ""

    text = re.sub(r'<img[^>]+>', img_replacer, raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<\s*br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/p\s*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/div\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/h[1-6]\s*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    tokens = re.split(r'\[\[IMG_TOKEN:(https?://[^\]]+)\]\]', text)
    sections = []
    
    first_text = tokens[0].strip()
    if first_text:
        sections.append({"text": first_text, "image": None})

    i = 1
    while i < len(tokens):
        img_url = tokens[i].strip()
        following_text = tokens[i+1].strip() if i+1 < len(tokens) else ""
        
        if sections and sections[-1]["image"] is None:
            sections[-1]["image"] = img_url
            if following_text:
                sections.append({"text": following_text, "image": None})
        else:
            sections.append({"text": following_text, "image": img_
