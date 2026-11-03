import os
import re
import json
import time
import requests

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
STORAGE_FILE = "last_youtube_videos.json"

# ==========================================
# ⚙️ กำหนดช่อง YouTube และห้อง Discord ทั้ง 3 ช่อง
# ==========================================
YOUTUBE_CHANNELS = [
    # --- ช่องที่ 1: EPID Games (คลิปปกติ) ---
    {
        "name": "EPID Games",
        "channel_url": "https://www.youtube.com/@epidgames6350/videos",
        "discord_channel_id": "1566895972859121885",
        "role_id": None
    },
    # --- ช่องที่ 1: EPID Games (คลิป Shorts) ---
    {
        "name": "EPID Games (Shorts)",
        "channel_url": "https://www.youtube.com/@epidgames6350/shorts",
        "discord_channel_id": "1566895972859121885",
        "role_id": None
    },

    # --- ช่องที่ 2: ระบุชื่อและลิงก์ของช่องที่ 2 ---
    {
        "name": "ชื่อช่องที่ 2",
        "channel_url": "https://www.youtube.com/@ชื่อช่องที่สอง/videos",
        "discord_channel_id": "ใส่_ID_ห้อง_Discord_ช่องที่_2",
        "role_id": None
    },
    {
        "name": "ชื่อช่องที่ 2 (Shorts)",
        "channel_url": "https://www.youtube.com/@ชื่อช่องที่สอง/shorts",
        "discord_channel_id": "ใส่_ID_ห้อง_Discord_ช่องที่_2",
        "role_id": None
    },

    # --- ช่องที่ 3: ระบุชื่อและลิงก์ของช่องที่ 3 ---
    {
        "name": "ชื่อช่องที่ 3",
        "channel_url": "https://www.youtube.com/@ชื่อช่องที่สาม/videos",
        "discord_channel_id": "ใส่_ID_ห้อง_Discord_ช่องที่_3",
        "role_id": None
    },
    {
        "name": "ชื่อช่องที่ 3 (Shorts)",
        "channel_url": "https://www.youtube.com/@ชื่อช่องที่สาม/shorts",
        "discord_channel_id": "ใส่_ID_ห้อง_Discord_ช่องที่_3",
        "role_id": None
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
    if not target_channel or not str(target_channel).isdigit():
        print(f"Skipped sending: Invalid target channel ID ({target_channel})", flush=True)
        return
    url = f"https://discord.com/api/v10/channels/{target_channel}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"content": content_text}
    response = requests.post(url, headers=headers, json=payload)
    print(f"Sent to Discord ({target_channel}): Status Code {response.status_code}", flush=True)

def fetch_latest_videos(channel_url, headers):
    try:
        res = requests.get(channel_url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"Failed to fetch {channel_url}. Status: {res.status_code}", flush=True)
            return []

        # ดักจับแพตเทิร์นรหัสคลิปทั้งแบบคลิปยาวและ Shorts
        if "/shorts" in channel_url:
            patterns = [
                r'(?:/shorts/|\\/shorts/)([a-zA-Z0-9_-]{11})',
                r'"videoId":"([a-zA-Z0-9_-]{11})"'
            ]
        else:
            patterns = [
                r'(?:/watch\?v=|\\/watch\?v=)([a-zA-Z0-9_-]{11})',
                r'"videoId":"([a-zA-Z0-9_-]{11})"'
            ]

        video_ids = []
        for pattern in patterns:
            matches = re.findall(pattern, res.text)
            if matches:
                video_ids.extend(matches)

        seen = set()
        ordered_ids = []
        for vid in video_ids:
            if vid not in seen:
                seen.add(vid)
                ordered_ids.append(vid)

        videos = []
        for v_id in ordered_ids[:5]:
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

        # ข้ามช่องตัวอย่างที่ยังไม่ได้ใส่ URL หรือ ID ห้องจริง
        if "ชื่อช่อง" in channel_url or not str(target_discord_channel_id).isdigit():
            continue

        videos = fetch_latest_videos(channel_url, headers)
        print(f"[{name}] Found {len(videos)} items on page", flush=True)

        if not videos:
            print(f"Warning: No items parsed for {name}", flush=True)
            continue

        seen_ids = last_videos.get(channel_url, [])
        if isinstance(seen_ids, str):
            seen_ids = [seen_ids]

        recent_videos = videos[:5]

        for video in reversed(recent_videos):
            video_id = video["id"]
            video_link = video["link"]

            if video_id not in seen_ids:
                print(f"Sending video for {name}: {video_id}", flush=True)
                seen_ids.append(video_id)
                updated = True

                if role_id:
                    mention = f"<@&{role_id}> **{name}**"
                else:
                    mention = f"**{name}**"

                message_text = f"{mention}\n{video_link}"

                send_to_discord(message_text, target_discord_channel_id)
                time.sleep(1)

        last_videos[channel_url] = seen_ids

    if updated:
        save_last_videos(last_videos)

if __name__ == "__main__":
    run()
