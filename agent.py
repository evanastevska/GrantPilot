import os
import queue
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.environ['GEMINI_API_KEY'])

CINEMA_VERDE_CONTEXT = """
Cinema Verde is a 501(c)(3) nonprofit environmental film festival based in
Gainesville, Florida. Mission: environmental education and advocacy through
the art of film. Programs include an annual film festival, year-round
screenings, environmental education initiatives, and community partnerships
with local schools and conservation groups. Audience: students, educators,
environmentalists, and the general public in North Central Florida.
Website: cinemaverde.org
"""

GRANT_SECTIONS = [
    "Executive Summary",
    "Organization Background",
    "Statement of Need",
    "Project Description",
    "Goals and Objectives",
    "Evaluation Plan",
    "Budget Narrative",
    "Conclusion",
    "Notes for Reviewer",
]


def run_agent(grant_input: str, recipient_email: str, q: queue.Queue):
    """
    Main agent entry point. Called in a background thread by app.py.
    Runs the ReAct loop and puts progress messages into q.
    When done, puts 'DONE:<doc_url>' or 'ERROR:<message>' into q.
    """

    q.put("Agent starting... (not yet implemented)")
    q.put("DONE:https://placeholder-url.com")