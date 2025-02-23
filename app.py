from flask import Flask, jsonify
from flask_cors import CORS
from flask_caching import Cache  # Import Flask-Caching
import requests
import feedparser
from bs4 import BeautifulSoup
import os
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS

# Flask-Caching configuration
app.config["CACHE_TYPE"] = "simple"  # In-memory caching
app.config["CACHE_DEFAULT_TIMEOUT"] = 600  # Cache for 10 minutes
cache = Cache(app)  # Initialize cache

# RSS Feeds
RSS_FEEDS = {
    "Latest": "https://techcrunch.com/feed/",
    "AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "Apps": "https://techcrunch.com/category/apps/feed/",
    "Security": "https://techcrunch.com/category/security/feed/",
    "Climate": "https://techcrunch.com/category/climate/feed/",
    "Cloud Computing": "https://techcrunch.com/tag/cloud-computing/feed/",
    "Gadgets": "https://techcrunch.com/category/gadgets/feed/",
    "Gaming": "https://techcrunch.com/category/gaming/feed/",
    "Space": "https://techcrunch.com/category/space/feed/",
    "Government Policy": "https://techcrunch.com/category/government-policy/feed/",
    "Layoffs": "https://techcrunch.com/tag/layoffs/feed/",
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

def clean_html(raw_html):
    """Removes HTML tags from the description."""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text()

def format_date(date_string):
    """Formats the date properly."""
    try:
        parsed_date = datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %z")
        return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error formatting date: {e}")
        return date_string

@cache.memoize(timeout=600)  # Cache each category's news for 10 minutes
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
        for entry in feed.entries[:15]:  # Limit to latest 15 articles
            image_url = None
            if "media_content" in entry:
                image_url = entry.media_content[0]["url"]
            elif "media_thumbnail" in entry:
                image_url = entry.media_thumbnail[0]["url"]
            elif "enclosures" in entry and entry.enclosures:
                image_url = entry.enclosures[0]["href"]

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
                "image": image_url or None,  # Remove placeholder
                "topics": category_names,
                "category": category_name,
                "source": "TechCrunch"
            })

        return articles
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {category_name} news: {e}")
        return []

@app.route("/api/techcrunch", methods=["GET"])
@cache.cached(timeout=300)  # Cache the entire API response for 5 minutes
def get_techcrunch_news():
    """Fetch all TechCrunch news categories."""
    news = []
    all_topics = set()

    for category, url in RSS_FEEDS.items():
        category_news = fetch_news(url, category)
        news.extend(category_news)

        for article in category_news:
            all_topics.update(article["topics"])

    return jsonify({"news": news, "topics": list(all_topics)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Use dynamic port for Render
    app.run(host="0.0.0.0", port=port, debug=True)
