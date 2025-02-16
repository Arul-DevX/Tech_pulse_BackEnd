from flask import Flask, jsonify
from flask_cors import CORS
import requests
import feedparser
from bs4 import BeautifulSoup
import os
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS for all routes

# RSS Feeds
RSS_FEEDS = {
    "AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "Apps": "https://techcrunch.com/category/apps/feed/",
    "Security": "https://techcrunch.com/category/security/feed/",
    "Climate": "https://techcrunch.com/category/climate/feed/",
    "Cloud Computing": "https://techcrunch.com/category/cloud-computing/feed/",
    "Gadgets": "https://techcrunch.com/category/gadgets/feed/",
    "Gaming": "https://techcrunch.com/category/gaming/feed/",
    "Space": "https://techcrunch.com/category/space/feed/",
    "Government Policy": "https://techcrunch.com/category/government-policy/feed/",
    "Layoffs": "https://techcrunch.com/category/layoffs/feed/",
    "privacy": "https://techcrunch.com/category/privacy/feed/",
    "Social": "https://techcrunch.com/category/social/feed/",
    "Media Entertainment": "https://techcrunch.com/category/media-entertainment/feed/",
    "Crypto Currency": "https://techcrunch.com/category/cryptocurrency/feed/",
    "Robotics": "https://techcrunch.com/category/robotics/feed/",
    "Startups": "https://techcrunch.com/category/startups/feed/",
    "Enterprise": "https://techcrunch.com/category/enterprise/feed/",
    "Commerce": "https://techcrunch.com/category/commerce/feed/",
    "Biotech Health": "https://techcrunch.com/category/biotech-health/feed/"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_article_image(article_url):
    """Fetches the article page and extracts the featured image"""
    try:
        response = requests.get(article_url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image["content"]:
                return og_image["content"]
    except Exception as e:
        print(f"Error fetching image: {e}")
    return None

def clean_html(raw_html):
    """Removes HTML tags from the description"""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text()

def format_date(date_string):
    """Removes +0000 and formats the date properly"""
    try:
        parsed_date = datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %z")
        return parsed_date.strftime("%Y-%m-%d %H:%M:%S")  # Example: 2025-02-15 18:39:14
    except Exception as e:
        print(f"Error formatting date: {e}")
        return date_string  # Return original if parsing fails

def fetch_news(feed_url, category_name):
    """Fetch and parse RSS feed articles"""
    response = requests.get(feed_url, headers=HEADERS)
    if response.status_code != 200:
        return []

    feed = feedparser.parse(response.text)
    if not feed.entries:
        return []

    articles = []
    for entry in feed.entries[:40]:  # Fetch latest 5 articles from each category
        image_url = get_article_image(entry.link)  # Fetch image from article page
        categories = [category for category in entry.get("tags", [])]  # Extract categories
        category_names = [cat.term for cat in categories] if categories else []

        # Clean description and format date
        description_text = clean_html(entry.description) if "description" in entry else "No description"
        formatted_date = format_date(entry.published) if "published" in entry else "No date"

        articles.append({
            "title": entry.title,
            "link": entry.link,
            "description": description_text,  # Cleaned text without HTML tags
            "author": entry.get("author", "Unknown Author"),  # Extracted Author
            "published": formatted_date,  # Formatted date
            "image": image_url,  # Fetched from the article
            "topics": category_names,  # TechCrunch topics (categories)
            "category": category_name,  # AI or Apps
            "source": "TechCrunch"
        })

    return articles

@app.route("/api/techcrunch", methods=["GET"])
def get_techcrunch_news():
    news = []
    all_topics = set()

    for category, url in RSS_FEEDS.items():
        category_news = fetch_news(url, category)
        news.extend(category_news)

        # Collect all unique topics from both feeds
        for article in category_news:
            all_topics.update(article["topics"])

    return jsonify({"news": news, "topics": list(all_topics)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Use dynamic port for Render deployment
    app.run(host="0.0.0.0", port=port, debug=True)
