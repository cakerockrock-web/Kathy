import os
import re
import io
import json
import requests
from PIL import Image, ImageSequence
from datetime import datetime, timezone, timedelta

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

def clean_image_url(url):
    if not url: return None
    return url.split("?")[0]

def extract_comic_images(raw_html):
    if not raw_html: return []
    cleaned_html = re.sub(r'<div[^>]*class="[^"]*(?:oglink|link_box|banner)[^"]*"[^>]*>.*?</div>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    cleaned_html = re.sub(r'<a[^>]*class="[^"]*oglink[^"]*"[^>]*>.*?</a>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
    
    img_tags = re.findall(r'<img[^>]+>', cleaned_html, flags=re.IGNORECASE)
    images = []
    seen = set()
    IGNORE_KEYWORDS = ["icon", "logo", "favicon", "avatar", "profile", "twimg", "twitter", "x.com", "placeholder", "blank", "static", "badge"]
    
    for tag in img_tags:
        if any(k in tag.lower() for k in ["oglink", "icon", "logo", "thumb_link"]):
            continue
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if m:
            img_url = m.group(1).strip()
            if img_url.startswith("//"): img_url = "https:" + img_url
            if img_url.startswith("http"):
                if any(k in img_url.lower() for k in IGNORE_KEYWORDS): continue
                if "pstatic.net" not in img_url and "naver.com" not in img_url: continue
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

def merge_two_images(url1, url2):
    """ฟังก์ชันดาวน์โหลดรูป 2 รูปมาประกบซ้าย-ขวาเป็นรูปเดียว (รองรับไฟล์ GIF เคลื่อนไหว)"""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r1 = requests.get(url1, headers=headers, timeout=10)
        r2 = requests.get(url2, headers=headers, timeout=10)
        im1 = Image.open(io.BytesIO(r1.content))
        im2 = Image.open(io.BytesIO(r2.content))

        # ตรวจสอบว่าเป็นภาพขยับ (Animated GIF) หรือไม่
        is_animated = getattr(im1, "is_animated", False) or getattr(im2, "is_animated", False)

        if not is_animated:
            # รวมภาพนิ่งทั่วไป
            target_h = min(im1.height, im2.height)
            im1_w = int(im1.width * (target_h / im1.height))
            im2_w = int(im2.width * (target_h / im2.height))
            im1_resized = im1.resize((im1_w, target_h), Image.Resampling.LANCZOS)
            im2_resized = im2.resize((im2_w, target_h), Image.Resampling.LANCZOS)

            merged = Image.new("RGBA", (im1_w + im2_w, target_h))
            merged.paste(im1_resized, (0, 0))
            merged.paste(im2_resized, (im1_w, 0))

            output = io.BytesIO()
            merged.save(output, format="PNG")
            output.seek(0)
            return output.getvalue(), "merged.png"
        else:
            # รวมภาพ GIF เคลื่อนไหวทีละเฟรม
            frames1 = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(im1)]
            frames2 = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(im2)]
            max_frames = max(len(frames1), len(frames2))
            
            target_h = min(im1.height, im2.height)
            w1 = int(im1.width * (target_h / im1.height))
            w2 = int(im2.width * (target_h / im2.height))

            merged_frames = []
            durations = []
            for idx in range(max_frames):
                f1 = frames1[idx % len(frames1)].resize((w1, target_h), Image.Resampling.LANCZOS)
                f2 = frames2[idx % len(frames2)].resize((w2, target_h), Image.Resampling.LANCZOS)
                new_frame = Image.new("RGBA", (w1 + w2, target_h))
                new_frame.paste(f1, (0, 0))
                new_frame.paste(f2, (w1, 0))
                merged_frames.append(new_frame)
                durations.append(im1.info.get("duration", 100))

            output = io.BytesIO()
            merged_frames[0].save(
                output, format="GIF", save_all=True, append_images=merged_frames[1:],
                duration=durations, loop=0, disposal=2
            )
            output.seek(0)
            return output.getvalue(), "merged.gif"
    except Exception as e:
        print(f"Error merging images: {e}", flush=True)
        return None, None

def send_to_discord_with_file(payload_json, file_bytes=None, filename=None):
    if not CHANNEL_ID_WEBTOON: return
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID_WEBTOON}/messages"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    
    if file_bytes and filename:
        files = {
            "payload_json": (None, json.dumps(payload_json), "application/json"),
            "files[0]": (filename, file_bytes, "image/gif" if filename.endswith(".gif") else "image/png")
        }
        requests.post(url, headers=headers, files=files)
    else:
        headers["Content-Type"] = "application/json"
        requests.post(url, headers=headers, json=payload_json)

def send_webtoon_to_discord(feed_summary):
    feed_id = str(feed_summary.get("feedId"))
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    target_data = fetch_feed_detail(feed_id) or feed_summary
    title = target_data.get("title") or "웹툰"
    raw_contents = target_data.get("contents") or ""
    color = 0x2ECC71
    
    date_str = format_thai_time(target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("timestamp"))
    thumb_url = clean_image_url(next((rep.get("path") for rep in target_data.get("representations", []) if rep.get("representationType") == "IMAGE" and rep.get("path")), None))

    # 1. การ์ดหัวข้อหลัก
    header_embed = {
        "title": "트릭컬 리바이브 - 웹툰 (Webtoon)", 
        "url": post_url,
        "description": f"**{title}**\n{date_str}   |   ID: {feed_id}", 
        "color": color
    }
    if thumb_url: header_embed["thumbnail"] = {"url": thumb_url}

    components = [{
        "type": 1,
        "components": [{
            "type": 2, "style": 5, "label": " อ่านในเว็บ Naver", "url": post_url, "emoji": {"name": "🟢"}
        }]
    }]

    # 2. จัดการรูปภาพการ์ตูน: นำภาพที่อยู่ติดกันมาประกบคู่ทีละ 2 รูป
    images = extract_comic_images(raw_contents)
    
    # ส่งข้อความแรก (หัวเรื่อง + ปุ่ม)
    send_to_discord_with_file({"embeds": [header_embed], "components": components})

    # วนลูปส่งรูปภาพ (ประกบคู่ทีละ 2 รูป)
    i = 0
    while i < len(images):
        if i + 1 < len(images):
            # มีรูปคู่ -> ประกบซ้าย-ขวาเป็นรูปเดียว
            file_bytes, filename = merge_two_images(images[i], images[i+1])
            if file_bytes:
                emb = {"color": color, "image": {"url": f"attachment://{filename}"}}
                send_to_discord_with_file({"embeds": [emb]}, file_bytes, filename)
            i += 2
        else:
            # เศษ 1 รูปสุดท้าย -> ส่งเดี่ยว
            emb = {"color": color, "image": {"url": images[i]}}
            send_to_discord_with_file({"embeds": [emb]})
            i += 1

def run():
    if not BOT_TOKEN: return
    seen_ids = load_last_ids()
    feeds = fetch_lounge_feeds()
    if not feeds: return

    unique_feeds = []
    temp_seen = set()
    for f in feeds:
        fid = str(f.get("feedId"))
        if fid not in temp_seen:
            temp_seen.add(fid)
            unique_feeds.append(f)

    if not seen_ids:
        save_last_ids([str(f.get("feedId")) for f in unique_feeds])
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
