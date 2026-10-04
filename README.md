# SevaSetu AI — Government Scheme Recommendation API

Live recommendation service for **current** Indian government schemes.

The API does **not** store schemes in JSON, CSV, SQLite, ChromaDB, or any other local dataset. When a citizen profile is submitted, the service searches the public web (Tavily), prefers official `.gov.in` / `.nic.in` / MyScheme pages, extracts facts with Gemini, and matches eligibility for that request only.

## Architecture

```
User
 ↓
FastAPI (`POST /recommend`, `GET /schemes/search`)
 ↓
AI scheme agent (Gemini)
 ↓
Live Tavily web search (request time)
 ↓
Official government sources
 ↓
Extract current scheme information
 ↓
Eligibility matching against the profile
 ↓
JSON response (in-memory only)
```

## Secrets

Copy `.env.example` to `.env` and fill in keys. Do not commit `.env`.

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | yes | Google Gemini API key |
| `TAVILY_API_KEY` | yes | Tavily search API key |
| `GEMINI_MODEL` | no | Override model (default `gemini-3.1-flash-lite`) |

Get a Gemini key at [Google AI Studio](https://aistudio.google.com/app/apikey). Get a Tavily key at [tavily.com](https://tavily.com).

## Run locally

From `Government-Scheme-Agent/`:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux
# edit .env and add GEMINI_API_KEY and TAVILY_API_KEY

uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Open docs at `http://127.0.0.1:8000/docs`.

## Example curl requests

```bash
curl -s http://127.0.0.1:8000/health

curl -s -X POST http://127.0.0.1:8000/recommend ^
  -H "Content-Type: application/json" ^
  -d "{\"age\":20,\"education\":\"B.Tech\",\"state\":\"Telangana\",\"category\":\"OBC\",\"annual_income\":250000}"

curl -s "http://127.0.0.1:8000/schemes/search?q=scholarships+for+OBC+students"
```

macOS / Linux:

```bash
curl -s -X POST http://127.0.0.1:8000/recommend \
  -H "Content-Type: application/json" \
  -d '{"age":20,"education":"B.Tech","state":"Telangana","category":"OBC","annual_income":250000}'
```

## Example response shape

```json
{
  "recommendations": [
    {
      "scheme_name": "Post Matric Scholarship for OBC Students",
      "government_department": "Ministry of Social Justice and Empowerment",
      "description": "...",
      "eligibility": "...",
      "benefits": "...",
      "application_process": "...",
      "application_url": "https://scholarships.gov.in",
      "official_source_url": "https://www.myscheme.gov.in/schemes/...",
      "important_dates": null,
      "relevance_explanation": "Relevant because the profile is an OBC B.Tech student in Telangana with income within the published ceiling.",
      "eligibility_status": "relevant",
      "missing_information": [],
      "source_verification": {
        "is_official_government_source": true,
        "domain": "myscheme.gov.in",
        "tier": "official"
      },
      "eligibility_notice": "Based on the information provided, this scheme may be relevant to you. Please verify the latest eligibility criteria and application details on the official government portal before applying."
    }
  ],
  "notice": null,
  "retrieval": {
    "mode": "live_web_search",
    "provider": "tavily",
    "cached": false,
    "queries": ["site:myscheme.gov.in Telangana OBC B.Tech ..."],
    "result_count": 8,
    "official_result_count": 6,
    "source_urls": ["https://www.myscheme.gov.in/..."]
  }
}
```

Exact scheme names and URLs change with live search. The service never invents URLs: every `official_source_url` must appear in that request's Tavily hits.

If live search fails, the API returns HTTP 503 and **does not** fall back to a local scheme list.

## How to verify retrieval is live

1. `GET /health` includes `"stores_schemes": false`.
2. Every successful response includes `"retrieval": {"mode": "live_web_search", "provider": "tavily", "cached": false}`.
3. `source_urls` are pages fetched for that request.
4. There is no `data/schemes.json` and no Chroma collection.
5. Repeat the same profile later: newly published official pages can appear because nothing is cached on disk.

## Tests

```bash
pytest -q
```

Tests cover Telangana B.Tech OBC, female student, General category, and high-income profiles. They assert live search is called, official sources are ranked first, ungrounded/hallucinated URLs are dropped, and API payloads are JSON.

## Deploy

This is a normal ASGI backend.

**Render / Railway / Fly.io:** set `GEMINI_API_KEY` and `TAVILY_API_KEY`, start with:

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

`render.yaml` and `Procfile` are included. Docker:

```bash
docker build -t scheme-api .
docker run -p 8000:8000 --env-file .env scheme-api
```

Free-tier notes: live search + Gemini run per request, so cold starts and rate limits depend on Tavily and Gemini quotas.

## Project structure

```
Government-Scheme-Agent/
├── api/main.py                 # FastAPI app
├── agent/
│   ├── pipeline.py             # recommend + live search orchestration
│   ├── agent_loop.py           # Gemini tool-calling loop (live retriever)
│   ├── profile_extractor.py    # free-text → structured profile
│   ├── recommendation.py       # Gemini eligibility explanations
│   ├── scheme_extractor.py     # extract facts from search hits
│   └── secrets.py              # GEMINI_API_KEY / TAVILY_API_KEY
├── rag/
│   ├── live_retriever.py       # Tavily request-time search
│   └── official_sources.py     # .gov.in / .nic.in ranking
├── tests/
├── .env.example
├── Dockerfile
└── requirements.txt
```

Voice helpers under `voice/` are unchanged and unused by the API.
