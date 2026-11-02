import os
import re
import html
import json
import requests
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID_MAIN = os.environ.get("DISCORD_CHANNEL_ID")
CHANNEL_ID_COUPON = os.environ.get("DISCORD_CHANNEL_ID_COUPON") 
STORAGE_FILE = "last_ids.json"

CATEGORIES = [
    {"board_id": "8", "name": "공지사항 (ประกาศอัปเดต)", "color": 0x3498DB},
    {"board_id": "11", "name": "이벤트 (คูปอง /กิจกรรม)", "color": 0xF1C40F},
    {"board_id": "31", "name": "개발자 노트 (Dev Note)", "color": 0x9E6649}
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

def format_thai_time(timestamp_val):
    kst = timezone(timedelta(hours=9))
    if timestamp_val and (isinstance(timestamp_val, (int, float)) or (isinstance(timestamp_val, str) and timestamp_val.isdigit())):
        dt = datetime.fromtimestamp(int(timestamp_val) / 1000, tz=kst)
    else:
        dt = datetime.now(tz=kst)
    thai_months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"{dt.day} {thai_months[dt.month-1]} {dt.year} {dt.hour:02d}:{dt.minute:02d} น."

def parse_html_to_sections(raw_html):
    if not raw_html: return []
    def img_replacer(match):
        tag = match.group(0)
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if m:
            img_url = m.group(1).strip()
            if img_url.startswith("//"): img_url = "https:" + img_url
            if img_url.startswith("http"): return f"[[IMG_TOKEN:{img_url}]]"
        return ""
    text = re.sub(r'<img[^>]+>', img_replacer, raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<\s*br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:p|div|h[1-6]|tr|li|ul|ol)\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:td|th)\s*>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', text).strip()

    tokens = re.split(r'\[\[IMG_TOKEN:(https?://[^\]]+)\]\]', text)
    sections = []
    for i in range(0, len(tokens), 2):
        txt = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', tokens[i].strip())
        img = tokens[i+1].strip() if i+1 < len(tokens) else None
        if txt or img: sections.append({"text": txt, "image": img})
    return sections

def extract_coupon_info(text):
    coupon_code = "N/A"
    claim_period = None
    
    match_code = re.search(r'쿠폰\s*코드[^\n]*\n+([^\n]+)', text)
    if match_code:
        coupon_code = match_code.group(1).replace('◆', '').replace('◇', '').strip()
        
    if coupon_code == "N/A" or not coupon_code:
        code_match = re.search(r'([A-Z0-9]{6,20})', text)
        if code_match:
            coupon_code = code_match.group(1)
            
    match_period = re.search(r'사용\s*기한[^\n]*\n+([^\n]+)', text)
    if match_period:
        claim_period = match_period.group(1).strip()
        if claim_period.startswith("-"):
            claim_period = claim_period[1:].strip()
            
    return coupon_code, claim_period

def fetch_feed_detail(feed_id):
    url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed/{feed_id}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200: return res.json().get("content", {}).get("feed")
    except: pass
    return None

def fetch_lounge_feeds(board_id):
    api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={board_id}&buffFilteringYN=N&limit=5&offset=0&order=NEW"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://game.naver.com/lounge/Trickcal/board/{board_id}"}
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200: return res.json().get("content", {}).get("feeds", [])
    except: pass
    return []

def send_to_discord_bot(payload, target_channel):
    if not target_channel:
        print("Error: Target channel ID is empty!", flush=True)
        return
        
    url = f"https://discord.com/api/v10/channels/{target_channel}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, headers=headers, json=payload)
    return resp.status_code

