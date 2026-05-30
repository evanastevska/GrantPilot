# GrantPilot

An internal tool I built during my AI/ML internship at Cinema Verde, a nonprofit 
environmental film festival in Gainesville, Florida. The team has no dedicated  
grant writer, so I built an AI agent to help automate the process.

You paste in a grant opportunity, and the agent researches the funder and writes a complete grant application tailored to them. The tool then 
drops a formatted Google Doc in the organization's shared Drive folder.

**Live deployment:** https://cinemaverde-grant-agent-283276831935.us-central1.run.app/  
*Internal tool (restricted to Cinema Verde staff).*

---

## What it does

1. Searches the web for information about the funder using Serper
2. Reads relevant pages to understand their priorities and eligibility requirements
3. Flags potential mismatches between the funder and Cinema Verde
4. Writes all nine grant sections tailored to that specific funder
5. Creates a Google Doc, saves it to Cinema Verde's shared Drive folder, and 
   shares it with whoever submitted the form

The whole process takes 2–5 minutes. A live progress log streams updates to the 
browser while the agent runs.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| LLM | Gemini 2.5 Flash — native function calling |
| Agent architecture | Custom ReAct loop — no LangChain |
| Web search | Serper API |
| Web server | Flask + Gunicorn |
| Streaming | Server-Sent Events (SSE) |
| Docs integration | Google Docs API + Drive API (OAuth2) |
| Hosting | Google Cloud Run |
| Secrets | Google Cloud Secret Manager |

---

## Running locally

### Prerequisites

- Python 3.11+
- Gemini API key (Google AI Studio)
- Serper API key (serper.dev)
- Google Cloud project with Docs API and Drive API enabled

### Setup

```bash
git clone https://github.com/yourusername/grantpilot
cd grantpilot

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Create a `.env` file:

```env
GEMINI_API_KEY=your_gemini_key
SERPER_API_KEY=your_serper_key
GOOGLE_DRIVE_FOLDER_ID=your_drive_folder_id
APP_PASSWORD=your_password
```

Run the OAuth authorization flow once to generate `token.json`:

```bash
python authorize.py
```

Start the server:

```bash
python app.py
```

Go to `http://localhost:5000`.

> `token.json` and `oauth_credentials.json` are excluded via `.gitignore`. 
> You will need to set up your own Google Cloud project and run the 
> authorization flow to generate them.

---

## Deploying to Cloud Run

```bash
docker build -t gcr.io/YOUR_PROJECT_ID/grant-agent .
docker push gcr.io/YOUR_PROJECT_ID/grant-agent

gcloud run deploy grant-agent \
  --image gcr.io/YOUR_PROJECT_ID/grant-agent \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --timeout 600 \
  --memory 512Mi \
  --update-secrets="GEMINI_API_KEY=gemini-api-key:latest,SERPER_API_KEY=serper-api-key:latest,GOOGLE_DRIVE_FOLDER_ID=google-drive-folder-id:latest,APP_PASSWORD=app-password:latest,/secrets/token.json=token-json:latest" \
  --set-env-vars="TOKEN_PATH=/secrets/token.json"
```
