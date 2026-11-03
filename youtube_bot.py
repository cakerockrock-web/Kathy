import os
import json
import time
import requests
import feedparser

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
STORAGE_FILE = "last_youtube_videos.json"

# --- ⚙️ กำหนดช่อง YouTube และห้อง Discord ---
YOUTUBE_CHANNELS = [
    {
        "name": "EPIDGames",
        "feed_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCI37oS0O5OlmQNeiyIywEAQ",
        "discord_channel_id": "1566895972859121885"
    }
]

def load_last_videos():
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_last_videos(data):
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_to_discord(payload, target_channel):
    if not target_channel:
        print("No target channel ID provided", flush=True)
        return
    url = f"https://discord.com/api/v10/channels/{target_channel}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Sent to Discord: Status Code {response.status_code}", flush=True)

def run():
    if not BOT_TOKEN:
        print("Error: Missing DISCORD_BOT_TOKEN in Secrets", flush=True)
        return

    last_videos = load_last_videos()
    updated = False

    # กำหนด User-Agent ให้เสมือนการเปิดผ่านเว็บบราวเซอร์ปกติ
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    for item in YOUTUBE_CHANNELS:
        name = item["name"]
        feed_url = item["feed_url"]
        target_discord_channel_id = item["discord_channel_id"]

        try:
            res = requests.get(feed_url, headers=headers, timeout=15)
            print(f"[{name}] Fetch Status: {res.status_code}, Length: {len(res.content)} bytes", flush=True)
            feed = feedparser.parse(res.content)
        except Exception as e:
            print(f"Error fetching feed for {name}: {e}", flush=True)
            continue

        print(f"[{name}] Found entries: {len(feed.entries)}", flush=True)

        if not feed.entries:
            print(f"Warning: No entries found for {name} (URL: {feed_url})", flush=True)
            continue

        seen_ids = last_videos.get(feed_url, [])
        if isinstance(seen_ids, str):
            seen_ids = [seen_ids]

        # ตรวจสอบและส่งคลิปที่ยังไม่มีในประวัติ (วนจากคลิปเก่าไปหาคลิปใหม่)
        for entry in reversed(feed.entries):
            video_id = entry.get("yt_videoid") or entry.get("id")
            video_title = entry.get("title")
            video_link = entry.get("link")
            author_name = entry.get("author", name)

            if video_id not in seen_ids:
                print(f"Sending video for {name}: {video_title}", flush=True)
                seen_ids.append(video_id)
                updated = True

                embed = {
                    "title": f"🎬 มีคลิปใหม่จาก {author_name}!",
                    "description": f"**{video_title}**",
                    "color": 0xFF0000,
                    "fields": [
                        {"name": "รับชมคลิปได้ที่นี่", "value": video_link, "inline": False}
                    ],
                    "footer": {"text": "YouTube Notifier 🍬"}
                }

                payload = {
                    "embeds": [embed],
                    "components": [{
                        "type": 1,
                        "components": [{
                            "type": 2,
                            "style": 5,
                            "label": " ไปที่ YouTube",
                            "url": video_link,
                            "emoji": {"name": "▶️"}
                        }]
                    }]
                }

                send_to_discord(payload, target_discord_channel_id)
                time.sleep(1)

        last_videos[feed_url] = seen_ids

    if updated:
        save_last_videos(last_videos)

if __name__ == "__main__":
    run()
