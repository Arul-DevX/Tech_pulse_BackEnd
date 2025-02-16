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
    "Latest": "https://techcrunch.com/feed/",
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
    "Privacy": "https://techcrunch.com/category/privacy/feed/",
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
    """Fetches the article page and extracts the featured image from og:image."""
    try:
        response = requests.get(article_url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                return og_image["content"]
    except Exception as e:
        print(f"Error fetching image: {e}")
    return None

def clean_html(raw_html):
    """Removes HTML tags from the description."""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text()

def format_date(date_string):
    """Removes +0000 and formats the date properly."""
    try:
        parsed_date = datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %z")
        return parsed_date.strftime("%Y-%m-%d %H:%M:%S")  # Example: 2025-02-15 18:39:14
    except Exception as e:
        print(f"Error formatting date: {e}")
        return date_string  # Return original if parsing fails

def fetch_news(feed_url, category_name):
    """Fetch and parse RSS feed articles."""
    try:
        response = requests.get(feed_url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        feed = feedparser.parse(response.text)
        if not feed.entries:
            print(f"Warning: No entries found for {category_name}. Check the RSS URL.")
            return []

        articles = []
        for entry in feed.entries[:6]:  # Limit to latest 40 articles
            # Extract image from RSS fields
            image_url = None
            if "media_content" in entry:
                image_url = entry.media_content[0]["url"]
            elif "media_thumbnail" in entry:
                image_url = entry.media_thumbnail[0]["url"]
            elif "enclosures" in entry and entry.enclosures:
                image_url = entry.enclosures[0]["href"]
            elif "content" in entry and isinstance(entry.content, list):
                # Check for image inside content
                soup = BeautifulSoup(entry.content[0].value, "html.parser")
                img_tag = soup.find("img")
                if img_tag and img_tag.get("src"):
                    image_url = img_tag["src"]

            # Fetch image from article page if missing
            if not image_url:
                image_url = get_article_image(entry.link)

            categories = [category for category in entry.get("tags", [])]
            category_names = [cat.term for cat in categories] if categories else []

            description_text = clean_html(entry.description) if "description" in entry else "No description"
            formatted_date = format_date(entry.published) if "published" in entry else "No date"

            articles.append({
                "title": entry.title,
                "link": entry.link,
                "description": description_text,
                "author": entry.get("author", "Unknown Author"),
                "published": formatted_date,
                "image": image_url or "https://via.placeholder.com/300",  # Fallback placeholder
                "topics": category_names,
                "category": category_name,
                "source": "TechCrunch"
            })

        return articles
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {category_name} news: {e}")
        return []

@app.route("/api/techcrunch", methods=["GET"])
def get_techcrunch_news():
    """Fetch all TechCrunch news categories."""
    news = []
    all_topics = set()

    for category, url in RSS_FEEDS.items():
        category_news = fetch_news(url, category)
        news.extend(category_news)

        # Collect all unique topics from feeds
        for article in category_news:
            all_topics.update(article["topics"])

    return jsonify({"news": news, "topics": list(all_topics)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Use dynamic port for Render deployment
    app.run(host="0.0.0.0", port=port, debug=True)
