import os
import json
import requests

CAFE_ID = "30131231"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STORAGE_FILE = "last_ids.json"

# กำหนดหมวดหมู่ที่ต้องการเฝ้าดู (เพิ่ม/ลด หรือเปลี่ยนสีได้ตามใจชอบ)
CATEGORIES = [
    {
        "menu_id": "67",
        "name": "🎟️ คูปอง / กิจกรรม",
        "color": 0xF1C40F  # สีทอง
    },
    {
        "menu_id": "68",
        "name": "🛠️ ประกาศอัปเดต",
        "color": 0x3498DB  # สีฟ้า
    },
    {
        "menu_id": "85",
        "name": "📝 Dev Note (สารจากผู้พัฒนา)",
        "color": 0x9B59B6  # สีม่วง
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
    api_url = f"https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json?cafeId={CAFE_ID}&menuId={menu_id}&page=1&perPage=5"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://cafe.naver.com/f-e/cafes/{CAFE_ID}/menus/{menu_id}"
    }
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        data = res.json()
        return data.get("message", {}).get("result", {}).get("articleList", [])
    except Exception as e:
        print(f"Error fetching menu {menu_id}: {e}")
        return []

def send_to_discord(article, category):
    article_id = article.get("articleId")
    title = article.get("subject", "ประกาศใหม่")
    post_url = f"https://cafe.naver.com/f-e/cafes/{CAFE_ID}/articles/{article_id}"
    image_url = article.get("representImage")

    embed = {
        "title": title,
        "url": post_url,
        "description": f"มีโพสต์ใหม่ในหมวด **{category['name']}**",
        "color": category["color"],
        "footer": {
            "text": f"Naver Cafe • Trickcal Re:vive"
        }
    }
    if image_url:
        embed["image"] = {"url": image_url}

    payload = {
        "username": "Trickcal Cafe Notifier",
        "embeds": [embed]
    }
    requests.post(WEBHOOK_URL, json=payload)

def run():
    if not WEBHOOK_URL:
        print("Missing DISCORD_WEBHOOK")
        return

    last_ids = load_last_ids()
    updated = False

    for cat in CATEGORIES:
        menu_id = cat["menu_id"]
        articles = fetch_articles(menu_id)
        if not articles:
            continue

        saved_id = str(last_ids.get(menu_id, ""))
        latest_id = str(articles[0].get("articleId"))

        # รันครั้งแรกของหมวดนี้ ให้จดจำ ID ล่าสุดไว้ก่อน
        if not saved_id:
            last_ids[menu_id] = latest_id
            updated = True
            print(f"Initialized menu {menu_id} with ID: {latest_id}")
            continue

        # ค้นหาโพสต์ใหม่ที่ยังไม่ได้ส่ง
        new_posts = []
        for art in articles:
            art_id = str(art.get("articleId"))
            if art_id == saved_id:
                break
            new_posts.append(art)

        # ส่งเรียงจากโพสต์เก่าไปใหม่
        if new_posts:
            for post in reversed(new_posts):
                send_to_discord(post, cat)
            last_ids[menu_id] = latest_id
            updated = True
            print(f"Sent {len(new_posts)} new notices for menu {menu_id}")

    if updated:
        save_last_ids(last_ids)

if __name__ == "__main__":
    run()
