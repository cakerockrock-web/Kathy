import os
import json
import requests
import feedparser

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
STORAGE_FILE = "last_youtube_videos.json"

# --- ⚙️ กำหนดช่อง YouTube และแยกห้อง Discord ของใครของมันตรงนี้ ---
YOUTUBE_CHANNELS = [
    {
        "name": "ช่องที่ 1",
        "feed_url": "https://www.youtube.com/@aljazeeraenglish",
        "discord_channel_id": "1566895972859121885"
    },
    {
        "name": "ช่องที่ 2",
        "feed_url": "https://www.youtube.com/@Patima_KR",
        "discord_channel_id": "1566904623304810547"
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
        return
    url = f"https://discord.com/api/v10/channels/{target_channel}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    requests.post(url, headers=headers, json=payload)

def run():
    if not BOT_TOKEN:
        print("Missing BOT_TOKEN", flush=True)
        return

    last_videos = load_last_videos()
    updated = False

    for item in YOUTUBE_CHANNELS:
        feed_url = item["feed_url"]
        target_discord_channel_id = item["discord_channel_id"]
        
        feed = feedparser.parse(feed_url)
        if not feed.entries:
            continue

        latest_entry = feed.entries[0]
        video_id = latest_entry.get("yt_videoid") or latest_entry.get("id")
        video_title = latest_entry.get("title")
        video_link = latest_entry.get("link")
        author_name = latest_entry.get("author", "YouTube Channel")

        saved_video_id = last_videos.get(feed_url)

        if video_id != saved_video_id:
            last_videos[feed_url] = video_id
            updated = True

            if not saved_video_id:
                continue

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
            
            # ส่งไปยังห้อง Discord เฉพาะของช่องนั้นๆ
            send_to_discord(payload, target_discord_channel_id)

    if updated:
        save_last_videos(last_videos)

if __name__ == "__main__":
    run()
