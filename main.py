import os
import re
import html
import json
import requests
from datetime import datetime, timezone, timedelta

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STORAGE_FILE = "last_ids.json"

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

def format_thai_time(timestamp_val):
    kst = timezone(timedelta(hours=9))
    if timestamp_val and (isinstance(timestamp_val, (int, float)) or (isinstance(timestamp_val, str) and timestamp_val.isdigit())):
        dt = datetime.fromtimestamp(int(timestamp_val) / 1000, tz=kst)
    else:
        dt = datetime.now(tz=kst)
        
    thai_months = [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    return f"{dt.day} {thai_months[dt.month-1]} {dt.year} {dt.hour:02d}:{dt.minute:02d} น."

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
                return f"[[IMG_TOKEN:{img_url}]]"
        return ""

    text = re.sub(r'<img[^>]+>', img_replacer, raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<\s*br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:p|div|h[1-6]|tr|li|ul|ol)\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:td|th)\s*>', ' ', text, flags=re.IGNORECASE)
    
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    
    text = text.replace("\xa0", " ").replace("\u200b", "")
    
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', text)
    text = text.strip()

    tokens = re.split(r'\[\[IMG_TOKEN:(https?://[^\]]+)\]\]', text)
    sections = []
    
    for i in range(0, len(tokens), 2):
        txt = tokens[i].strip()
        txt = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', txt)
        img = tokens[i+1].strip() if i+1 < len(tokens) else None
        
        if txt or img:
            sections.append({"text": txt, "image": img})

    return sections

def fetch_feed_detail(feed_id):
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
    api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={board_id}&buffFilteringYN=N&limit=5&offset=0&order=NEW"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://game.naver.com/lounge/Trickcal/board/{board_id}"
    }
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("content", {}).get("feeds", [])
    except Exception as e:
        print(f"Board {board_id} Error: {e}", flush=True)
    return []

def send_to_discord(feed_summary, category):
    feed_id = str(feed_summary.get("feedId"))
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    full_detail = fetch_feed_detail(feed_id)
    target_data = full_detail if full_detail else feed_summary

    title = target_data.get("title") or "공지사항"
    raw_contents = target_data.get("contents") or ""
    color = category["color"]
    
    raw_time = target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("writeDate") or target_data.get("timestamp")
    date_str = format_thai_time(raw_time)

    thumb_url = None
    for rep in target_data.get("representations", []):
        if rep.get("representationType") == "IMAGE" and rep.get("path"):
            thumb_url = rep.get("path")
            break

    # ==========================================
    # ส่งข้อความก้อนที่ 1: Header + Date + Button
    # ==========================================
    header_embed = {
        "title": "트릭컬 리바이브",
        "description": f"**{title}**",
        "color": color
    }
    if thumb_url:
        header_embed["thumbnail"] = {"url": thumb_url}
        
    meta_embed = {
        "description": f"{date_str}   |   ID: {feed_id}",
        "color": color
    }

    # โครงสร้าง UI ปุ่ม Discord (Action Row)
    payload_header = {
        "username": "เคธี่นักสอดแนม",
        "embeds": [header_embed, meta_embed],
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 5,
                        "label": "ไปที่ลิงก์",
                        "url": post_url,
                        "emoji": {
                            "name": "🟢" 
                        }
                    }
                ]
            }
        ]
    }
    requests.post(WEBHOOK_URL, json=payload_header)


    # ==========================================
    # ส่งข้อความก้อนที่ 2: เนื้อหา Sections
    # ==========================================
    sections = parse_html_to_sections(raw_contents)
    content_embeds = []

    for sec in sections:
        sec_text = sec["text"]
        sec_img = sec["image"]

        if not sec_text and not sec_img:
            continue

        if len(sec_text) > 2000:
            sec_text = sec_text[:2000].rstrip() + "..."

        emb = {"color": color}
        if sec_text:
            emb["description"] = sec_text
        if sec_img:
            emb["image"] = {"url": sec_img}

        content_embeds.append(emb)

    MAX_TOTAL_EMBEDS = 25
    if len(content_embeds) > MAX_TOTAL_EMBEDS:
        content_embeds = content_embeds[:MAX_TOTAL_EMBEDS]
        content_embeds.append({
            "description": "[ คอมโพเนนต์เกินขีดจำกัด ขอละรายละเอียดบางส่วนไว้ ]",
            "color": color
        })

    batch_size = 10
    for i in range(0, len(content_embeds), batch_size):
        batch = content_embeds[i:i + batch_size]
        payload_content = {
            "username": "เคธี่ นักสอดแนม",
            "embeds": batch
        }
        resp = requests.post(WEBHOOK_URL, json=payload_content)
        print(f"Sent content batch {i//batch_size + 1} for ID {feed_id} - Status: {resp.status_code}", flush=True)

def run():
    if not WEBHOOK_URL:
        print("Missing DISCORD_WEBHOOK", flush=True)
        return

    last_ids = load_last_ids()
    updated = False

    for cat in CATEGORIES:
        board_id = cat["board_id"]
        feeds = fetch_lounge_feeds(board_id)
        if not feeds:
            continue

        saved_id = str(last_ids.get(board_id, ""))
        latest_id = str(feeds[0].get("feedId"))

        if not saved_id:
            last_ids[board_id] = latest_id
            updated = True
            print(f"Board {board_id}: Initialized ID to {latest_id}", flush=True)
            continue

        new_posts = []
        for feed in feeds:
            f_id = str(feed.get("feedId"))
            if f_id == saved_id:
                break
            new_posts.append(feed)

        if saved_id == "0" and len(new_posts) > 0:
            new_posts = [new_posts[0]]

        if new_posts:
            print(f"Board {board_id}: Found {len(new_posts)} new posts. Sending...", flush=True)
            for post in reversed(new_posts):
                send_to_discord(post, cat)
            last_ids[board_id] = latest_id
            updated = True
        else:
            print(f"Board {board_id}: Up to date", flush=True)

    if updated:
        save_last_ids(last_ids)

if __name__ == "__main__":
    run()
