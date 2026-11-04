import os
import re
import html
import json
import requests
from datetime import datetime, timezone, timedelta

# ดึง Token และ ID ห้องสำหรับ Webtoon จาก Environment (ตั้งค่าใน Secrets)
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID_WEBTOON = os.environ.get("DISCORD_CHANNEL_ID_WEBTOON") 
STORAGE_FILE = "last_webtoon_ids.json"
TARGET_BOARD_ID = "6"

def load_last_ids():
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

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

def fetch_lounge_feeds():
    api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={TARGET_BOARD_ID}&buffFilteringYN=N&limit=15&offset=0&order=NEW"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/{TARGET_BOARD_ID}"}
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200:
            content = res.json().get("content", {})
            return content.get("noticeFeeds", []) + content.get("feeds", [])
    except Exception as e:
        print(f"Error fetching webtoon feeds: {e}", flush=True)
    return []

def send_to_discord_bot(payload):
    if not CHANNEL_ID_WEBTOON:
        print("Error: Webtoon channel ID is empty!", flush=True)
        return
        
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID_WEBTOON}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    requests.post(url, headers=headers, json=payload)

def send_webtoon_to_discord(feed_summary):
    feed_id = str(feed_summary.get("feedId"))
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    target_data = fetch_feed_detail(feed_id) or feed_summary
    title = target_data.get("title") or "웹툰"
    raw_contents = target_data.get("contents") or ""
    color = 0x2ECC71 # สีเขียวสำหรับ Webtoon
    
    date_str = format_thai_time(target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("timestamp"))
    thumb_url = next((rep.get("path") for rep in target_data.get("representations", []) if rep.get("representationType") == "IMAGE" and rep.get("path")), None)

    # 1. ส่งหน้าปกและลิงก์
    header_embed = {
        "title": f"트릭컬 리바이브 - 웹툰 (Webtoon)", 
        "description": f"**{title}**\n{date_str}   |   ID: {feed_id}", 
        "color": color
    }
    if thumb_url: header_embed["thumbnail"] = {"url": thumb_url}

    payload_header = {
        "embeds": [header_embed],
        "components": [{
            "type": 1,
            "components": [{
                "type": 2, "style": 5, "label": " อ่านในเว็บ Naver", "url": post_url, "emoji": {"name": "🟢"}
            }]
        }]
    }
    send_to_discord_bot(payload_header)

    # 2. ส่งเนื้อหาและรูปภาพ (Webtoon มักจะมีรูปเยอะ โค้ดนี้จะช่วยสอยรูปมาเรียงให้)
    sections = parse_html_to_sections(raw_contents)
    content_embeds = []
    
    for sec in sections:
        sec_text = sec["text"][:2000].rstrip() + "..." if len(sec["text"]) > 2000 else sec["text"]
        emb = {"color": color}
        if sec_text: emb["description"] = sec_text
        if sec["image"]: emb["image"] = {"url": sec["image"]}
        if emb.get("description") or emb.get("image"): content_embeds.append(emb)

    if len(content_embeds) > 25:
        content_embeds = content_embeds[:25]
        content_embeds.append({"description": "[ รูปภาพหรือเนื้อหาเยอะเกินไป กรุณากดอ่านต่อในลิงก์หลัก ]", "color": color})

    MAX_EMBEDS = 10 
    for i in range(0, len(content_embeds), MAX_EMBEDS):
        batch = content_embeds[i:i + MAX_EMBEDS]
        send_to_discord_bot({"embeds": batch})

def run():
    if not BOT_TOKEN or not CHANNEL_ID_WEBTOON:
        print("Missing BOT_TOKEN or DISCORD_CHANNEL_ID_WEBTOON", flush=True)
        return

    seen_ids = load_last_ids()
    feeds = fetch_lounge_feeds()
    
    if not feeds:
        return

    # ลบข้อมูลที่ซ้ำกันออก
    unique_feeds = []
    temp_seen = set()
    for f in feeds:
        fid = str(f.get("feedId"))
        if fid not in temp_seen:
            temp_seen.add(fid)
            unique_feeds.append(f)

    if not seen_ids:
        save_last_ids([str(f.get("feedId")) for f in unique_feeds])
        print("Initial run: Saved current Webtoon history.")
        return

    is_test_mode = "0" in seen_ids
    new_posts = [f for f in unique_feeds if str(f.get("feedId")) not in seen_ids]

    if is_test_mode and new_posts: 
        new_posts = new_posts[:3]
        seen_ids = [x for x in seen_ids if x != "0"]

    if new_posts:
        posts_to_send = new_posts[:3] # ล็อกลิมิตส่งสูงสุด 3 โพสต์
        for post in reversed(posts_to_send): 
            send_webtoon_to_discord(post)

        for f in unique_feeds:
            fid = str(f.get("feedId"))
            if fid not in seen_ids:
                seen_ids.append(fid)

        save_last_ids(seen_ids[-50:]) # เก็บย้อนหลัง 50 โพสต์

if __name__ == "__main__":
    run()
