from flask import Flask, jsonify
from flask_cors import CORS
from flask_caching import Cache
import requests
import feedparser
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime
from urllib.parse import urljoin

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Flask-Caching configuration
app.config["CACHE_TYPE"] = "simple"
app.config["CACHE_DEFAULT_TIMEOUT"] = 600
cache = Cache(app)

# RSS Feeds
RSS_FEEDS = {
    "Latest": "https://techcrunch.com/feed/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_html(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text()

def format_date(date_string):
    try:
        parsed_date = datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %z")
        return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error formatting date: {e}")
        return date_string

@cache.memoize(timeout=3600)  # Cache for 1 hour
def get_techcrunch_image(article_url):
    """
    Scrape the TechCrunch article page to find the WordPress featured image
    """
    try:
        response = requests.get(article_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Method 1: Look for WordPress featured image in meta tags
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image and 'content' in og_image.attrs:
            image_url = og_image['content']
            # Verify it's a WordPress media URL
            if '/wp-content/uploads/' in image_url:
                return image_url
        
        # Method 2: Look for WordPress image URL pattern in all image sources
        wp_images = []
        for img in soup.find_all('img'):
            if img.get('src') and '/wp-content/uploads/' in img['src']:
                wp_images.append(img['src'])
        
        if wp_images:
            # Sort by apparent image size/quality (prefer larger images)
            # WordPress often includes size parameters in URLs like ?w=1200
            def get_image_size(url):
                # Check for resize parameter
                resize_match = re.search(r'resize=(\d+),(\d+)', url)
                if resize_match:
                    width = int(resize_match.group(1))
                    return width
                
                # Check for width parameter
                width_match = re.search(r'[?&]w=(\d+)', url)
                if width_match:
                    return int(width_match.group(1))
                
                # No size info, assume it's original size (high quality)
                return 2000  # Arbitrary high number to prioritize original images
            
            # Sort images by presumed size, largest first
            wp_images.sort(key=get_image_size, reverse=True)
            return wp_images[0]
        
        # Method 3: Check for featured image div with inline style containing background-image
        for div in soup.select('[class*="featured"], [class*="hero"], [class*="image"]'):
            style = div.get('style', '')
            url_match = re.search(r'background-image:\s*url\([\'"]?([^\'"]+)[\'"]?\)', style)
            if url_match and '/wp-content/uploads/' in url_match.group(1):
                return url_match.group(1)
        
        # Method 4: Look for any data attributes that might contain image URLs
        for elem in soup.select('[data-image], [data-src], [data-lazy-src]'):
            for attr in ['data-image', 'data-src', 'data-lazy-src']:
                if elem.has_attr(attr) and '/wp-content/uploads/' in elem[attr]:
                    return elem[attr]
        
        # Method 5: Check for image JSON data in the page
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            if script.string:
                # Look for image URLs in the JSON data
                wp_url_matches = re.findall(r'https?://techcrunch\.com/wp-content/uploads/[^"\']+', script.string)
                if wp_url_matches:
                    return wp_url_matches[0]
        
        # Method 6: Fallback to any WordPress media URL on the page
        all_wp_urls = re.findall(r'https?://techcrunch\.com/wp-content/uploads/[^"\']+', response.text)
        if all_wp_urls:
            return all_wp_urls[0]
            
        # Method 7: Last resort - check for Twitter image which is often the featured image
        twitter_image = soup.select_one('meta[name="twitter:image"]')
        if twitter_image and 'content' in twitter_image.attrs:
            return twitter_image['content']
        
        return None
    except Exception as e:
        print(f"Error scraping image from TechCrunch article {article_url}: {e}")
        return None

@cache.memoize(timeout=600)
def fetch_news(feed_url, category_name):
    try:
        response = requests.get(feed_url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        feed = feedparser.parse(response.text)
        if not feed.entries:
            print(f"No entries found for {category_name}")
            return []

        articles = []
        for entry in feed.entries[:15]:  # Limit to the latest 15 articles
            # Get the image directly from the article page
            image_url = get_techcrunch_image(entry.link)
            
            # Extract other article information
            description_text = ""
            if hasattr(entry, 'description'):
                description_text = clean_html(entry.description)
            elif hasattr(entry, 'summary'):
                description_text = clean_html(entry.summary)
            
            formatted_date = "No date"
            if hasattr(entry, 'published'):
                formatted_date = format_date(entry.published)
            elif hasattr(entry, 'updated'):
                formatted_date = format_date(entry.updated)
            
            # Extract categories/tags
            category_names = []
            if hasattr(entry, 'tags'):
                category_names = [tag.term for tag in entry.tags if hasattr(tag, 'term')]
            
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "description": description_text or "No description available",
                "author": entry.get("author", "Unknown Author"),
                "published": formatted_date,
                "image": image_url,  # This will be the WordPress image URL or None
                "topics": category_names,
                "category": category_name,
                "source": "TechCrunch"
            })

        return articles
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {category_name} news: {e}")
        return []
@cache.memoize(timeout=3600)  # Cache for 1 hour
def get_full_article_content(article_url):
    """
    Scrape the full article content from a TechCrunch article
    """
    try:
        response = requests.get(article_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get the featured image
        featured_image = get_techcrunch_image(article_url)
        
        # Find the article content container
        article_content = soup.select_one('div.article-content')
        
        if not article_content:
            # Try alternative selectors if the main one fails
            article_content = soup.select_one('.post-content, .entry-content, article')
        
        if not article_content:
            return {
                "success": False,
                "message": "Could not find article content",
                "featured_image": featured_image
            }
        
        # Extract and process all images in the article
        images = []
        for img in article_content.find_all('img'):
            if 'src' in img.attrs:
                img_url = img['src']
                # Make sure URL is absolute
                if not img_url.startswith(('http://', 'https://')):
                    img_url = urljoin(article_url, img_url)
                
                # Save image info
                alt_text = img.get('alt', '')
                images.append({
                    "url": img_url,
                    "alt": alt_text
                })
        
        # Get all paragraphs of text
        paragraphs = []
        for p in article_content.find_all(['p', 'h2', 'h3', 'h4', 'blockquote']):
            # Remove any script or style elements
            for script in p.find_all(['script', 'style']):
                script.decompose()
                
            # Get the text content
            text = p.get_text().strip()
            if text:
                # Determine the type of element
                tag_type = p.name
                paragraphs.append({
                    "type": tag_type,
                    "content": text
                })
        
        # Extract any embedded tweets or social media content
        embeds = []
        for embed in article_content.select('.embed, iframe, twitterwidget, blockquote.twitter-tweet'):
            embed_html = str(embed)
            embeds.append(embed_html)
        
        # Get author info if available
        author_element = soup.select_one('.article__byline a, .byline-link')
        author = author_element.get_text() if author_element else "Unknown Author"
        
        # Get publication date if available
        date_element = soup.select_one('time, .article__byline time, .byline-timestamp')
        pub_date = date_element.get('datetime') if date_element and date_element.has_attr('datetime') else None
        
        # Structure the complete article data
        article_data = {
            "success": True,
            "title": soup.title.string if soup.title else "",
            "featured_image": featured_image,
            "author": author,
            "published_date": pub_date,
            "content": paragraphs,
            "images": images,
            "embeds": embeds
        }
        
        return article_data
        
    except Exception as e:
        print(f"Error extracting full article from {article_url}: {e}")
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "featured_image": get_techcrunch_image(article_url)
        }

# Add this new route to your Flask app
@app.route("/api/article", methods=["GET"])
@cache.cached(timeout=1800)  # Cache for 30 minutes
def get_article():
    article_url = request.args.get('url')
    if not article_url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Validate the URL is from TechCrunch
    if not article_url.startswith('https://techcrunch.com/'):
        return jsonify({"error": "Only TechCrunch URLs are supported"}), 400
    
    article_data = get_full_article_content(article_url)
    return jsonify(article_data)

@app.route("/api/techcrunch", methods=["GET"])
@cache.cached(timeout=300)
def get_techcrunch_news():
    news = []
    all_topics = set()

    for category, url in RSS_FEEDS.items():
        category_news = fetch_news(url, category)
        news.extend(category_news)

        for article in category_news:
            all_topics.update(article["topics"])

    return jsonify({"news": news, "topics": list(all_topics)})

@app.route("/api/latest-news", methods=["GET"])
@cache.cached(timeout=300)
def get_latest_news():
    all_articles = []

    for category, url in RSS_FEEDS.items():
        category_articles = fetch_news(url, category)
        all_articles.extend(category_articles)

    sorted_articles = sorted(
        all_articles,
        key=lambda x: x["published"],
        reverse=True
    )

    latest_articles = sorted_articles[:10]

    return jsonify({"latest": latest_articles})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
