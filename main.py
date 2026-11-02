import os
import json
import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STORAGE_FILE = "last_ids.json"

# กำหนดหมวดหมู่บน Naver Lounge ของ Trickcal
CATEGORIES = [
    {
        "board_id": "0",  # ใส่ 0 เพื่อทดสอบดึงฟีดรวมทั้งหมด
        "name": "🔥 ทดสอบ: รวมทุกโพสต์ (All Feeds)",
        "color": 0xE74C3C
    },
    {
        "board_id": "3",  # กระดานประกาศหลัก (Notice / Update)
        "name": "🛠️ ประกาศทางการ / อัปเดต",
        "color": 0x3498DB
    },
    {
        "board_id": "4",  # กิจกรรม / คูปอง
        "name": "🎟️ คูปอง / กิจกรรม",
        "color": 0xF1C40F
    },
    {
        "board_id": "7",  # สารจากผู้พัฒนา (Dev Note)
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

def fetch_lounge_feeds(board_id):
    if board_id == "0":
        api_url = "https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?limit=5&order=NEW"
    else:
        api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={board_id}&limit=5&order=NEW"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://game.naver.com/lounge/Trickcal/board"
    }

    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"Board {board_id}: HTTP Error {res.status_code}", flush=True)
            return []
        data = res.json()
        return data.get("content", {}).get("feeds", [])
    except Exception as e:
        print(f"Board {board_id} Error: {e}", flush=True)
        return []

def send_to_discord(feed, category):
    feed_id = feed.get("feedId")
    title = feed.get("title") or "ประกาศใหม่จาก Trickcal"
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    # ดึงรูปภาพหน้าปก (ถ้ามี)
    image_url = None
    representations = feed.get("representations", [])
    for rep in representations:
        if rep.get("representationType") == "IMAGE":
            image_url = rep.get("path")
            break

    embed = {
        "title": title,
        "url": post_url,
        "description": f"มีประกาศใหม่ในหมวด **{category['name']}**",
        "color": category["color"],
        "footer": {
            "text": "Naver Lounge • Trickcal Re:vive"
        }
    }
    if image_url:
        embed["image"] = {"url": image_url}

    payload = {
        "username": "Trickcal Lounge Notifier",
        "embeds": [embed]
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
            print(f"Board {board_id}: No feeds returned", flush=True)
            continue

        saved_id = str(last_ids.get(board_id, ""))
        latest_id = str(feeds[0].get("feedId"))

        # รันรอบแรกเพื่อบันทึก ID ล่าสุด
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
