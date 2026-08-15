# Conversation Ledger Streamlit app

This folder is the isolated canonical application surface for YouTube conversation analysis.

Install the app dependencies from this folder:

```bash
../.venv/bin/python -m pip install -r requirements.txt
```

Use Python 3.10 or newer for this environment. The Gemini Interactions API
support in `google-genai` 2.x is not installable on Python 3.9.

Run it from this folder so Streamlit loads the adjacent `.streamlit/config.toml`:

```bash
cd /Users/infinityfoundation/Code/yt_transcript_scraping/streamlit_app
../.venv/bin/streamlit run streamlit_app.py
```

The local run store is `.conversation_runs/`. It is intentionally outside
Streamlit session state and is ignored by Git. The app accepts live-chat replay
and comments through `scrape_youtube_live_chat.py`, or CSV/JSON/JSONL imports.

Live/imported runs use the deterministic classifier by default. It records
auditable message signals (length, word count, question marks, emoji, mentions,
URLs, confidence, and the matched rule) and is tuned for the Hindi/English
conversation patterns in the Ghoomta Aaina development sample. The optional
`AI-assisted classification` checkbox sends at most 1,500 non-synthetic records to
Gemini Flash in default batches of 100, with an overall cap of 1,500. The batch
size can be raised through `GEMINI_CLASSIFICATION_BATCH_SIZE` for controlled
experiments. Each request has a 90-second timeout, progress is shown
batch-by-batch, and any provider failure falls back to deterministic
labels; manual corrections are never overwritten. Short, high-confidence
greetings, blessings, thanks, and wishes remain in the run but are excluded from
the AI payload to save tokens. The app supports both the newer `google-genai`
Interactions API and older SDKs exposing `models.generate_content`; set
`GEMINI_MODEL` through secrets, `.env`, or the environment to override the
default `gemini-2.5-flash`.

Run the isolated tests from the repository root:

```bash
./.venv/bin/python -m unittest discover -s streamlit_app/tests -v
```
