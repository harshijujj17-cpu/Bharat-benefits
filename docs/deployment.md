# Deployment — Bharat Benefit Navigator

## Architecture

- **Frontend**: React + Vite, built to static files (`frontend/dist`), served as a static site.
- **Backend**: FastAPI (`api.main:app`) served by uvicorn as a persistent web service.
- **AI**: Configured LLM provider (Gemini by default, or OpenAI-compatible via env).
- **Retrieval**: Live Tavily web search at request time. No static scheme data, no cache.

## Environment variables (names only — never commit values)

Backend:
- `GEMINI_API_KEY`
- `TAVILY_API_KEY`
- `GEMINI_MODEL` (optional)
- `GEMINI_FALLBACK_MODELS` (optional)
- `LLM_PROVIDER` (optional: `gemini` default, or `openai_compatible`)
- `LLM_MODEL`, `LLM_FALLBACK_MODELS`, `LLM_API_KEY`, `LLM_BASE_URL` (optional)
- `CORS_ORIGINS` — comma-separated allowed frontend origins (set to your deployed frontend URL)
- `RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` (optional)

Frontend build:
- `VITE_API_URL` — public URL of the deployed FastAPI backend (used at `npm run build` time)

## Build & start commands

Backend:
```bash
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

Frontend:
```bash
cd frontend
VITE_API_URL=https://<your-backend-url> npm run build
# serve frontend/dist with any static host
```

## How to deploy on Render (this repo's render.yaml)

1. Create a new Render Blueprint from this repo (or set a Web Service manually).
2. Set the secret env vars listed above (`GEMINI_API_KEY`, `TAVILY_API_KEY`, `CORS_ORIGINS=https://<your-frontend>`).
3. Deploy the backend; note its URL.
4. Build the frontend with `VITE_API_URL=https://<your-backend-url>` and publish `frontend/dist` (Render Static Site, Netlify, etc.).
5. Go back and set the backend `CORS_ORIGINS` to the exact frontend origin, then redeploy backend.

## Redeploy

- Backend: push to the connected repo or click "Redeploy" in Render.
- Frontend: rebuild with the same `VITE_API_URL` and republish `frontend/dist`.

## Run locally

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev
```

## Health checks

- `GET /health` must return `"status": "ok"` before running nationwide QA.
- `python qa/provider_smoke.py` verifies LLM provider reachability, model, quota, and structured response.

## Known limitations

- Free-tier provider quotas (Gemini/Tavily) can be exhausted; errors surface as structured `provider_quota_exhausted`/`provider_upstream_error` — never fabricated results.
- Do not run the 540-case nationwide QA during a live demo.
