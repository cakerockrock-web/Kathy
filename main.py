import os
import re
import html
import json
import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STORAGE_FILE = "last_ids.json"

CATEGORIES = [
    {
        "board_id": "0",  # หมวดรวมโพสต์สำหรับทดสอบ (เทสเสร็จแล้วค่อยลบออกได้)
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
    if board_id == "0":
        api_url = "https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?limit=5&order=NEW"
    else:
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

    title = target_data.get("title") or "ประกาศใหม่จาก Trickcal"
    if len(title) > 250:
        title = title[:247] + "..."

    raw_contents = target_data.get("contents") or ""
    clean_desc = clean_html_to_markdown(raw_contents)

    if len(clean_desc) > 2000:
        clean_desc = clean_desc[:2000].rstrip() + f"\n\n... *(เนื้อหายาวเกินกำหนด [อ่านฉบับเต็มบนเว็บ]({post_url}))*"

    if not clean_desc:
        clean_desc = f"มีประกาศใหม่ในหมวด **{category['name']}**\n[คลิกเพื่อดูรายละเอียด]({post_url})"

    images = []
    for rep in target_data.get("representations", []):
        if rep.get("representationType") == "IMAGE" and rep.get("path"):
            images.append(rep.get("path"))

    inline_imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', raw_contents, flags=re.IGNORECASE)
    for img in inline_imgs:
        if img.startswith("http") and img not in images:
            images.append(img)

    valid_images = [img for img in images if img.startswith("http")]

    main_embed = {
        "title": f"📢 {title}",
        "url": post_url,
        "description": clean_desc,
        "color": category["color"],
        "footer": {
            "text": f"Naver Lounge • {category['name']}"
        }
    }
    if valid_images:
        main_embed["image"] = {"url": valid_images[0]}

    embeds = [main_embed]

    for extra_img in valid_images[1:4]:
        embeds.append({
            "url": post_url,
            "image": {"url": extra_img}
        })

    payload = {
        "username": "Trickcal Notifier",
        "embeds": embeds
    }

    resp = requests.post(WEBHOOK_URL, json=payload)
    print(f"Sent post {feed_id} to Discord - Status: {resp.status_code}", flush=True)

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
