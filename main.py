◈ 쿠폰 코드 ◈
포브스선정프리미엄브랜드대상1위트릭컬리바이브지금당장쿠폰입력여기까지붙여넣기
```

สาเหตุที่โค้ดหาไม่เจอในรอบที่แล้ว เพราะมีสัญลักษณ์เพชร (`◈`) ประกบหัวท้าย ทำให้ตัวตรวจจับเดิมมองข้ามไปครับ

---

### จุดแก้ไขใน `extract_coupon_details`
เพิ่มตัวตรวจจับหัวข้อแบบมีสัญลักษณ์พิเศษ (`◈`, `◆`, `◇`, `■`, `▶`) โดยตัดสัญลักษณ์ตกแต่งออกให้เหลือคำเพียวๆ ว่า **`쿠폰코드`** แล้วสั่งให้ **ดึงข้อความในบรรทัดถัดไปมาเป็นรหัสคูปองทันที**[cite: 62]

นำโค้ดด้านล่างนี้ไปวางทับในไฟล์ **`main.py`** ทั้งหมดได้เลยครับ:

```python
import os
import re
import html
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# รหัสและค่าตั้งค่าช่อง Discord
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID_MAIN = os.environ.get("DISCORD_CHANNEL_ID")
CHANNEL_ID_COUPON = os.environ.get("DISCORD_CHANNEL_ID_COUPON") or CHANNEL_ID_MAIN
STORAGE_FILE = "last_ids.json"

TARGET_BOARDS = ["13", "11", "31", "8"]

def load_last_ids():
    """โหลดประวัติโพสต์ และแปลงทุก ID ให้เป็น str ทั้งหมดเพื่อป้องกันชนิดข้อมูลไม่ตรงกัน"""
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            return []
    return []

def save_last_ids(data):
    clean_data = list(dict.fromkeys([str(x).strip() for x in data if str(x).strip()]))
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, ensure_ascii=False, indent=2)

def format_thai_time(timestamp_val):
    kst = timezone(timedelta(hours=9))
    if timestamp_val and (isinstance(timestamp_val, (int, float)) or (isinstance(timestamp_val, str) and timestamp_val.isdigit())):
        dt = datetime.fromtimestamp(int(timestamp_val) / 1000, tz=kst)
    else:
        dt = datetime.now(tz=kst)
    thai_months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"{dt.day} {thai_months[dt.month-1]} {dt.year} {dt.hour:02d}:{dt.minute:02d} น."

def clean_image_url(url):
    if not url: return None
    return url.split("?")[0]

def clean_unwanted_text(text):
    if not text: return ""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        l_str = line.strip()
        if any(store in l_str for store in ["Google Play", "App Store", "원스토어"]):
            continue
        if "다운로드" in l_str and "바로" in l_str:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def format_table_to_text(table_html):
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, flags=re.DOTALL | re.IGNORECASE)
    formatted_rows = []
    for r in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, flags=re.DOTALL | re.IGNORECASE)
        clean_cells = []
        for c in cells:
            c_text = re.sub(r'<[^>]+>', ' ', c)
            c_text = html.unescape(c_text).strip()
            c_text = re.sub(r'\s+', ' ', c_text)
            if c_text:
                clean_cells.append(c_text)
        if clean_cells:
            if len(clean_cells) == 2:
                formatted_rows.append(f"• {clean_cells[0]}: {clean_cells[1]}")
            else:
                formatted_rows.append(" - " + " | ".join(clean_cells))
    return "\n" + "\n".join(formatted_rows) + "\n"

def parse_html_to_sections(raw_html):
    if not raw_html: return []
    raw_html = re.sub(r'<table[^>]*>(.*?)</table>', lambda m: format_table_to_text(m.group(0)), raw_html, flags=re.DOTALL | re.IGNORECASE)

    def img_replacer(match):
        tag = match.group(0)
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if m:
            img_url = m.group(1).strip()
            if img_url.startswith("//"): img_url = "https:" + img_url
            if img_url.startswith("http"):
                clean_url = clean_image_url(img_url)
                return f"\n[[IMG_TOKEN:{clean_url}]]\n"
        return ""

    text = re.sub(r'<img[^>]+>', img_replacer, raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<\s*br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:p|div|h[1-6]|tr|li|ul|ol)\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', text).strip()

    tokens = re.split(r'\[\[IMG_TOKEN:(https?://[^\]]+)\]\]', text)
    sections = []
    
    for i in range(0, len(tokens), 2):
        chunk_text = clean_unwanted_text(tokens[i].strip())
        img = tokens[i+1].strip() if i+1 < len(tokens) else None
        
        if chunk_text:
            while len(chunk_text) > 1800:
                cut_idx = chunk_text.rfind('\n', 0, 1800)
                if cut_idx == -1: cut_idx = 1800
                sections.append({"text": chunk_text[:cut_idx].strip(), "image": None})
                chunk_text = chunk_text[cut_idx:].strip()
            if chunk_text:
                sections.append({"text": chunk_text, "image": None})
                
        if img:
            sections.append({"text": "", "image": img})

    return sections

