import requests
from bs4 import BeautifulSoup

def read_url(url: str) -> str:
    """Fetch a URL and return its text content, stripped of HTML."""
    try:
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; research-bot/1.0)'
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        #remove script and style tags, want only want readable text
        for tag in soup(['script', 'style', 'nav', 'footer']):
            tag.decompose()

        text = soup.get_text(separator=' ', strip=True)

        #trim to ~3000 words for context
        words = text.split()
        if len(words) > 3000:
            text = ' '.join(words[:3000]) + '\n[page truncated]'

        return text

    except Exception as e:
        return f"Error fetching URL: {str(e)}"