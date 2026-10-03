# SevaSetu AI 🏛️
### National Government Scheme Intelligence — Powered by Gemini + ChromaDB

> A conversational AI agent that helps Indian citizens discover government welfare schemes they are eligible for, based on their personal profile.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://your-app.streamlit.app)

---

## ✨ Features

- 🗣️ **Voice Input** — Describe your profile by speaking
- 🤖 **AI Profile Extraction** — Gemini extracts structured data from free-form text
- 🔍 **Semantic Search** — ChromaDB + Gemini Embeddings retrieve the most relevant schemes
- 📋 **Eligibility Analysis** — Gemini explains why each scheme matches your profile
- 📄 **Document Checklist** — Lists required documents for each scheme
- 🌐 **Multilingual Ready** — Supports regional language speech input

## 🏗️ Architecture

```
User Input (text / voice)
       ↓
Profile Extractor (Gemini)
       ↓
ChromaDB Semantic Retrieval
       ↓
Eligibility Checker (Gemini)
       ↓
Scheme Recommendations + Documents
```

## 🚀 Deploy to Streamlit Cloud

1. **Fork this repo** on GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo, branch `main`, and set **Main file path** to `app.py`
4. Under **Advanced settings → Secrets**, add:
   ```toml
   GEMINI_API_KEY = "your-gemini-api-key-here"
   ```
5. Click **Deploy** — ChromaDB will auto-build on first startup (~60 seconds)

## 💻 Run Locally

```bash
# 1. Clone the repo
git clone https://github.com/your-username/scheme-welfare-agent.git
cd scheme-welfare-agent/Government-Scheme-Agent

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your API key
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 5. Run the app
streamlit run app.py
```

## 🔑 Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Your Google Gemini API key ([get one here](https://aistudio.google.com/app/apikey)) |
| `GEMINI_MODEL` | Optional — override the default model (default: `gemini-3.5-pro`) |

## 📁 Project Structure

```
Government-Scheme-Agent/
├── app.py                    # Streamlit frontend
├── agent/
│   ├── agent_loop.py         # Agentic tool-calling loop (Gemini)
│   ├── profile_extractor.py  # Free-text → structured profile
│   ├── recommendation.py     # Gemini-grounded eligibility analysis
│   ├── prompts.py            # System prompts & response schemas
│   ├── tools.py              # Tool implementations
│   └── secrets.py            # API key resolver (cloud + local)
├── rag/
│   ├── retriever.py          # ChromaDB retrieval
│   └── embeddings.py         # Gemini embedding helpers
├── data/
│   └── schemes.json          # Government scheme database
├── voice/
│   ├── speech_to_text.py     # Speech recognition
│   └── text_to_speech.py     # TTS output
└── .streamlit/
    └── config.toml           # Streamlit theme config
```

## 📊 Tested Profiles

The agent has been tested against 12 diverse Telangana citizen profiles covering:
- School & college students (OBC/SC)
- Farmers (OBC/SC/General)
- Senior citizens & retirees
- Women entrepreneurs
- Persons with disabilities
- Homemakers

**Result: 12/12 profiles successfully matched to relevant schemes.**

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.