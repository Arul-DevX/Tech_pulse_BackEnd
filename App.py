from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Ars Technica URLs
ARS_TECHNICA_URLS = {
    "AI": "https://arstechnica.com/ai/",
    "IT":"https://arstechnica.com/information-technology/",
    "Cars": "https://arstechnica.com/cars/",
    "Culture": "https://arstechnica.com/culture/",
    "Gaming": "https://arstechnica.com/gaming/",
    "Health": "https://arstechnica.com/health/",
    "Policy": "https://arstechnica.com/tech-policy/",
    "Science": "https://arstechnica.com/science/",
    "Security": "https://arstechnica.com/security/",
    "Business": "https://arstechnica.com/business/",
    "Space": "https://arstechnica.com/science/space/",
    "Gadgets": "https://arstechnica.com/gadgets/"
}

# Set user-agent to bypass bot protection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape_ars_technica(url):
    """Scrape news articles from an Ars Technica category page."""
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"⚠️ Failed to fetch: {url} (Status: {response.status_code})")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        articles = []

        # 🔹 Inspect the page source to get the correct class
        for article in soup.find_all("article"):  # Updated selector
            title_tag = article.find("a")
            summary_tag = article.find("p")
            image_tag = article.find("img")

            if title_tag:
                title = title_tag.text.strip()
                link = title_tag["href"]
                summary = summary_tag.text.strip() if summary_tag else "No Summary"
                image = image_tag["src"] if image_tag else "https://via.placeholder.com/300"

                articles.append({
                    "title": title,
                    "summary": summary,
                    "image": image,
                    "url": link
                })

        return articles[:30]  # Get only the latest 5 articles

    except Exception as e:
        print(f"❌ Error scraping {url}: {e}")
        return []

@app.route("/news/all", methods=["GET"])
def get_all_news():
    """Fetch news from multiple Ars Technica sections."""
    all_news = {}

    for category, url in ARS_TECHNICA_URLS.items():
        articles = scrape_ars_technica(url)
        if articles:
            all_news[category] = articles
        else:
            all_news[category] = [{"error": "No news available"}]

    return jsonify(all_news)

if __name__ == "__main__":
    app.run(debug=True)
