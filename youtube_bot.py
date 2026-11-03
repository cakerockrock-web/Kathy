import os
import re
import json
import time
import requests

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
STORAGE_FILE = "last_youtube_videos.json"

# --- ⚙️ กำหนดช่อง YouTube และห้อง Discord ---
# หากต้องการแท็กยศ ให้ใส่ ID ยศใน "role_id": "ตัวเลขยศ" (ถ้าไม่แท็กให้ปล่อยเป็น None)
YOUTUBE_CHANNELS = [
    {
        "name": "EPID Games",
        "channel_url": "https://www.youtube.com/@epidgames6350/videos",
        "discord_channel_id": "1566895972859121885",
        "role_id": None  # ตัวอย่างถ้ามียศ: "123456789012345678"
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

def send_to_discord(content_text, target_channel):
    if not target_channel:
        print("No target channel ID provided", flush=True)
        return
    url = f"https://discord.com/api/v10/channels/{target_channel}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "content": content_text
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Sent to Discord: Status Code {response.status_code}", flush=True)

def fetch_latest_videos(channel_url, headers):
    try:
        res = requests.get(channel_url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"Failed to fetch page. Status: {res.status_code}", flush=True)
            return []

        # สกัด ID คลิปเฉพาะจากวิดีโอที่เป็นทางการ
        video_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', res.text)
        
        seen = set()
        ordered_ids = []
        for vid in video_ids:
            if vid not in seen:
                seen.add(vid)
                ordered_ids.append(vid)

        videos = []
        for v_id in ordered_ids[:10]:
            videos.append({
                "id": v_id,
                "link": f"https://youtu.be/{v_id}"
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
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    for item in YOUTUBE_CHANNELS:
        name = item["name"]
        channel_url = item["channel_url"]
        target_discord_channel_id = item["discord_channel_id"]
        role_id = item.get("role_id")

        videos = fetch_latest_videos(channel_url, headers)
        print(f"[{name}] Found {len(videos)} videos on page", flush=True)

        if not videos:
            print(f"Warning: No videos parsed for {name}", flush=True)
            continue

        seen_ids = last_videos.get(name, [])
        if isinstance(seen_ids, str):
            seen_ids = [seen_ids]

        # เลือก 5 คลิปแรก แล้วตรวจส่ง
        recent_videos = videos[:5]

        for video in reversed(recent_videos):
            video_id = video["id"]
            video_link = video["link"]

            if video_id not in seen_ids:
                print(f"Sending video for {name}: {video_id}", flush=True)
                seen_ids.append(video_id)
                updated = True

                # จัดข้อความแบบรูปทางซ้าย: แท็กยศ/ชื่อช่อง แล้วตามด้วยบรรทัดลิงก์
                if role_id:
                    mention = f"<@&{role_id}> **{name}**"
                else:
                    mention = f"**{name}**"

                message_text = f"{mention}\n{video_link}"

                send_to_discord(message_text, target_discord_channel_id)
                time.sleep(1)

        last_videos[name] = seen_ids

    if updated:
        save_last_videos(last_videos)

if __name__ == "__main__":
    run()
