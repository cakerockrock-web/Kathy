import os
import re
import html
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# รหัสและค่าตั้งค่าช่อง Discord
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID_MAIN = os.environ.get("DISCORD_CHANNEL_ID")
CHANNEL_ID_COUPON = os.environ.get("DISCORD_CHANNEL_ID_COUPON") or CHANNEL_ID_MAIN
STORAGE_FILE = "last_ids.json"

TARGET_BOARDS = ["13", "11", "31", "8"]

def load_last_ids():
    """โหลดประวัติโพสต์ และบังคับแปลงทุก ID ให้เป็น str ทั้งหมด"""
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            return []
    return []

def save_last_ids(data):
    """บันทึกประวัติโพสต์โดยตัดค่าซ้ำและเก็บเป็น str เสมอ"""
    clean_data = list(dict.fromkeys([str(x).strip() for x in data if str(x).strip()]))
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, ensure_ascii=False, indent=2)

def format_thai_time(timestamp_val):
    kst = timezone(timedelta(hours=9))
    if timestamp_val and (isinstance(timestamp_val, (int, float)) or (isinstance(timestamp_val, str) and timestamp_val.isdigit())):
        dt = datetime.fromtimestamp(int(timestamp_val) / 1000, tz=kst)
    else:
        dt = datetime.now(tz=kst)
    thai_months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"{dt.day} {thai_months[dt.month-1]} {dt.year} {dt.hour:02d}:{dt.minute:02d} น."

def clean_image_url(url):
    if not url: return None
    return url.split("?")[0]

def clean_unwanted_text(text):
    """ตัดลิงก์ดาวน์โหลดและลิงก์ร้านค้าที่ไม่จำเป็นท้ายโพสต์ทิ้ง"""
    if not text: return ""
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

def format_table_to_text(table_html):
    """แปลงตาราง HTML ให้เป็นบรรทัดข้อความกระชับ อ่านง่าย ไม่แตกแถว"""
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, flags=re.DOTALL | re.IGNORECASE)
    formatted_rows = []
    for r in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, flags=re.DOTALL | re.IGNORECASE)
        clean_cells = []
        for c in cells:
            c_text = re.sub(r'<[^>]+>', ' ', c)
            c_text = html.unescape(c_text).strip()
            c_text = re.sub(r'\s+', ' ', c_text)
            if c_text:
                clean_cells.append(c_text)
        if clean_cells:
            # รวมคอลัมน์ในแถวเดียวกันด้วยเครื่องหมาย : หรือ -
            if len(clean_cells) == 2:
                formatted_rows.append(f"• {clean_cells[0]}: {clean_cells[1]}")
            else:
                formatted_rows.append(" - " + " | ".join(clean_cells))
    return "\n" + "\n".join(formatted_rows) + "\n"

def parse_html_to_sections(raw_html):
    """แยกเนื้อหาข้อความและรูปภาพ จัดการตาราง และเว้นวรรคให้พอดี"""
    if not raw_html: return []
    
    # 1. จัดการแปลงตาราง HTML ให้เรียบร้อยก่อน
    raw_html = re.sub(r'<table[^>]*>(.*?)</table>', lambda m: format_table_to_text(m.group(0)), raw_html, flags=re.DOTALL | re.IGNORECASE)

    # 2. แปลงรูปภาพเป็นโทเคน
    def img_replacer(match):
        tag = match.group(0)
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if m:
            img_url = m.group(1).strip()
            if img_url.startswith("//"): img_url = "https:" + img_url
            if img_url.startswith("http"):
                clean_url = clean_image_url(img_url)
                return f"\n[[IMG_TOKEN:{clean_url}]]\n"
        return ""

    text = re.sub(r'<img[^>]+>', img_replacer, raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<\s*br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:p|div|h[1-6]|tr|li|ul|ol)\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', text).strip()

    tokens = re.split(r'\[\[IMG_TOKEN:(https?://[^\]]+)\]\]', text)
    sections = []
    
    for i in range(0, len(tokens), 2):
        chunk_text = clean_unwanted_text(tokens[i].strip())
        img = tokens[i+1].strip() if i+1 < len(tokens) else None
        
        # ตัดแบ่งข้อความหากยาวเกิน 1,800 ตัวอักษร
        if chunk_text:
            while len(chunk_text) > 1800:
                cut_idx = chunk_text.rfind('\n', 0, 1800)
                if cut_idx == -1: cut_idx = 1800
                sections.append({"text": chunk_text[:cut_idx].strip(), "image": None})
                chunk_text = chunk_text[cut_idx:].strip()
            if chunk_text:
                sections.append({"text": chunk_text, "image": None})
                
        if img:
            sections.append({"text": "", "image": img})

    return sections

def fetch_feed_detail(feed_id):
    url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed/{feed_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    }
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=25)
            if res.status_code == 200:
                feed = res.json().get("content", {}).get("feed")
                if feed and feed.get("contents"):
                    return feed
        except Exception as e:
            print(f"Attempt {attempt+1} fetching detail {feed_id} failed: {e}", flush=True)
            time.sleep(2)
    return None

