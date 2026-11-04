import os
import re
import html
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# ดึงค่า Secrets จาก GitHub
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID_MAIN = os.environ.get("DISCORD_CHANNEL_ID")
CHANNEL_ID_COUPON = os.environ.get("DISCORD_CHANNEL_ID_COUPON") or CHANNEL_ID_MAIN
STORAGE_FILE = "last_ids.json"

# บอร์ดที่ต้องการตรวจสอบ (13: ประกาศ, 11: อัปเดต/กิจกรรม, 31: Dev Note, 8: แพตช์)
TARGET_BOARDS = ["13", "11", "31", "8"]

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

def clean_image_url(url):
    if not url: return None
    return url.split("?")[0]

def parse_html_to_sections(raw_html):
    """แยกเนื้อหาข้อความและรูปภาพออกจาก HTML อย่างปลอดภัย"""
    if not raw_html: return []
    
    # ดักจับแท็กรูปภาพ
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
    text = re.sub(r'<\s*/(?:td|th)\s*>', ' | ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', text).strip()

    tokens = re.split(r'\[\[IMG_TOKEN:(https?://[^\]]+)\]\]', text)
    sections = []
    
    for i in range(0, len(tokens), 2):
        chunk_text = tokens[i].strip()
        img = tokens[i+1].strip() if i+1 < len(tokens) else None
        
        # ตัดแบ่งข้อความหากยาวเกิน 1,800 ตัวอักษร เพื่อไม่ให้ Discord Error
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
    """ดึงเนื้อหาโพสต์ฉบับเต็ม พร้อมระบบลองใหม่ 3 ครั้งหากเจอโพสต์ขนาดใหญ่"""
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
    """ดึงรายชื่อโพสต์ล่าสุดจากทุกบอร์ดที่กำหนด"""
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
    
    # ส่งข้อความ พร้อมระบบดักรับมือ Rate Limit 429
    for _ in range(3):
        resp = requests.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201, 204):
            return
        elif resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 2)
            print(f"Rate limited by Discord. Waiting {retry_after}s...", flush=True)
            time.sleep(float(retry_after) + 0.5)
        else:
            print(f"Discord API Error ({resp.status_code}): {resp.text}", flush=True)
            break

def send_lounge_to_discord(feed_summary):
    feed_id = str(feed_summary.get("feedId"))
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    # ดึงรายละเอียดแบบเต็ม
    target_data = fetch_feed_detail(feed_id) or feed_summary
    title = target_data.get("title") or "공지사항"
    raw_contents = target_data.get("contents") or ""
    
    # ตรวจสอบว่าเป็นโพสต์คูปองหรือไม่
    is_coupon = "쿠폰" in title or "COUPON" in title.upper()
    target_channel = CHANNEL_ID_COUPON if is_coupon else CHANNEL_ID_MAIN
    color = 0xF1C40F if is_coupon else 0x2ECC71  # สีเหลืองถ้าเป็นคูปอง, สีเขียวถ้าเป็นประกาศทั่วไป
    
    date_str = format_thai_time(target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("timestamp"))
    thumb_url = clean_image_url(next((rep.get("path") for rep in target_data.get("representations", []) if rep.get("representationType") == "IMAGE" and rep.get("path")), None))

    # 1. กล่องหัวข้อหลัก
    header_embed = {
        "title": "트릭컬 리바이브 (Trickcal RE:VIVE)", 
        "url": post_url,
        "description": f"**{title}**\n{date_str}   |   ID: {feed_id}", 
        "color": color
    }
    if thumb_url: 
        header_embed["thumbnail"] = {"url": thumb_url}

    # 2. แกะข้อความและรูปภาพทั้งหมด
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

    # จำกัดจำนวนบล็อกสูงสุดเพื่อไม่ให้สแปมช่องแชทจนเกินไป (ตัดจบเหมือนตัวอย่าง)
    if len(content_embeds) > 28:
        content_embeds = content_embeds[:28]
        content_embeds.append({
            "description": "[ 컴포넌트 초과로 자세한 내용은 생략합니다 / เนื้อหายาวเกินกำหนด สามารถอ่านฉบับเต็มได้ในลิงก์ Naver ]",
            "color": color
        })

    # รวมชุดข้อความละไม่เกิน 10 Embeds และไม่เกิน 5,000 ตัวอักษร
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

    # วนลูปส่งทีละข้อความ พร้อมหน่วงเวลาเพื่อป้องกัน Rate Limit
    for idx, batch in enumerate(batches):
        payload = {"embeds": batch}
        if idx == 0:
            payload["components"] = components
        send_to_discord_bot(target_channel, payload)
        time.sleep(1.5)  # เว้นช่วง 1.5 วินาทีต่อข้อความ ให้ Discord แสดงผลได้ครบถ้วน

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
        print("Initial run: Saved current history.")
        return

    is_test_mode = "0" in seen_ids
    new_posts = [f for f in unique_feeds if str(f.get("feedId")) not in seen_ids]

    # โหมดทดสอบ จำกัดส่ง 3 โพสต์
    if is_test_mode and new_posts: 
        new_posts = new_posts[:3]
        seen_ids = [x for x in seen_ids if x != "0"]

    if new_posts:
        posts_to_send = new_posts[:3]
        for post in reversed(posts_to_send): 
            send_lounge_to_discord(post)

        for f in unique_feeds:
            fid = str(f.get("feedId"))
            if fid not in seen_ids:
                seen_ids.append(fid)

        save_last_ids(seen_ids[-100:])

if __name__ == "__main__":
    run()
