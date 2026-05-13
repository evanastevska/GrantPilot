import requests

def search_web(query: str) -> str:
    """
    Search the web using Google Search grounding via the Gemini API.
    Returns a summary of search results as a string.
    Note: actual grounding is handled inside the Gemini API call in agent.py,
    not as a standalone HTTP request. This function is a placeholder for
    any supplemental direct fetching we need.
    """

    pass


def read_url(url: str) -> str:
    """
    Fetch a URL and return its text content, stripped of HTML tags.
    Used by the agent to read funder websites, grant pages, etc.
    """

    pass