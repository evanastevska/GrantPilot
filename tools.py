import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


def search_web(query: str) -> str:
    """Search the web using Serper and return top results."""
    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": os.environ["SERPER_API_KEY"]},
            json={"q": query, "num": 5},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        results = []

        #answer box (sometimes Google gets a direct answer)
        if "answerBox" in data:
            results.append(f"Direct answer: {data['answerBox'].get('answer') or data['answerBox'].get('snippet', '')}")

        #organic results
        for item in data.get("organic", []):
            results.append(
                f"Title: {item['title']}\n"
                f"URL: {item['link']}\n"
                f"Snippet: {item['snippet']}"
            )

        return "\n\n".join(results) if results else "No results found."

    except Exception as e:
        return f"Search error: {str(e)}"


def read_url(url: str) -> str:
    """Fetch a URL and return its text content, stripped of HTML."""
    try:
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; research-bot/1.0)'
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for tag in soup(['script', 'style', 'nav', 'footer']):
            tag.decompose()

        text = soup.get_text(separator=' ', strip=True)

        words = text.split()
        if len(words) > 3000:
            text = ' '.join(words[:3000]) + '\n[page truncated]'

        return text

    except Exception as e:
        return f"Error fetching URL: {str(e)}"