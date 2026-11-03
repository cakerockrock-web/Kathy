import os
import re
import json
import time
import requests

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
STORAGE_FILE = "last_youtube_videos.json"

# --- ⚙️ กำหนดช่อง YouTube และห้อง Discord ---
YOUTUBE_CHANNELS = [
    {
        "name": "EPIDGames",
        "channel_url": "https://www.youtube.com/@epidgames6350/videos",
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

def fetch_latest_videos(channel_url, headers):
    try:
        res = requests.get(channel_url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"Failed to fetch page. Status: {res.status_code}", flush=True)
            return []

        # สกัด videoId และ title จากข้อมูล JSON ภายในหน้าเว็บ YouTube
        matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}\]', res.text)
        
        videos = []
        seen = set()
        for v_id, title in matches:
            if v_id not in seen:
                seen.add(v_id)
                videos.append({
                    "id": v_id,
                    "title": title.encode().decode('unicode-escape', 'ignore'),
                    "link": f"https://www.youtube.com/watch?v={v_id}"
                })
        return videos
    except Exception as e:
        print(f"Error fetching videos: {e}", flush=True)
        return []

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
        channel_url = item["channel_url"]
        target_discord_channel_id = item["discord_channel_id"]

        videos = fetch_latest_videos(channel_url, headers)
        print(f"[{name}] Found {len(videos)} videos on page", flush=True)

        if not videos:
            print(f"Warning: No videos parsed for {name}", flush=True)
            continue

        seen_ids = last_videos.get(name, [])
        if isinstance(seen_ids, str):
            seen_ids = [seen_ids]

        # เลือกดึง 10 คลิปแรกสุด แล้ววนส่งจากคลิปเก่าไปหาคลิปใหม่
        recent_videos = videos[:10]

        for video in reversed(recent_videos):
            video_id = video["id"]
            video_title = video["title"]
            video_link = video["link"]

            if video_id not in seen_ids:
                print(f"Sending video for {name}: {video_title}", flush=True)
                seen_ids.append(video_id)
                updated = True

                embed = {
                    "title": f"🎬 มีคลิปใหม่จาก {name}!",
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

        last_videos[name] = seen_ids

    if updated:
        save_last_videos(last_videos)

if __name__ == "__main__":
    run()
