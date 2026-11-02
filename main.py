import os
import re
import html
import json
import requests
from datetime import datetime, timezone, timedelta

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STORAGE_FILE = "last_ids.json"

# เหลือเฉพาะหมวด Official เท่านั้น
CATEGORIES = [
    {
        "board_id": "3",
        "name": "공지사항",
        "color": 0x3498DB
    },
    {
        "board_id": "4",
        "name": "이벤트",
        "color": 0xF1C40F
    },
    {
        "board_id": "7",
        "name": "개발자 노트",
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
            sections.append({"text": following_text, "image": img_url})
        i += 2

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
    api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={board_id}&limit=5&order=NEW"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://game.naver.com/lounge/Trickcal/board"
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
    created_at = target_data.get("created_at") or target_data.get("createdAt")
    date_str = format_kst_time(created_at)

    thumb_url = None
    for rep in target_data.get("representations", []):
        if rep.get("representationType") == "IMAGE" and rep.get("path"):
            thumb_url = rep.get("path")
            break

    embeds = []

    # 1. กล่องหัวเรื่อง + รูปปก Thumbnail ขนาดเล็ก
    header_embed = {
        "title": "트릭컬 리바이브",
        "description": f"**{title}**",
        "color": color
    }
    if thumb_url:
        header_embed["thumbnail"] = {"url": thumb_url}
    embeds.append(header_embed)

    # 2. กล่อง Meta Info + ปุ่ม
    meta_desc = f"{date_str}   |   ID: {feed_id}\n🟢 [네이버 라운지 ↗]({post_url})"
    embeds.append({
        "description": meta_desc,
        "color": color
    })

    # 3. แยกท่อนเนื้อหาและรูปภาพ (ไม่มี URL แฝง เพื่อกัน Discord รวมเป็น Grid)
    sections = parse_html_to_sections(raw_contents)

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

        embeds.append(emb)

    MAX_TOTAL_EMBEDS = 25
    if len(embeds) > MAX_TOTAL_EMBEDS:
        embeds = embeds[:MAX_TOTAL_EMBEDS]
        embeds.append({
            "description": "[ 컴포넌트 초과로 자세한 내용은 생략합니다 ]",
            "color": color
        })

    batch_size = 10
    for i in range(0, len(embeds), batch_size):
        batch = embeds[i:i + batch_size]
        payload = {
            "username": "Trickcal Notifier",
            "embeds": batch
        }
        resp = requests.post(WEBHOOK_URL, json=payload)
        print(f"Sent batch {i//batch_size + 1} - Status: {resp.status_code}", flush=True)

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
            print(f"Board {board_id}: Initialized latest ID to {latest_id}", flush=True)
            continue

        new_posts = []
        for feed in feeds:
            f_id = str(feed.get("feedId"))
            if f_id == saved_id:
                break
            new_posts.append(feed)

        if new_posts:
            print(f"Board {board_id}: Found {len(new_posts)} new posts. Sending...", flush=True)
            for post in reversed(new_posts):
                send_to_discord(post, cat)
            last_ids[board_id] = latest_id
            updated = True
        else:
            print(f"Board {board_id}: Up to date (Latest: {latest_id})", flush=True)

    if updated:
        save_last_ids(last_ids)

if __name__ == "__main__":
    run()
