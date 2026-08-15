"""Streamlit interface for downloading an auditable YouTube live-chat CSV."""

from pathlib import Path

import streamlit as st

from scrape_youtube_live_chat import VIDEO_URL, extract


st.set_page_config(
    page_title="YouTube Live Chat Extractor",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --ink: #17212b; --muted: #5d6b78; --accent: #d95f39; --wash: #f4efe8; }
    .stApp { background: #fbfaf8; color: var(--ink); }
    [data-testid="stSidebar"] { background: var(--wash); border-right: 1px solid #e2d9ce; }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--ink) !important; }
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color: var(--ink) !important; font-weight: 650; }
    [data-testid="stSidebar"] input {
        background: #fff !important;
        color: var(--ink) !important;
        border: 1px solid #cfc3b5 !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] input:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 1px var(--accent) !important; }
    h1 { letter-spacing: -0.04em; font-size: clamp(2.2rem, 5vw, 4.2rem); line-height: .98; }
    h2, h3 { letter-spacing: -0.025em; }
    .lede { color: var(--muted); font-size: 1.1rem; max-width: 45rem; line-height: 1.55; }
    .status-strip { border: 1px solid #e2d9ce; background: #fff; padding: 1rem 1.15rem; border-radius: 12px; }
    .status-label { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }
    div.stButton > button[kind="primary"] { background: var(--accent); border-color: var(--accent); color: #fff; }
    </style>
    """,
    unsafe_allow_html=True,
)


def run_extraction(video_url: str, output_name: str):
    progress = st.progress(0, text="Opening YouTube page…")
    status = st.empty()

    def update(page_count: int, record_count: int):
        # The replay API does not expose a total page count, so use an indeterminate
        # progress bar and make the durable count the primary signal.
        progress.progress(0, text=f"Reading replay pages · {record_count:,} records captured")
        status.markdown(
            f'<div class="status-strip"><div class="status-label">Live extraction</div>'
            f'<strong>Page {page_count:,}</strong> · {record_count:,} records captured</div>',
            unsafe_allow_html=True,
        )

    rows = extract(video_url.strip(), Path(output_name), progress_callback=update)
    progress.progress(100, text=f"Complete · {len(rows):,} records")
    status.success(f"Wrote {len(rows):,} records to `{output_name}`.")
    return rows


def normalize_output_name(output_name: str) -> str:
    output_name = output_name.strip()
    if not output_name:
        raise ValueError("Choose an output filename.")
    if Path(output_name).name != output_name:
        raise ValueError("Output filename must be a filename, not a directory path.")
    return output_name if output_name.lower().endswith(".csv") else f"{output_name}.csv"


st.title("YouTube live-chat extractor")
st.markdown(
    '<p class="lede">Capture a live-chat replay into a flat, auditable CSV — with message metadata, timestamps, badges, purchases, and the original renderer JSON preserved.</p>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Capture settings")
    st.caption("The replay must be publicly accessible and have live-chat replay available.")
    with st.form("capture_form"):
        video_url = st.text_input("YouTube video URL", value=VIDEO_URL)
        output_name = st.text_input("Output filename", value="livechat.csv")
        submitted = st.form_submit_button("Extract live chat", type="primary", use_container_width=True)
    st.divider()
    st.caption("Output keeps the original 18-column schema from the command-line extractor.")

if submitted:
    try:
        output_name = normalize_output_name(output_name)
        st.session_state.pop("rows", None)
        st.session_state["rows"] = run_extraction(video_url, output_name)
        st.session_state["output_name"] = output_name
    except Exception as exc:
        st.error(f"Extraction failed: {exc}")

rows = st.session_state.get("rows")
if rows is not None:
    output_name = st.session_state["output_name"]
    st.subheader("Captured records")
    st.write(f"{len(rows):,} records · sorted by video offset")
    st.dataframe(rows[:200], use_container_width=True, hide_index=True)
    csv_path = Path(output_name)
    if csv_path.exists():
        st.download_button(
            "Download CSV",
            data=csv_path.read_bytes(),
            file_name=csv_path.name,
            mime="text/csv",
            type="primary",
        )
else:
    st.info("Choose a video in the sidebar, then start an extraction to preview and download the CSV.")
