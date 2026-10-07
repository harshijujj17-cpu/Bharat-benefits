# AI-Powered Government Scheme Recommendation System for Telangana

**Subtitle:** Telangana Government Scheme Assistant

This system is an AI-powered citizen welfare navigation platform focused entirely on Telangana. It recommends Telangana State Government schemes and Central/National Government schemes applicable to Telangana citizens. Rather than simply listing government schemes, it converts a citizen's needs and profile into a personalized **benefit journey** containing potential benefits, eligibility reasoning, required documents, application steps, alternatives, and official sources.

## Problem

Most scheme-list websites make citizens do the work: guess the scheme name, search, and hope it applies to their state and situation. Lists are long, stale, and rarely explain *why* a benefit does or does not apply.

## Proposed solution

The user answers four things:

1. **What do you need help with?** — Education, Agriculture, Employment & Business, Housing, Women & Children, Senior Citizens, Disability, Healthcare, Social Security, or Other
2. **Which state?** — Telangana
3. **Who are you?** — age, gender, occupation, income, category, education, farmer/student/disability status
4. **Find My Benefits**

The app runs a live pipeline and returns a **Citizen Benefit Plan**:

- Potentially relevant benefits (never fabricated)
- Eligibility status: Likely Eligible / Possibly Eligible / Not Eligible / Need More Information
- Why the result was produced
- Required documents and missing information
- Application journey (check eligibility → prepare documents → official portal → submit → track)
- Official source URLs
- Alternatives when a benefit is not suitable
- Explicit "Why am I not eligible?" explanations

## Key innovation

NORMAL: Search → Scheme list

THIS PROJECT: Citizen situation → State → Need → Profile → Live government information → Eligibility reasoning → Documents → Alternatives → Application journey → Official sources

## Architecture

```text
React + Vite frontend
        |
        | POST /recommend, POST /clarify, POST /benefits/journey
        v
FastAPI API
        |
        +-- LLM provider abstraction (agent/llm_client.py):
        |      Gemini (default) or any OpenAI-compatible model
        |      configurable via LLM_PROVIDER / LLM_MODEL / LLM_API_KEY
        |
        +-- Tavily: live web search at request time
                    |
                    v
           Official government pages (.gov.in, .nic.in, MyScheme)
```

- No static scheme catalogue, no fabricated eligibility rules
- Official-source grounding is mandatory: a scheme URL must appear in live Tavily results
- Provider errors are explicit: `provider_quota_exhausted` (503), `provider_timeout` (504), `provider_upstream_error` (502), `internal_server_error` (500)
- Rate limiting, CORS, and `/health` are preserved

## User flow

1. Home — "What do you need help with?" (need cards) + state selector
2. Profile — age, gender, occupation, income, category, education, statuses
3. "Find My Benefits" → "Your Citizen Benefit Plan" dashboard
4. Each benefit shows eligibility status, why, conditions, documents, missing info, application steps, official source, alternatives

## State-aware behavior

The current supported scope is Telangana. If a request names a different state, the API returns: "Currently, this system is designed specifically for Telangana citizens."

## Testing & demo scope

Use Telangana profiles for recommendations, including Telangana-specific schemes and Central/National schemes applicable to Telangana citizens.

Before demos, verify providers with `python qa/provider_smoke.py` (all checks must be `yes`). Then:

```bash
# Backend
uvicorn api.main:app --port 8000

# Frontend
cd frontend && npm run dev
```

Demo scenarios: Telangana student, Telangana farmer, Telangana woman, Telangana citizen with an applicable Central Government scheme, and a non-Telangana state rejection check.

Run the full test suite with `python -m pytest -q` and the frontend build with `npm run build`.

## Limitations

- Live provider quota (Gemini/Tavily free tiers) can interrupt runs; provider errors are surfaced explicitly instead of fake results
- Eligibility is decision-support, not legal confirmation
- Scheme data quality depends on official sources' own pages

## Current Implementation

- Telangana State Government schemes
- Central Government schemes applicable to Telangana
- Live Tavily retrieval
- Official government sources
- Gemini-based extraction and processing
- State and need relevance validation
