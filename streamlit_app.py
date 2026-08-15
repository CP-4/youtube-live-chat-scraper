"""Streamlit interface for downloading an auditable YouTube live-chat CSV."""

from pathlib import Path
from collections import Counter

import streamlit as st

from scrape_youtube_live_chat import VIDEO_URL, extract_combined


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
    [data-testid="stSidebar"] [data-testid="stNumberInput"] button {
        background: #fff !important;
        color: var(--ink) !important;
        border-color: #cfc3b5 !important;
    }
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


def run_extraction(video_url: str, output_name: str, include_chat: bool,
                   include_comments: bool, max_comments: int):
    progress = st.progress(0, text="Opening YouTube page…")
    status = st.empty()

    def update(stage: str, page_count: int, record_count: int):
        label = "Reading live-chat replay" if stage == "chat" else "Retrieving video comments"
        detail = f"Page {page_count:,}" if stage == "chat" else "yt-dlp response received"
        progress.progress(0, text=f"{label} · {record_count:,} records captured")
        status.markdown(
            f'<div class="status-strip"><div class="status-label">Live extraction</div>'
            f'<strong>{detail}</strong> · {record_count:,} records captured</div>',
            unsafe_allow_html=True,
        )

    rows, issues = extract_combined(
        video_url.strip(), Path(output_name),
        include_chat=include_chat,
        include_comments=include_comments,
        max_comments=max_comments or None,
        progress_callback=update,
    )
    progress.progress(100, text=f"Complete · {len(rows):,} records")
    status.success(f"Wrote {len(rows):,} records to `{output_name}`.")
    return rows, issues


def normalize_output_name(output_name: str) -> str:
    output_name = output_name.strip()
    if not output_name:
        raise ValueError("Choose an output filename.")
    if Path(output_name).name != output_name:
        raise ValueError("Output filename must be a filename, not a directory path.")
    return output_name if output_name.lower().endswith(".csv") else f"{output_name}.csv"


st.title("YouTube conversation extractor")
st.markdown(
    '<p class="lede">Bring post-video comments and live-chat replay into one auditable CSV. Every row is labelled <code>comment</code> or <code>chat</code>, with source-specific metadata preserved.</p>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Capture settings")
    st.caption("The replay must be publicly accessible and have live-chat replay available.")
    with st.form("capture_form"):
        video_url = st.text_input("YouTube video URL", value=VIDEO_URL)
        output_name = st.text_input("Output filename", value="youtube_conversation.csv")
        include_comments = st.checkbox("Include video comments", value=True)
        max_comments = st.number_input("Max comments (0 = all)", min_value=0, value=0, step=100)
        include_chat = st.checkbox("Include live-chat replay", value=True)
        submitted = st.form_submit_button("Extract conversation", type="primary", use_container_width=True)
    st.divider()
    st.caption("The combined CSV adds source_type plus comment likes, parent IDs, and uploader flags.")

if submitted:
    try:
        output_name = normalize_output_name(output_name)
        if not include_comments and not include_chat:
            raise ValueError("Select at least one source to extract.")
        st.session_state.pop("rows", None)
        rows, issues = run_extraction(
            video_url, output_name, include_chat, include_comments, max_comments
        )
        st.session_state["rows"] = rows
        st.session_state["issues"] = issues
        st.session_state["output_name"] = output_name
    except Exception as exc:
        st.error(f"Extraction failed: {exc}")

rows = st.session_state.get("rows")
if rows is not None:
    output_name = st.session_state["output_name"]
    counts = Counter(row["source_type"] for row in rows)
    st.subheader("Captured records")
    st.write(
        f"{len(rows):,} records · {counts.get('comment', 0):,} comments · "
        f"{counts.get('chat', 0):,} chat messages"
    )
    for issue in st.session_state.get("issues", []):
        st.warning(f"Partial extraction: {issue}")
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
    st.info("Choose one or both sources in the sidebar, then start an extraction to preview and download the combined CSV.")
