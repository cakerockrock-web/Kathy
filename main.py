import os
import re
import html
import json
import requests
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID_MAIN = os.environ.get("DISCORD_CHANNEL_ID")
CHANNEL_ID_COUPON = os.environ.get("DISCORD_CHANNEL_ID_COUPON") 
STORAGE_FILE = "last_ids.json"

TARGET_BOARD_IDS = ["13", "11", "31", "8"]

BOARD_METADATA = {
    "13": {"name": "공지사항 (ประกาศหลัก)", "color": 0x3498DB},
    "11": {"name": "이벤트/업데이트 (อัปเดต / กิจกรรม)", "color": 0xF1C40F},
    "31": {"name": "개발자 노트 (Dev Note)", "color": 0x9E6649},
    "8":  {"name": "패치노트 (Patch Note)", "color": 0xE67E22},
    "default": {"name": "공지사항 (ประกาศ)", "color": 0x95A5A6}
}

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

def format_thai_time(timestamp_val):
    kst = timezone(timedelta(hours=9))
    if timestamp_val and (isinstance(timestamp_val, (int, float)) or (isinstance(timestamp_val, str) and timestamp_val.isdigit())):
        dt = datetime.fromtimestamp(int(timestamp_val) / 1000, tz=kst)
    else:
        dt = datetime.now(tz=kst)
    thai_months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"{dt.day} {thai_months[dt.month-1]} {dt.year} {dt.hour:02d}:{dt.minute:02d} น."

def parse_html_to_sections(raw_html):
    if not raw_html: return []
    def img_replacer(match):
        tag = match.group(0)
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if m:
            img_url = m.group(1).strip()
            if img_url.startswith("//"): img_url = "https:" + img_url
            if img_url.startswith("http"): return f"[[IMG_TOKEN:{img_url}]]"
        return ""
    text = re.sub(r'<img[^>]+>', img_replacer, raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<\s*br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:p|div|h[1-6]|tr|li|ul|ol)\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:td|th)\s*>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', text).strip()

    tokens = re.split(r'\[\[IMG_TOKEN:(https?://[^\]]+)\]\]', text)
    sections = []
    for i in range(0, len(tokens), 2):
        txt = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', tokens[i].strip())
        img = tokens[i+1].strip() if i+1 < len(tokens) else None
        if txt or img: sections.append({"text": txt, "image": img})
    return sections

def extract_coupon_info(text):
    coupon_code = "N/A"
    claim_period = None
    
    match_code = re.search(r'쿠폰\s*코드[^\n]*\n+([^\n]+)', text)
    if match_code:
        coupon_code = match_code.group(1).replace('◆', '').replace('◇', '').strip()
        
    if coupon_code == "N/A" or not coupon_code:
        code_match = re.search(r'([A-Z0-9]{6,20})', text)
        if code_match:
            coupon_code = code_match.group(1)
            
    match_period = re.search(r'사용\s*기한[^\n]*\n+([^\n]+)', text)
    if match_period:
        claim_period = match_period.group(1).strip()
        if claim_period.startswith("-"):
            claim_period = claim_period[1:].strip()
            
    return coupon_code, claim_period

def fetch_feed_detail(feed_id):
    url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed/{feed_id}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200: return res.json().get("content", {}).get("feed")
    except Exception as e:
        print(f"Error fetching detail {feed_id}: {e}", flush=True)
    return None

def fetch_lounge_feeds(board_id):
    api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={board_id}&buffFilteringYN=N&limit=15&offset=0&order=NEW"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/{board_id}"}
    try:
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code == 200:
            content = res.json().get("content", {})
            notice_feeds = content.get("noticeFeeds") or []
            normal_feeds = content.get("feeds") or []
            combined = notice_feeds + normal_feeds

            seen_ids = set()
            unique_feeds = []
            for feed in combined:
                fid = str(feed.get("feedId"))
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    unique_feeds.append(feed)
            return unique_feeds
    except Exception as e:
        print(f"Error fetching feeds for board {board_id}: {e}", flush=True)
    return []

def send_to_discord_bot(payload, target_channel):
    if not target_channel:
        print("Error: Target channel ID is empty!", flush