def is_valid_coupon_code(code_str):
    """ตรวจสอบว่าเป็นรหัสคูปองแท้ ไม่ใช่ประโยคพูดคุยหรือคำเกริ่น"""
    if not code_str:
        return False
    bad_chars = ['?', '!', ',', '.', '~', '"', "'", '(', ')']
    if any(c in code_str for c in bad_chars):
        return False
    bad_words = ["감사", "마음", "뜻으로", "받아", "주세요", "길어졌지만", "안내", "확인", "아래", "다음", "사항", "유의", "보상"]
    if any(w in code_str for w in bad_words):
        return False
    if len(code_str.strip()) < 4:
        return False
    return True

def extract_coupon_details(raw_html):
    """แกะรหัสคูปองและระยะเวลาการใช้งานจากทั้งบรรทัดเพชร ◈ และตารางอย่างแม่นยำ"""
    coupon_code = None
    claim_period = None

    # แปลง HTML เป็นข้อความแยกทีละบรรทัด
    text = re.sub(r'<\s*br\s*/?>', '\n', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:p|div|tr|li|h[1-6])\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/(?:td|th)\s*>', ' | ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace('\xa0', ' ')
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    for idx, line in enumerate(lines):
        # ตัดอักขระพิเศษ สัญลักษณ์เพชร ◈◆◇ และช่องว่างออกทั้งหมดเพื่อเช็กคำหลัก
        pure_korean = re.sub(r'[^가-힣a-zA-Z0-9]', '', line)

        # ตรวจจับหัวข้อ "쿠폰코드" / "쿠폰번호" / "쿠폰명" (เช่น ◈ 쿠폰 코드 ◈)
        if pure_korean in ["쿠폰코드", "쿠폰번호", "쿠폰명", "코드"]:
            # ดึงบรรทัดถัดไปทันที
            if idx + 1 < len(lines):
                cand = lines[idx + 1].strip()
                cand_clean = re.sub(r'^[◈◆◇■▶※\:\=\|\-\s\[\]\(\)]+', '', cand)
                cand_clean = re.sub(r'[◈◆◇■▶※\:\=\|\-\s\[\]\(\)]+$', '', cand_clean).strip()
                if is_valid_coupon_code(cand_clean):
                    coupon_code = cand_clean

        # ตรวจจับกรณีที่รหัสอยู่ในบรรทัดเดียวกันโดยมีเครื่องหมายคั่น
        elif not coupon_code and any(k in pure_korean for k in ["쿠폰코드", "쿠폰번호"]):
            m = re.search(r'(?:쿠폰\s*코드|쿠폰\s*번호|쿠폰명)\s*[◈◆◇■▶※\:\=\|\-\s]*[:：\|]\s*([^\n\r\|◈◆◇]+)', line)
            if m:
                cand = m.group(1).strip()
                if is_valid_coupon_code(cand):
                    coupon_code = cand

        # ตรวจจับระยะเวลาการใช้งาน
        if not claim_period and any(k in pure_korean for k in ["사용기간", "입력기간", "쿠폰기간"]):
            m_p = re.search(r'(?:사용\s*기간|입력\s*기간|쿠폰\s*기간)\s*[◈◆◇■▶※\:\=\|\-\s]*[:：\|]?\s*([^\n\r]+)', line)
            if m_p and "~" in m_p.group(1):
                claim_period = m_p.group(1).strip()
            elif idx + 1 < len(lines):
                cand_p = lines[idx + 1].strip().lstrip('|:- ').strip()
                if "~" in cand_p:
                    claim_period = cand_p

    # Fallback ถ้าเป็นตาราง HTML
    if not coupon_code:
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', raw_html, flags=re.DOTALL | re.IGNORECASE):
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, flags=re.DOTALL | re.IGNORECASE)
            clean_cells = [html.unescape(re.sub(r'<[^>]+>', '', c)).replace('\xa0', ' ').strip() for c in cells]
            clean_cells = [c for c in clean_cells if c]
            if len(clean_cells) >= 2:
                col0 = re.sub(r'[^가-힣a-zA-Z0-9]', '', clean_cells[0])
                col1 = clean_cells[1].strip()
                if col0 in ["쿠폰번호", "쿠폰코드", "쿠폰명"] and is_valid_coupon_code(col1):
                    coupon_code = col1
                if col0 in ["사용기간", "입력기간", "쿠폰기간"] and not claim_period:
                    claim_period = col1

    # Fallback สำหรับหาระยะเวลา (หาช่วงวันที่ที่มีเครื่องหมาย ~)
    if not claim_period:
        m_date = re.search(r'(\d+월\s*\d+일[^\n\r~]+~[^\n\r]+)', text)
        if m_date:
            claim_period = m_date.group(1).strip()

    return coupon_code or "확인 불가 (ตรวจสอบในลิงก์)", claim_period or "공지 확인 (ตรวจสอบในลิงก์)"

