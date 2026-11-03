import os
import json
import requests
import feedparser

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
STORAGE_FILE = "last_youtube_videos.json"

# --- ⚙️ กำหนดช่อง YouTube และห้อง Discord ---
YOUTUBE_CHANNELS = [
    {
        "name": "EPIDGames",
        "feed_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCI37oS0O5OlmQNeiyIywEAQ",
        "discord_channel_id": "ใส่_ID_ห้อง_Discord_ช่องนี้"
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

    for item in YOUTUBE_CHANNELS:
        name = item["name"]
        feed_url = item["feed_url"]
        target_discord_channel_id = item["discord_channel_id"]
        
        feed = feedparser.parse(feed_url)
        if not feed.entries:
            print(f"Warning: No entries found for {name} (URL: {feed_url})", flush=True)
            continue

        latest_entry = feed.entries[0]
        video_id = latest_entry.get("yt_videoid") or latest_entry.get("id")
        video_title = latest_entry.get("title")
        video_link = latest_entry.get("link")
        author_name = latest_entry.get("author", name)

        saved_video_id = last_videos.get(feed_url)

        if video_id != saved_video_id:
            print(f"New video found for {name}: {video_title}", flush=True)
            last_videos[feed_url] = video_id
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
        else:
            print(f"No new video for {name}", flush=True)

    if updated:
        save_last_videos(last_videos)

if __name__ == "__main__":
    run()
