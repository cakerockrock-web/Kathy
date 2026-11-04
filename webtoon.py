import os
import re
import json
import requests
from datetime import datetime, timezone, timedelta

# รหัสบอท และห้อง Discord สำหรับ Webtoon
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID_WEBTOON = os.environ.get("DISCORD_CHANNEL_ID_WEBTOON") or "1440393996739547310"
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

def clean_image_url(url):
    """ตัด ?type=... ด้านหลังทิ้ง เพื่อให้ได้ไฟล์ภาพต้นฉบับแท้ๆ ช่วยให้ GIF ขยับบนมือถือได้"""
    if not url: return None
    return url.split("?")[0]

def extract_comic_images(raw_html):
    """ดึงเฉพาะรูปภาพการ์ตูนแท้ๆ และตัดรูปการ์ด Twitter/X หรือไอคอนขยะทิ้งทั้งหมด"""
    if not raw_html: return []
    
    # 1. ตัดส่วนที่เป็นกล่องการ์ดลิงก์ Twitter/X ออกจาก HTML ทันที
    cleaned_html = re.sub(r'<div[^>]*class="[^"]*(?:oglink|link_box|banner)[^"]*"[^>]*>.*?</div>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    cleaned_html = re.sub(r'<a[^>]*class="[^"]*oglink[^"]*"[^>]*>.*?</a>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
    
    img_tags = re.findall(r'<img[^>]+>', cleaned_html, flags=re.IGNORECASE)
    images = []
    seen = set()
    
    # คำที่มักเป็นไอคอน โลโก้ หรือภาพพรีวิวลิงก์ที่ไม่ใช่รูปการ์ตูน
    IGNORE_KEYWORDS = [
        "icon", "logo", "favicon", "avatar", "profile", "twimg", 
        "twitter", "x.com", "placeholder", "blank", "static", "badge"
    ]
    
    for tag in img_tags:
        # ข้าม tag ที่มี class หรือ id บ่งบอกว่าเป็น icon หรือ link preview
        if any(k in tag.lower() for k in ["oglink", "icon", "logo", "thumb_link"]):
            continue
            
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if m:
            img_url = m.group(1).strip()
            if img_url.startswith("//"): 
                img_url = "https:" + img_url
                
            if img_url.startswith("http"):
                # ข้ามรูปที่มีคำต้องห้าม
                if any(k in img_url.lower() for k in IGNORE_KEYWORDS):
                    continue
                    
                # ต้องเป็นรูปที่อัปโหลดบนระบบของ Naver (pstatic.net หรือ naver.com) เท่านั้น
                if "pstatic.net" not in img_url and "naver.com" not in img_url:
                    continue
                    
                clean_url = clean_image_url(img_url)
                if clean_url and clean_url not in seen:
                    seen.add(clean_url)
                    images.append(clean_url)
    return images

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

    # 1. การ์ดหัวข้อหลัก
    header_embed = {
        "title": "트릭컬 리바이브 - 웹툰 (Webtoon)", 
        "url": post_url,
        "description": f"**{title}**\n{date_str}   |   ID: {feed_id}", 
        "color": color
    }
    if thumb_url: 
        header_embed["thumbnail"] = {"url": thumb_url}

    # 2. ดึงรูปภาพการ์ตูนแท้ๆ (กรองรูปขยะทิ้งหมดแล้ว)
    images = extract_comic_images(raw_contents)
    image_embeds = []
    
    for img_url in images:
        image_embeds.append({
            "image": {"url": img_url},
            "color": color
        })

    # 3. จัดกลุ่มส่ง
    batches = []
    current_batch = [header_embed]

    for emb in image_embeds:
        if len(current_batch) >= 10:
            batches.append(current_batch)
            current_batch = [emb]
        else:
            current_batch.append(emb)

    if current_batch:
        batches.append(current_batch)

    # ปุ่มกดไปอ่านที่หน้าเว็บต้นฉบับ
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
