# Conversation Ledger Streamlit app

This folder is the isolated canonical application surface for YouTube conversation analysis.

Install the app dependencies from this folder:

```bash
../.venv/bin/python -m pip install -r requirements.txt
```

Run it from this folder so Streamlit loads the adjacent `.streamlit/config.toml`:

```bash
cd /Users/infinityfoundation/Code/yt_transcript_scraping/streamlit_app
../.venv/bin/streamlit run streamlit_app.py
```

The local run store is `.conversation_runs/`. It is intentionally outside
Streamlit session state and is ignored by Git. The app accepts live-chat replay
and comments through `scrape_youtube_live_chat.py`, or CSV/JSON/JSONL imports.

When `GEMINI_API_KEY` is supplied through Streamlit secrets or the environment,
new live/imported runs automatically send up to 500 non-synthetic records to
Gemini Flash in batches of 40 for category/subcategory suggestions. Missing
keys, provider failures, and malformed responses fall back to deterministic
classification; manual corrections are never overwritten. Short, high-confidence
greetings, blessings, thanks, and wishes remain in the run but are excluded from
the AI payload to save tokens; substantive messages still go to Gemini.

Run the isolated tests from the repository root:

```bash
./.venv/bin/python -m unittest discover -s streamlit_app/tests -v
```