def send_coupon_layout(target_data, feed_id, post_url, color, thumb_url, date_str, target_channel):
    raw_contents = target_data.get("contents") or ""
    sections = parse_html_to_sections(raw_contents)
    full_text = "\n".join([sec["text"] for sec in sections if sec["text"]])
    
    coupon_code, claim_period = extract_coupon_info(full_text)
    display_period = claim_period if claim_period else f"โพสต์เมื่อ: {date_str}"

    body_images = []
    for sec in sections:
        if sec.get("image") and sec["image"] not in body_images:
            body_images.append(sec["image"])

    selected_image = None
    if len(body_images) >= 3:
        selected_image = body_images[1]  
    elif len(body_images) == 2:
        selected_image = body_images[-1] 
    elif len(body_images) == 1:
        selected_image = body_images[0]  
    elif not body_images and thumb_url:
        selected_image = thumb_url

    embed = {
        "author": {
            "name": "Trickcal RE:VIVE KR - Coupon",
        },
        "title": target_data.get("title") or "쿠폰 안내",
        "color": 0x9B59B6,
        "fields": [
            {"name": "Coupon Code (ในมือถือกดค้าง Copy ได้)", "value": f"`{coupon_code}`", "inline": False},
            {"name": "Coupon Claim Period", "value": display_period, "inline": False}
        ],
        "footer": {"text": f"เคธี่น่ารัก 🍬 | ID: {feed_id}"}
    }
    
    if selected_image:
        embed["image"] = {"url": selected_image}
    
    payload = {
        "embeds": [embed],
        "components": [{
            "type": 1,
            "components": [{
                "type": 2, 
                "style": 5, 
                "label": " Ingame or Click Here", 
                "url": post_url, 
                "emoji": {"name": "🟢"}
            }]
        }]
    }
    send_to_discord_bot(payload, target_channel)

def send_to_discord(feed_summary, category):
    feed_id = str(feed_summary.get("feedId"))
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    target_data = fetch_feed_detail(feed_id) or feed_summary
    title = target_data.get("title") or "공지사항"
    raw_contents = target_data.get("contents") or ""
    color = category["color"]
    date_str = format_thai_time(target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("timestamp"))
    thumb_url = next((rep.get("path") for rep in target_data.get("representations", []) if rep.get("representationType") == "IMAGE" and rep.get("path")), None)

    if "쿠폰" in title:
        route_to = CHANNEL_ID_COUPON if CHANNEL_ID_COUPON else CHANNEL_ID_MAIN
        send_coupon_layout(target_data, feed_id, post_url, color, thumb_url, date_str, route_to)
        return

    header_embed = {
        "title": "트릭컬 리바이브", 
        "description": f"**{title}**\n{date_str}   |   ID: {feed_id}", 
        "color": color
    }
    if thumb_url: header_embed["thumbnail"] = {"url": thumb_url}

    payload_header = {
        "embeds": [header_embed],
        "components": [{
            "type": 1,
            "components": [{
                "type": 2, "style": 5, "label": " ไปที่ลิงก์", "url": post_url, "emoji": {"name": "🟢"}
            }]
        }]
    }
    send_to_discord_bot(payload_header, CHANNEL_ID_MAIN)

    sections = parse_html_to_sections(raw_contents)
    content_embeds = []
    
    for sec in sections:
        sec_text = sec["text"][:2000].rstrip() + "..." if len(sec["text"]) > 2000 else sec["text"]
        emb = {"color": color}
        if sec_text: emb["description"] = sec_text
        if sec["image"]: emb["image"] = {"url": sec["image"]}
        if emb.get("description") or emb.get("image"): content_embeds.append(emb)

    if len(content_embeds) > 25:
        content_embeds = content_embeds[:25]
        content_embeds.append({"description": "[ คอมโพเนนต์เกินขีดจำกัด ขอละรายละเอียดบางส่วนไว้ ]", "color": color})

    MAX_EMBEDS = 10 
    for i in range(0, len(content_embeds), MAX_EMBEDS):
        batch = content_embeds[i:i + MAX_EMBEDS]
        send_to_discord_bot({"embeds": batch}, CHANNEL_ID_MAIN)

def run():
    if not BOT_TOKEN or not CHANNEL_ID_MAIN:
        print("Missing BOT_TOKEN or CHANNEL_ID_MAIN", flush=True)
        return

    last_ids = load_last_ids()
    updated = False

    for cat in CATEGORIES:
        board_id = cat["board_id"]
        feeds = fetch_lounge_feeds(board_id)
        if not feeds: continue

        saved_id = str(last_ids.get(board_id, ""))
        latest_id = str(feeds[0].get("feedId"))

        if not saved_id:
            last_ids[board_id] = latest_id
            updated = True
            continue

        new_posts = []
        for feed in feeds:
            f_id = str(feed.get("feedId"))
            if f_id == saved_id: break
            new_posts.append(feed)

        if saved_id == "0" and new_posts: 
            new_posts = [new_posts[0]]

        if new_posts:
            for post in reversed(new_posts): 
                send_to_discord(post, cat)
            last_ids[board_id] = latest_id
            updated = True

    if updated: save_last_ids(last_ids)

if __name__ == "__main__":
    run()
