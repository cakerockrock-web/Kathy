import os
import re
import html
import json
import requests
from datetime import datetime, timezone, timedelta

# ข้อมูลประจำตัวบอทและห้อง Discord สำหรับ Webtoon
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID_WEBTOON = os.environ.get("DISCORD_CHANNEL_ID_WEBTOON") or "1566795322632704143"
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

def clean_download_links(text):
    if not text:
        return ""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        l_str = line.strip()
        if any(store in l_str for store in ["Google Play", "App Store", "원스토어"]):
            continue
        if "다운로드" in l_str and "바로" in l_str:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def clean_image_url(url):
    """ตัด ?type=... ด้านหลังออกเพื่อให้เป็นนามสกุล .gif แท้ๆ ช่วยให้ GIF เล่นบนมือถือได้"""
    if not url: return None
    return url.split("?")[0]

def parse_html_to_sections(raw_html):
    if not raw_html: return []
    def img_replacer(match):
        tag = match.group(0)
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if m:
            img_url = m.group(1).strip()
            if img_url.startswith("//"): img_url = "https:" + img_url
            if img_url.startswith("http"):
                img_url = clean_image_url(img_url)
                return f"[[IMG_TOKEN:{img_url}]]"
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
        txt = clean_download_links(txt)
        img = tokens[i+1].strip() if i+1 < len(tokens) else None
        if txt or img: sections.append({"text": txt, "image": img})
    return sections

def fetch_feed_detail(feed_id):
    url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed/{feed_id}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200: return res.json().get("content", {}).get("feed")
    except Exception as e:
        print(f"Error fetching detail {feed_id}: {e}", flush=True)
    return None

def fetch_lounge_feeds():
    api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={TARGET_BOARD_ID}&buffFilteringYN=N&limit=15&offset=0&order=NEW"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/{TARGET_BOARD_ID}"}
    try:
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code == 200:
            content = res.json().get("content", {})
            return (content.get("noticeFeeds") or []) + (content.get("feeds") or [])
    except Exception as e:
        print(f"Error fetching feeds: {e}", flush=True)
    return []

def send_to_discord_bot(payload):
    if not CHANNEL_ID_WEBTOON:
        print("Error: Target channel ID is empty!", flush=True)
        return
        
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID_WEBTOON}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code not in (200, 204):
        print(f"Discord API Error ({resp.status_code}): {resp.text}", flush=True)

def send_webtoon_to_discord(feed_summary):
    feed_id = str(feed_summary.get("feedId"))
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    target_data = fetch_feed_detail(feed_id) or feed_summary
    title = target_data.get("title") or "웹툰"
    raw_contents = target_data.get("contents") or ""
    color = 0x2ECC71  # กรอบสีเขียว Webtoon
    
    date_str = format_thai_time(target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("timestamp"))
    thumb_url = clean_image_url(next((rep.get("path") for rep in target_data.get("representations", []) if rep.get("representationType") == "IMAGE" and rep.get("path")), None))

    # 1. การ์ดหัวข้อและปุ่มเปิดดูต้นฉบับ
    header_embed = {
        "title": "트릭컬 리바이브 - 웹툰 (Webtoon)", 
        "url": post_url,
        "description": f"**{title}**\n{date_str}   |   ID: {feed_id}", 
        "color": color
    }
    if thumb_url: 
        header_embed["thumbnail"] = {"url": thumb_url}

    # 2. แยกข้อความและจับคู่รูปภาพทีละ 2 รูป
    sections = parse_html_to_sections(raw_contents)
    content_embeds = []
    
    all_images = []
    for sec in sections:
        sec_text = sec["text"][:1900].rstrip() + "..." if len(sec["text"]) > 1900 else sec["text"]
        if sec_text:
            content_embeds.append({
                "description": sec_text,
                "color": color
            })
        if sec.get("image"):
            all_images.append(sec["image"])

    # วนลูปจับคู่รูปภาพทีละ 2 รูป (Pair Grid)
    pair_index = 0
    for i in range(0, len(all_images), 2):
        pair = all_images[i:i+2]
        pair_url = f"{post_url}#gallery-{pair_index}"
        pair_index += 1

        for img_url in pair:
            content_embeds.append({
                "image": {"url": img_url},
                "color": color,
                "url": pair_url
            })

    if len(content_embeds) > 24:
        content_embeds = content_embeds[:24]
        content_embeds.append({"description": "[ เนื้อหายาวเกินไป สามารถอ่านต่อได้ในลิงก์หลัก ]", "color": color})

    # 3. รวมหัวข้อกับเนื้อหาเข้าด้วยกันเป็นก้อนเดียว
    batches = []
    current_batch = [header_embed]
    current_char_count = len(header_embed.get("title", "")) + len(header_embed.get("description", ""))

    for emb in content_embeds:
        desc_len = len(emb.get("description") or "")
        if len(current_batch) >= 10 or (current_char_count + desc_len > 5000 and current_batch):
            batches.append(current_batch)
            current_batch = [emb]
            current_char_count = desc_len
        else:
            current_batch.append(emb)
            current_char_count += desc_len

    if current_batch:
        batches.append(current_batch)

    components = [{
        "type": 1,
        "components": [{
            "type": 2, "style": 5, "label": " อ่านในเว็บ Naver", "url": post_url, "emoji": {"name": "🟢"}
        }]
    }]

    for idx, batch in enumerate(batches):
        payload = {"embeds": batch}
        if idx == 0:
            payload["components"] = components
        send_to_discord_bot(payload)

def run():
    if not BOT_TOKEN:
        print("Missing BOT_TOKEN", flush=True)
        return

    seen_ids = load_last_ids()
    feeds = fetch_lounge_feeds()
    if not feeds:
        return

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
        posts_to_send = new_posts[:3]
        for post in reversed(posts_to_send): 
            send_webtoon_to_discord(post)

        for f in unique_feeds:
            fid = str(f.get("feedId"))
            if fid not in seen_ids:
                seen_ids.append(fid)

        save_last_ids(seen_ids[-50:])

if __name__ == "__main__":
    run()