def fetch_lounge_feeds():
    all_feeds = []
    for b_id in TARGET_BOARDS:
        api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={b_id}&buffFilteringYN=N&limit=10&offset=0&order=NEW"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": f"https://game.naver.com/lounge/Trickcal/board/{b_id}"
        }
        try:
            res = requests.get(api_url, headers=headers, timeout=15)
            if res.status_code == 200:
                content = res.json().get("content", {})
                feeds = (content.get("noticeFeeds") or []) + (content.get("feeds") or [])
                all_feeds.extend(feeds)
        except Exception as e:
            print(f"Error fetching board {b_id}: {e}", flush=True)
    return all_feeds

def send_to_discord_bot(channel_id, payload):
    if not channel_id: return
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    for _ in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code in (200, 201, 204):
                return
            elif resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 2)
                time.sleep(float(retry_after) + 0.5)
            else:
                break
        except Exception:
            time.sleep(2)

def send_lounge_to_discord(feed_summary):
    feed_id = str(feed_summary.get("feedId")).strip()
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    target_data = fetch_feed_detail(feed_id) or feed_summary
    title = target_data.get("title") or "공지사항"
    raw_contents = target_data.get("contents") or ""
    
    is_coupon = "쿠폰" in title or "COUPON" in title.upper()
    target_channel = CHANNEL_ID_COUPON if is_coupon else CHANNEL_ID_MAIN
    color = 0xF1C40F if is_coupon else 0x2ECC71
    
    date_str = format_thai_time(target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("timestamp"))
    thumb_url = clean_image_url(next((rep.get("path") for rep in target_data.get("representations", []) if rep.get("representationType") == "IMAGE" and rep.get("path")), None))

    header_embed = {
        "title": "트릭컬 리바이브 (Trickcal RE:VIVE)", 
        "url": post_url,
        "description": f"**{title}**\n{date_str}   |   ID: {feed_id}", 
        "color": color
    }
    if thumb_url: 
        header_embed["thumbnail"] = {"url": thumb_url}

    sections = parse_html_to_sections(raw_contents)
    content_embeds = []
    
    for sec in sections:
        emb = {"color": color}
        if sec["text"]:
            emb["description"] = sec["text"]
        if sec["image"]:
            emb["image"] = {"url": sec["image"]}
        if emb.get("description") or emb.get("image"):
            content_embeds.append(emb)

    if len(content_embeds) > 28:
        content_embeds = content_embeds[:28]
        content_embeds.append({
            "description": "[ 컴포넌트 초과로 자세한 내용은 생략합니다 / เนื้อหายาวเกินกำหนด สามารถอ่านฉบับเต็มได้ในลิงก์ Naver ]",
            "color": color
        })

    # รวมกลุ่มข้อความ
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

    # ปุ่มลิงก์ต้นฉบับ
    components = [{
        "type": 1,
        "components": [{
            "type": 2, "style": 5, "label": " 네이버 라운지 (Naver Lounge)", "url": post_url, "emoji": {"name": "🟢"}
        }]
    }]

    # ส่งข้อความแรกพร้อมปุ่ม (ปุ่มจะอยู่ใต้การ์ดหัวเรื่องเสมอ ไม่ไปคั่นกลางเนื้อหา)
    for idx, batch in enumerate(batches):
        payload = {"embeds": batch}
        if idx == 0:
            payload["components"] = components
        send_to_discord_bot(target_channel, payload)
        time.sleep(1.5)

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
        fid = str(f.get("feedId")).strip()
        if fid not in temp_seen:
            temp_seen.add(fid)
            unique_feeds.append(f)

    if not seen_ids:
        all_current = [str(f.get("feedId")).strip() for f in unique_feeds]
        save_last_ids(all_current)
        print("Initial run: Saved current history.")
        return

    is_test_mode = "0" in seen_ids
    seen_ids = [x for x in seen_ids if x != "0"]
    new_posts = [f for f in unique_feeds if str(f.get("feedId")).strip() not in seen_ids]

    if is_test_mode and new_posts: 
        new_posts = new_posts[:3]

    if new_posts:
        posts_to_send = new_posts[:3]
        for post in reversed(posts_to_send): 
            fid = str(post.get("feedId")).strip()
            try:
                send_lounge_to_discord(post)
                print(f"Sent post {fid} successfully.", flush=True)
            except Exception as e:
                print(f"Error sending post {fid}: {e}", flush=True)
            
            if fid not in seen_ids:
                seen_ids.append(fid)
            save_last_ids(seen_ids[-100:])

        for f in unique_feeds:
            fid = str(f.get("feedId")).strip()
            if fid not in seen_ids:
                seen_ids.append(fid)
        save_last_ids(seen_ids[-100:])
    else:
        print("No new posts found.")

if __name__ == "__main__":
    run()
