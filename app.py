from flask import Flask, jsonify
from flask_cors import CORS
import requests
import feedparser
from bs4 import BeautifulSoup
import os
import concurrent.futures
from datetime import datetime
from flask_caching import Cache

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS for all routes

# Cache configuration (stores data for 5 minutes)
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = 300  # 5 minutes
cache = Cache(app)
cache.init_app(app)

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
        response.raise_for_status()  # Raises an error for HTTP failures

        feed = feedparser.parse(response.text)
        if not feed.entries:
            print(f"Warning: No entries found for {category_name}. Check the RSS URL.")
            return []

        articles = []
        for entry in feed.entries[:40]:  # Limit to latest 40 articles
            # Extract image directly from RSS feed
            image_url = entry.get("media_content", [{}])[0].get("url", None) or entry.get("media_thumbnail", [{}])[0].get("url", None)

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
                "image": image_url,  # Directly from RSS feed
                "topics": category_names,
                "category": category_name,
                "source": "TechCrunch"
            })

        return articles
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {category_name} news: {e}")
        return []

@app.route("/api/techcrunch", methods=["GET"])
@cache.cached(timeout=300)  # Cache for 5 minutes
def get_techcrunch_news():
    news = []
    all_topics = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_category = {executor.submit(fetch_news, url, category): category for category, url in RSS_FEEDS.items()}

        for future in concurrent.futures.as_completed(future_to_category):
            category_news = future.result()
            news.extend(category_news)

            # Collect unique topics
            for article in category_news:
                all_topics.update(article["topics"])

    return jsonify({"news": news, "topics": list(all_topics)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Use dynamic port for Render deployment
    app.run(host="0.0.0.0", port=port, debug=True)
