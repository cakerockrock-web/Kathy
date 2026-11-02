import os
import json
import requests

CAFE_ID = "30131231"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STORAGE_FILE = "last_ids.json"

CATEGORIES = [
    {
        "menu_id": "0",
        "name": "🔥 ทดสอบ: โพสต์ทั้งหมด (All Posts)",
        "color": 0xE74C3C
    },
    {
        "menu_id": "67",
        "name": "🎟️ คูปอง / กิจกรรม",
        "color": 0xF1C40F
    },
    {
        "menu_id": "68",
        "name": "🛠️ ประกาศอัปเดต",
        "color": 0x3498DB
    },
    {
        "menu_id": "85",
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

def fetch_articles(menu_id):
    # ใช้ Mobile Endpoint ของ Naver Cafe ซึ่งเปิดรับคำขอจากภายนอกได้เสถียรกว่า
    api_url = f"https://apis.naver.com/cafe-web/cafe-mobile/CafeMemberNetworkArticleList?cafeId={CAFE_ID}"
    if menu_id != "0":
        api_url = f"https://apis.naver.com/cafe-web/cafe-mobile/CafeMemberNetworkArticleList?cafeId={CAFE_ID}&menuId={menu_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": f"https://m.cafe.naver.com/ca-fe/web/cafes/{CAFE_ID}/menus/{menu_id}",
        "Origin": "https://m.cafe.naver.com"
    }

    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        
        # ตรวจสอบสถานะ HTTP Status Code
        if res.status_code != 200:
            print(f"Menu {menu_id}: HTTP Error {res.status_code} - Body: {res.text[:100]}", flush=True)
            return []

        data = res.json()
        articles = data.get("message", {}).get("result", {}).get("articleList", [])
        return articles
    except Exception as e:
        print(f"Menu {menu_id} Exception: {e}", flush=True)
        return []

def send_to_discord(article, category):
    article_id = article.get("articleId")
    title = article.get("subject", "ประกาศใหม่")
    post_url = f"https://cafe.naver.com/ca-fe/cafes/{CAFE_ID}/articles/{article_id}"
    image_url = article.get("representImage")

    embed = {
        "title": title,
        "url": post_url,
        "description": f"มีโพสต์ใหม่ในหมวด **{category['name']}**",
        "color": category["color"],
        "footer": {
            "text": "Naver Cafe • Trickcal Re:vive"
        }
    }
    if image_url:
        embed["image"] = {"url": image_url}

    payload = {
        "username": "Trickcal Cafe Notifier",
        "embeds": [embed]
    }
    
    resp = requests.post(WEBHOOK_URL, json=payload)
    print(f"Sent post {article_id} to Discord - Status: {resp.status_code}", flush=True)

def run():
    if not WEBHOOK_URL:
        print("Missing DISCORD_WEBHOOK", flush=True)
        return

    last_ids = load_last_ids()
    updated = False

    for cat in CATEGORIES:
        menu_id = cat["menu_id"]
        articles = fetch_articles(menu_id)
        if not articles:
            print(f"Menu {menu_id}: No articles returned or failed to load", flush=True)
            continue

        saved_id = str(last_ids.get(menu_id, ""))
        latest_id = str(articles[0].get("articleId"))

        if not saved_id:
            last_ids[menu_id] = latest_id
            updated = True
            print(f"Menu {menu_id}: Initialized latest ID to {latest_id}", flush=True)
            continue

        new_posts = []
        for art in articles:
            art_id = str(art.get("articleId"))
            if art_id == saved_id:
                break
            new_posts.append(art)

        if new_posts:
            print(f"Menu {menu_id}: Found {len(new_posts)} new posts. Sending...", flush=True)
            for post in reversed(new_posts):
                send_to_discord(post, cat)
            last_ids[menu_id] = latest_id
            updated = True
        else:
            print(f"Menu {menu_id}: Up to date (Latest: {latest_id})", flush=True)

    if updated:
        save_last_ids(last_ids)

if __name__ == "__main__":
    run()
