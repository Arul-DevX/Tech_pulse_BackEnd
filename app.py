from flask import Flask, jsonify, request
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

@cache.memoize(timeout=3600)  # Cache for 1 hour
def get_article_content(article_url, content_percentage=100):
    """
    Scrape the article content from TechCrunch and return the specified percentage
    """
    try:
        response = requests.get(article_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the article content container
        article_content = soup.select_one('.article-content')
        
        if not article_content:
            # Try alternative selectors for article content
            article_content = soup.select_one('article .post-block')
            
        if not article_content:
            # Another alternative
            article_content = soup.select_one('.entry-content')
            
        if not article_content:
            # If we still can't find the content, get the main article element
            article_content = soup.select_one('article')
        
        if not article_content:
            return {
                "error": "Could not extract article content",
                "content_html": "",
                "content_text": ""
            }
        
        # Remove unwanted elements like related articles, ads, etc.
        for unwanted in article_content.select('.related-articles, .advertisement, .ad-zone, .share-block, .footer, .tags, .wp-block-latest-posts'):
            unwanted.decompose()
        
        # Process images to ensure they have absolute URLs
        for img in article_content.find_all('img'):
            if 'src' in img.attrs:
                if not img['src'].startswith(('http://', 'https://')):
                    img['src'] = urljoin(article_url, img['src'])
                # Make sure we prioritize high-res images
                if 'srcset' in img.attrs:
                    srcset = img['srcset'].split(',')
                    if srcset:
                        largest_src = srcset[-1].strip().split(' ')[0]
                        if largest_src:
                            img['src'] = largest_src
                
        # Get the full HTML content
        full_html = str(article_content)
        full_text = article_content.get_text(separator=' ', strip=True)
        
        # If we need to return only a portion of the content
        if content_percentage < 100:
            # For HTML, we'll take a percentage of the elements
            soup_content = BeautifulSoup(full_html, 'html.parser')
            all_elements = soup_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol'])
            
            # Calculate how many elements to keep
            elements_to_keep = max(1, int(len(all_elements) * (content_percentage / 100)))
            
            # Create a new soup with just the elements we want to keep
            partial_soup = BeautifulSoup('<div></div>', 'html.parser')
            for i, elem in enumerate(all_elements):
                if i < elements_to_keep:
                    partial_soup.div.append(elem)
            
            # Add a "Read more at TechCrunch" link
            read_more = soup.new_tag('p')
            read_more.string = f"Read the full article at TechCrunch: "
            
            read_more_link = soup.new_tag('a', href=article_url)
            read_more_link.string = "Continue reading..."
            read_more_link['target'] = '_blank'
            read_more_link['rel'] = 'noopener noreferrer'
            
            read_more.append(read_more_link)
            partial_soup.div.append(read_more)
            
            # For text, we'll take a percentage of the characters
            text_chars_to_keep = max(100, int(len(full_text) * (content_percentage / 100)))
            partial_text = full_text[:text_chars_to_keep] + f"... [Read more at TechCrunch]"
            
            return {
                "content_html": str(partial_soup.div),
                "content_text": partial_text
            }
        
        return {
            "content_html": full_html,
            "content_text": full_text
        }
        
    except Exception as e:
        print(f"Error scraping content from article {article_url}: {e}")
        return {
            "error": str(e),
            "content_html": "",
            "content_text": ""
        }

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

@app.route("/api/article-content", methods=["GET"])
def get_article_detail():
    """
    API endpoint to get article content at a specified percentage
    
    Query parameters:
    - url: The URL of the article to fetch
    - percentage: (Optional) Percentage of content to return (default: 100)
    """
    article_url = request.args.get('url')
    percentage = request.args.get('percentage', 100, type=int)
    
    if not article_url:
        return jsonify({"error": "Missing required parameter: url"}), 400
    
    # Validate percentage
    if percentage < 1 or percentage > 100:
        percentage = 100
    
    # Get the article content
    content = get_article_content(article_url, percentage)
    
    # Get the article image as well
    image_url = get_techcrunch_image(article_url)
    
    response = {
        "url": article_url,
        "percentage": percentage,
        "image": image_url,
        "content": content
    }
    
    return jsonify(response)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