def get_coupon_image(raw_contents, target_data):
    """ดึงรูปภาพคูปองตัวจริง โดยข้ามรูปแบนเนอร์หัวเรื่องเอเลน่า"""
    comic_images = []
    if raw_contents:
        img_tags = re.findall(r'<img[^>]+>', raw_contents, flags=re.IGNORECASE)
        for tag in img_tags:
            m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if m:
                url = m.group(1).strip()
                if url.startswith("//"): url = "https:" + url
                if url.startswith("http"):
                    clean = clean_image_url(url)
                    if clean and not any(k in clean.lower() for k in ["icon", "logo", "favicon", "profile", "twimg", "badge"]):
                        comic_images.append(clean)

    if len(comic_images) > 1:
        return comic_images[1]
    elif len(comic_images) == 1:
        return comic_images[0]

    reps = target_data.get("representations", [])
    for rep in reps:
        if rep.get("representationType") == "IMAGE" and rep.get("path"):
            return clean_image_url(rep.get("path"))
    return None

def fetch_feed_detail(feed_id):
    url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed/{feed_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    }
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=25)
            if res.status_code == 200:
                feed = res.json().get("content", {}).get("feed")
                if feed and feed.get("contents"):
                    return feed
        except Exception as e:
            print(f"Attempt {attempt+1} fetching detail {feed_id} failed: {e}", flush=True)
            time.sleep(2)
    return None

def fetch_lounge_feeds():
    all_feeds = []
    for b_id in TARGET_BOARDS:
        api_url = f"https://comm-api.game.naver.com/nng_main/v1/community/lounge/Trickcal/feed?boardId={b_id}&buffFilteringYN=N&limit=10&offset=0&order=NEW"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": f"https://game.naver.com/lounge/Trickcal/board/{b_id}"
        }
        try:
            res = requests.get(api_url, headers=headers, timeout=15)
            if res.status_code == 200:
                content = res.json().get("content", {})
                feeds = (content.get("noticeFeeds") or []) + (content.get("feeds") or [])
                all_feeds.extend(feeds)
        except Exception as e:
            print(f"Error fetching board {b_id}: {e}", flush=True)
    return all_feeds

def send_to_discord_bot(channel_id, payload):
    if not channel_id: return
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    for _ in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code in (200, 201, 204):
                return
            elif resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 2)
                time.sleep(float(retry_after) + 0.5)
            else:
                break
        except Exception:
            time.sleep(2)

def send_coupon_to_discord(feed_summary, target_data):
    feed_id = str(feed_summary.get("feedId")).strip()
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    title = target_data.get("title") or "쿠폰 안내"
    raw_contents = target_data.get("contents") or ""
    
    coupon_code, claim_period = extract_coupon_details(raw_contents)
    banner_url = get_coupon_image(raw_contents, target_data)
    redeem_url = "https://coupon.a.prod.service.trickcal.io/"

    desc = (
        f"**{title}**\n\n"
        f"**Coupon Code (ในมือถือกดค้าง Copy ได้)**\n"
        f"`{coupon_code}`\n\n"
        f"**Coupon Claim Period**\n"
        f"{claim_period}"
    )

    coupon_embed = {
        "title": "Trickcal RE:VIVE KR - Coupon",
        "url": post_url,
        "description": desc,
        "color": 0x9B59B6,
        "footer": {
            "text": f"เคธี่น่ารัก 🍖 | ID: {feed_id}"
        }
    }
    if banner_url:
        coupon_embed["image"] = {"url": banner_url}

    payload = {
        "embeds": [coupon_embed],
        "components": [{
            "type": 1,
            "components": [{
                "type": 2,
                "style": 5,
                "label": "Ingame or Click Here",
                "url": redeem_url,
                "emoji": {"name": "🟢"}
            }]
        }]
    }
    send_to_discord_bot(CHANNEL_ID_COUPON, payload)
    print(f"Sent coupon {feed_id} successfully. Code: {coupon_code}", flush=True)

