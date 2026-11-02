import os
import re
import html
import json
import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STORAGE_FILE = "last_ids.json"

CATEGORIES = [
    {
        "board_id": "0",  # หมวดรวมโพสต์สำหรับทดสอบ (เทสเสร็จแล้วลบออกได้)
        "name": "🔥 รวมโพสต์ทั้งหมด",
        "color": 0xE74C3C
    },
    {
        "board_id": "3",
        "name": "🛠️ ประกาศอัปเดต",
        "color": 0x3498DB
    },
    {
        "board_id": "4",
        "name": "🎟️ คูปอง / กิจกรรม",
        "color": 0xF1C40F
    },
    {
        "board_id": "7",
        "name": "📝 Dev Note",
        "color": 0x9B59B6
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

def clean_html_to_markdown(raw_html):
    """แปลงแท็ก HTML ในเนื้อหาโพสต์ให้กลายเป็นข้อความอ่านง่ายบน Discord"""
    if not raw_html:
        return ""
    text = re.sub(r'<\s*br\s*/?>', '\n', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/p\s*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/div\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def fetch_feed_detail(feed_id):
    """ดึงข้อมูลเนื้อหาและรูปภาพฉบับเต็มของโพสต์"""
    url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed/{feed_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("content", {}).get("feed")
    except Exception as e:
        print(f"Error fetching detail {feed_id}: {e}", flush=True)
    return None

def fetch_lounge_feeds(board_id):
