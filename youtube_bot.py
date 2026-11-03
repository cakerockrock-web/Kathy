import os
import re
import json
import time
import requests
import feedparser

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
STORAGE_FILE = "last_youtube_videos.json"

# --- ⚙️ กำหนดช่อง YouTube (ใส่ลิงก์หน้าช่องแบบมี @ ได้เลย) และห้อง Discord ---
YOUTUBE_CHANNELS = [
    {
        "name": "EPIDGames",
        "url": "https://www.youtube.com/@epidgames6350",
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

def get_channel_id_from_url(channel_url, headers):
    # ถ้าเป็น feed_url อยู่แล้ว หรือมี channel_id ส่งมา ให้ดึงออกมาตรงๆ
    if "channel_id=" in channel_url:
        return channel_url.split("channel_id=")[-1].split("&")[0]
    
    # กรณีเป็นลิงก์หน้าช่อง เช่น https://www.youtube.com/@epidgames6350
    try:
        res = requests.get(channel_url, headers=headers, timeout=15)
        match = re.search(r'itemprop="channelId"\s+content="(UC[\w-]+)"', res.text)
        if not match:
            match = re.search(r'"channelId":"(UC[\w-]+)"', res.text)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Error resolving channel ID: {e}", flush=True)
    return None

def run():
    if not BOT_TOKEN:
        print("Error: Missing DISCORD_BOT_TOKEN in Secrets", flush=True)
        return

    last_videos = load_last_videos()
    updated = False

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    for item in YOUTUBE_CHANNELS:
        name = item["name"]
        raw_url = item["url"]
        target_discord_channel_id = item["discord_channel_id"]

        # ดึง Channel ID จริงจากหน้าช่อง
        channel_id = get_channel_id_from_url(raw_url, headers)
        if not channel_id:
            print(f"[{name}] Failed to get Channel ID from {raw_url}", flush=True)
            continue

        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        print(f"[{name}] Resolved Channel ID: {channel_id}", flush=True)

        try:
            res = requests.get(feed_url, headers=headers, timeout=15)
            print(f"[{name}] Fetch Status: {res.status_code}", flush=True)
            feed = feedparser.parse(res.content)
        except Exception as e:
            print(f"Error fetching feed for {name}: {e}", flush=True)
            continue

        print(f"[{name}] Found entries: {len(feed.entries)}", flush=True)

        if not feed.entries:
            print(f"Warning: No entries found for {name}", flush=True)
            continue

        seen_ids = last_videos.get(channel_id, [])
        if isinstance(seen_ids, str):
            seen_ids = [seen_ids]

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

        last_videos[channel_id] = seen_ids

    if updated:
        save_last_videos(last_videos)

if __name__ == "__main__":
    run()