def send_lounge_to_discord(feed_summary):
    feed_id = str(feed_summary.get("feedId")).strip()
    post_url = f"https://game.naver.com/lounge/Trickcal/board/detail/{feed_id}"
    
    target_data = fetch_feed_detail(feed_id) or feed_summary
    title = target_data.get("title") or "공지사항"
    
    if "쿠폰" in title or "COUPON" in title.upper():
        send_coupon_to_discord(feed_summary, target_data)
        return

    raw_contents = target_data.get("contents") or ""
    color = 0x2ECC71
    date_str = format_thai_time(target_data.get("writtenAt") or target_data.get("createdAt") or target_data.get("timestamp"))
    thumb_url = clean_image_url(next((rep.get("path") for rep in target_data.get("representations", []) if rep.get("representationType") == "IMAGE" and rep.get("path")), None))

    header_embed = {
        "title": "트릭컬 리바이브 (Trickcal RE:VIVE)", 
        "url": post_url,
        "description": f"**{title}**\n{date_str}   |   ID: {feed_id}", 
        "color": color
    }
    if thumb_url: 
        header_embed["thumbnail"] = {"url": thumb_url}

    sections = parse_html_to_sections(raw_contents)
    content_embeds = []
    
    for sec in sections:
        emb = {"color": color}
        if sec["text"]:
            emb["description"] = sec["text"]
        if sec["image"]:
            emb["image"] = {"url": sec["image"]}
        if emb.get("description") or emb.get("image"):
            content_embeds.append(emb)

    if len(content_embeds) > 28:
        content_embeds = content_embeds[:28]
        content_embeds.append({
            "description": "[ 컴포넌트 초과로 자세한 내용은 생략합니다 / เนื้อหายาวเกินกำหนด สามารถอ่านฉบับเต็มได้ในลิงก์ Naver ]",
            "color": color
        })

    batches = []
    current_batch = [header_embed]
    current_char_count = len(header_embed.get("title", "")) + len(header_embed.get("description", ""))

    for emb in content_embeds:
        desc_len = len(emb.get("description") or "")
        if len(current_batch) >= 10 or (current_char_count + desc_len > 5000 and current_batch):
            batches.append(current_batch)
            current_batch = [emb]
            current_char_count = desc_len
        else:
            current_batch.append(emb)
            current_char_count += desc_len

    if current_batch:
        batches.append(current_batch)

    components = [{
        "type": 1,
        "components": [{
            "type": 2, "style": 5, "label": " 네이버 라운지 (Naver Lounge)", "url": post_url, "emoji": {"name": "🟢"}
        }]
    }]

    for idx, batch in enumerate(batches):
        payload = {"embeds": batch}
        if idx == 0:
            payload["components"] = components
        send_to_discord_bot(CHANNEL_ID_MAIN, payload)
        time.sleep(1.5)

def run():
    if not BOT_TOKEN:
        print("Missing BOT_TOKEN", flush=True)
        return

    seen_ids = load_last_ids()
    feeds = fetch_lounge_feeds()
    if not feeds:
        return

    unique_feeds = []
    temp_seen = set()
    for f in feeds:
        fid = str(f.get("feedId")).strip()
        if fid not in temp_seen:
            temp_seen.add(fid)
            unique_feeds.append(f)

    if not seen_ids:
        all_current = [str(f.get("feedId")).strip() for f in unique_feeds]
        save_last_ids(all_current)
        print("Initial run: Saved current history.")
        return

    is_test_mode = "0" in seen_ids
    seen_ids = [x for x in seen_ids if x != "0"]
    new_posts = [f for f in unique_feeds if str(f.get("feedId")).strip() not in seen_ids]

    if is_test_mode and new_posts: 
        new_posts = new_posts[:3]

    if new_posts:
        posts_to_send = new_posts[:3]
        for post in reversed(posts_to_send): 
            fid = str(post.get("feedId")).strip()
            try:
                send_lounge_to_discord(post)
                print(f"Sent post {fid} successfully.", flush=True)
            except Exception as e:
                print(f"Error sending post {fid}: {e}", flush=True)
            
            if fid not in seen_ids:
                seen_ids.append(fid)
            save_last_ids(seen_ids[-100:])

        for f in unique_feeds:
            fid = str(f.get("feedId")).strip()
            if fid not in seen_ids:
                seen_ids.append(fid)
        save_last_ids(seen_ids[-100:])
    else:
        print("No new posts found.")

if __name__ == "__main__":
    run()
