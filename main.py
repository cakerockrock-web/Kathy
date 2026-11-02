import os
import re
import html
import json
import requests
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID")
STORAGE_FILE = "last_ids.json"

CATEGORIES = [
    {"board_id": "8", "name": "공지사항 (ประกาศอัปเดต)", "color": 0x3498DB},
    {"board_id": "11", "name": "이벤트 (คูปอง / กิจกรรม)", "color": 0xF1C40F},
    {"board_id": "31", "name": "개발자 노트 (Dev Note)", "color": 0x9E6649}
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

def fetch_feed_detail(feed_id):
    url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed/{feed_id}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200: return res.json().get("content", {}).get("feed")
    except: pass
    return None

def fetch_lounge_feeds(board_id):
    api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={board_id}&buffFilteringYN=N&limit=5&offset=0&order=NEW"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/{board_id}"}
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200: return res.json().get("content", {}).get("feeds", [])
    except: pass
    return []

def send_to_discord_bot(payload):
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, headers=headers, json=payload)
    return resp.status_code

def send_to_discord(feed_summary, category):
    feed_id = str(feed_summary.get("feedId"))
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    target_data = fetch_feed_detail(feed_id) or feed_summary
    title = target_data.get("title") or "공지사항"
    raw_contents = target_data.get("contents") or ""
    color = category["color"]
    date_str = format_thai_time(target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("timestamp"))

    thumb_url = next((rep.get("path") for rep in target_data.get("representations", []) if rep.get("representationType") == "IMAGE" and rep.get("path")), None)

    header_embed = {"title": "트릭컬 리바이브", "description": f"**{title}**", "color": color}
    if thumb_url: header_embed["thumbnail"] = {"url": thumb_url}
    meta_embed = {"description": f"{date_str}   |   ID: {feed_id}", "color": color}

    payload_header = {
        "embeds": [header_embed, meta_embed],
        "components": [{
            "type": 1,
            "components": [{
                "type": 2,
                "style": 5,
                "label": " ไปที่ลิงก์", 
                "url": post_url,
                "emoji": {"name": "🟢"}
            }]
        }]
    }
    send_to_discord_bot(payload_header)

    sections = parse_html_to_sections(raw_contents)
    content_embeds = []
    for sec in sections:
        sec_text = sec["text"][:2000].rstrip() + "..." if len(sec["text"]) > 2000 else sec["text"]
        emb = {"color": color}
        if sec_text: emb["description"] = sec_text
        if sec["image"]: emb["image"] = {"url": sec["image"]}
        if emb.get("description") or emb.get("image"): content_embeds.append(emb)

    MAX_EMBEDS = 10 
    for i in range(0, len(content_embeds), MAX_EMBEDS):
        batch = content_embeds[i:i + MAX_EMBEDS]
        if i + MAX_EMBEDS >= len(content_embeds) and len(content_embeds) > 25:
            batch.append({"description": "[ คอมโพเนนต์เกินขีดจำกัด ขอละรายละเอียดบางส่วนไว้ ]", "color": color})
        send_to_discord_bot({"embeds": batch})

def run():
    if not BOT_TOKEN or not CHANNEL_ID:
        print("Missing BOT_TOKEN or CHANNEL_ID", flush=True)
        return

    last_ids = load_last_ids()
    updated = False

    for cat in CATEGORIES:
        board_id = cat["board_id"]
        feeds = fetch_lounge_feeds(board_id)
        if not feeds: continue

        saved_id = str(last_ids.get(board_id, ""))
        latest_id = str(feeds[0].get("feedId"))

        if not saved_id:
            last_ids[board_id] = latest_id
            updated = True
            continue

        # --- แก้ไขลอจิกตรงนี้ให้กลับมาเป็นแบบเดิม ทำงานถูกต้องชัวร์ๆ ---
        new_posts = []
        for feed in feeds:
            f_id = str(feed.get("feedId"))
            if f_id == saved_id:
                break
            new_posts.append(feed)

        # โหมดเทส
        if saved_id == "0" and len(new_posts) > 0: 
            new_posts = [new_posts[0]]

        if new_posts:
            for post in reversed(new_posts): 
                send_to_discord(post, cat)
            last_ids[board_id] = latest_id
            updated = True

    if updated: save_last_ids(last_ids)

if __name__ == "__main__":
    run()
