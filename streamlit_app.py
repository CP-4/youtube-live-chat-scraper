"""Canonical Streamlit workbench for YouTube conversation analysis."""

from __future__ import annotations

import html
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

try:
    from .conversation_analyzer import (
        CATEGORIES, SOURCE_LABELS, SUBCATEGORIES, RunStore, analysis_summary,
        audience_summary, category_counts, ensure_record_ids, filter_rows, generate_sample_records,
        inferred_mapping, make_run, normalize_records, parse_import_bytes, rows_to_csv, rows_to_json,
        host_review_csv, validate_youtube_url,
    )
    from .scrape_youtube_live_chat import VIDEO_URL, extract_combined, fetch_video_metadata
except ImportError:  # Streamlit executes this file as a top-level script.
    from conversation_analyzer import (
        CATEGORIES, SOURCE_LABELS, SUBCATEGORIES, RunStore, analysis_summary,
        audience_summary, category_counts, ensure_record_ids, filter_rows, generate_sample_records,
        inferred_mapping, make_run, normalize_records, parse_import_bytes, rows_to_csv, rows_to_json,
        host_review_csv, validate_youtube_url,
    )
    from scrape_youtube_live_chat import VIDEO_URL, extract_combined, fetch_video_metadata


st.set_page_config(
    page_title="Conversation Ledger",
    page_icon="◌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Impeccable direction contract: editorial evidence ledger; source truth before
# interpretation; a dense but calm workbench; assigned seed 7b784ff2, candidate 5.
st.markdown(
    """<!--
THESIS: A source-labelled evidence ledger turns public YouTube conversation into host-ready queues, not a raw data dump.
OWN-WORLD: cool paper-white workspace, ink typography, slate panels, and one signal-orange action color with source-specific chips.
STORY: the analyst sees what was captured, what needs attention, and what can be exported without losing raw evidence.
FIRST VIEWPORT: status strip, core counts, top themes, and the next review queue sit above the fold; extraction and import stay one action away.
FORM: editorial evidence ledger, candidate 5, direction seed 7b784ff2.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
-->""",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    :root { --paper:#f5f7f8; --panel:#ffffff; --ink:#15212b; --muted:#61707a; --line:#d9e1e5; --accent:#d95d38; --accent-dark:#a94327; --chat:#2d7691; --comment:#8f5b38; --ok:#28785b; --warn:#8b5c17; }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(245,247,248,.88); }
    [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display:none !important; }
    h1,h2,h3 { color: var(--ink); letter-spacing: -0.025em; }
    h1 { font-size: 2.55rem; line-height: 1.02; margin-bottom: .35rem; }
    h2 { font-size: 1.45rem; margin-top: 1.2rem; }
    h3 { font-size: 1.08rem; }
    .lede { color: var(--muted); max-width: 58rem; font-size: 1.02rem; line-height: 1.55; }
    .eyebrow { color: var(--accent-dark); font-size: .72rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
    .status-banner { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 1rem 1.1rem; margin: .45rem 0 1rem; box-shadow: 0 2px 8px rgba(21,33,43,.04); }
    .status-title { font-size: 1.1rem; font-weight: 750; margin-bottom: .18rem; }
    .status-subtitle { color: var(--muted); font-size: .88rem; overflow-wrap: anywhere; }
    .status-grid { display:grid; grid-template-columns: repeat(5,minmax(0,1fr)); gap:.8rem; margin-top:.85rem; }
    .status-cell { border-top: 1px solid var(--line); padding-top: .55rem; }
    .status-label { color: var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; }
    .status-value { font-weight: 680; margin-top:.14rem; }
    .source-chip { display:inline-block; padding:.18rem .48rem; border-radius:999px; font-size:.74rem; font-weight:700; margin-right:.28rem; }
    .source-chat { color:#19586b; background:#e2f0f4; }
    .source-comment { color:#70421f; background:#f4e9df; }
    .source-import { color:#4c4f56; background:#e9ebee; }
    .synthetic { border:1px solid #d6a93b; color:#6b4c0d; background:#fff7dc; border-radius:999px; padding:.22rem .55rem; font-size:.75rem; font-weight:700; }
    .metric-note { color:var(--muted); font-size:.8rem; }
    .empty-panel { background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:1.45rem; min-height:12rem; }
    .queue-note { color:var(--muted); font-size:.88rem; margin-top:-.35rem; }
    .message-meta { color:var(--muted); font-size:.82rem; }
    .message-text { font-size:1.02rem; line-height:1.52; }
    .warning-box { background:#fff7df; border:1px solid #e0bd62; border-radius:10px; padding:.65rem .8rem; color:#65470d; }
    .success-box { background:#edf8f2; border:1px solid #abd6be; border-radius:10px; padding:.65rem .8rem; color:#1d6247; }
    div.stButton > button { background:#ffffff !important; color:var(--ink) !important; border:1px solid var(--line) !important; }
    div.stButton > button:hover { border-color:var(--accent) !important; color:var(--accent-dark) !important; }
    div.stButton > button[kind="primary"] { background:var(--accent); border-color:var(--accent); color:#fff; }
    div.stButton > button[kind="primary"]:hover { background:var(--accent-dark); border-color:var(--accent-dark); }
    [data-testid="stFileUploader"] section { background:#ffffff !important; border:1px dashed var(--line) !important; }
    [data-testid="stFileUploader"] section * { color:var(--ink) !important; }
    button:focus, input:focus, textarea:focus, [role="combobox"]:focus { outline:3px solid rgba(217,93,56,.35) !important; outline-offset:2px; }
    [data-testid="stMetricValue"] { font-size:1.75rem; color:var(--ink); }
    .big-text [data-testid="stMarkdownContainer"], .big-text .message-text { font-size:1.15rem !important; line-height:1.65; }
    @media (max-width: 1050px) { [data-testid="stSidebar"] { display:none; } .status-grid { grid-template-columns:1fr; } h1 { font-size:2.15rem; } }
    @media (max-width: 640px) { .status-grid { grid-template-columns:1fr; } .status-banner { padding:.8rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)


STORE = RunStore()
AI_BATCH_SIZE = 40
AI_MAX_ROWS = 500


def get_ai_key() -> str:
    try:
        secret = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        secret = ""
    return str(secret or os.environ.get("GEMINI_API_KEY", "")).strip()


def ai_generate(prompt: str) -> str:
    key = get_ai_key()
    if not key:
        raise RuntimeError("Gemini is disabled because GEMINI_API_KEY is not configured.")
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("Gemini support is not installed; install the optional AI dependency.") from exc
    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(prompt)
    return str(getattr(response, "text", "") or "").strip()


def _parse_ai_array(response: str) -> list[dict[str, Any]]:
    """Extract a JSON array from a Gemini response without trusting prose around it."""
    cleaned = response.strip().replace("```json", "").replace("```", "").strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("Gemini did not return a JSON array")
    payload = json.loads(cleaned[start:end + 1])
    return payload if isinstance(payload, list) else []


def ai_categorize_rows(rows: list[dict[str, Any]], limit: int = AI_MAX_ROWS) -> tuple[list[dict[str, Any]], int, str | None]:
    """Automatically improve deterministic categories with bounded Gemini batches.

    A missing key, missing optional dependency, provider failure, malformed
    response, or invalid suggestion leaves the deterministic row untouched.
    Manual corrections are never overwritten.
    """
    if not get_ai_key():
        return rows, 0, None
    greeting_skipped = sum(1 for row in rows if row.get("ai_excluded"))
    candidates = [
        row for row in rows
        if row.get("message") and not row.get("synthetic")
        and row.get("category_source") != "manual" and not row.get("ai_excluded")
    ][:max(0, limit)]
    if not candidates:
        if greeting_skipped:
            return rows, 0, f"Skipped {greeting_skipped:,} high-confidence greetings/wishes before AI classification."
        return rows, 0, None
    by_id = {row.get("record_id"): row for row in candidates}
    applied = 0
    try:
        for start in range(0, len(candidates), AI_BATCH_SIZE):
            batch = candidates[start:start + AI_BATCH_SIZE]
            compact = [{"record_id": row.get("record_id"), "source": row.get("source_type"), "message": row.get("message")} for row in batch]
            prompt = (
                "Classify each public YouTube chat/comment message. Use exactly one category and one subcategory from this schema: "
                + json.dumps(SUBCATEGORIES, ensure_ascii=False)
                + ". Return only a JSON array with record_id, category, and subcategory. Preserve the record_id exactly. "
                "Do not infer facts beyond the message.\n\n"
                + json.dumps(compact, ensure_ascii=False)
            )
            for suggestion in _parse_ai_array(ai_generate(prompt)):
                row = by_id.get(suggestion.get("record_id"))
                category = suggestion.get("category")
                subcategory = suggestion.get("subcategory")
                if not row or category not in CATEGORIES:
                    continue
                allowed_subcategories = SUBCATEGORIES.get(category, [])
                row["category"] = category
                row["subcategory"] = subcategory if subcategory in allowed_subcategories else (allowed_subcategories[0] if allowed_subcategories else "Other")
                row["category_source"] = "ai"
                row["importance"] = max(int(row.get("importance") or 1), 2 if category == "Questions" else 1)
                applied += 1
        warning = f"Skipped {greeting_skipped:,} high-confidence greetings/wishes before AI classification." if greeting_skipped else None
        return rows, applied, warning
    except Exception as exc:
        skipped_note = f" Skipped {greeting_skipped:,} high-confidence greetings/wishes before AI classification." if greeting_skipped else ""
        return rows, applied, f"AI categorization unavailable after {applied:,} applied suggestion(s): {type(exc).__name__}: {exc}.{skipped_note}"


def save_run(run: dict[str, Any]) -> None:
    run["rows"] = ensure_record_ids(run.get("rows", []))
    run["summary"] = analysis_summary(run.get("rows", []))
    run["row_count"] = len(run.get("rows", []))
    run["run_id"] = STORE.save(run)
    st.session_state["current_run_id"] = run["run_id"]


def load_current_run() -> dict[str, Any] | None:
    if "current_run_id" not in st.session_state:
        st.session_state["current_run_id"] = STORE.last_id()
    run_id = st.session_state.get("current_run_id")
    return STORE.load(run_id) if run_id else None


def update_row(run: dict[str, Any], record_id: str, **changes: Any) -> None:
    for row in run.get("rows", []):
        if row.get("record_id") == record_id:
            if "category" in changes and changes["category"] != row.get("category"):
                changes["category_source"] = "manual"
            row.update(changes)
            if row.get("category") == "Questions":
                row["subcategory"] = "Answered question" if row.get("answered") else (row.get("subcategory") or "Unanswered question")
            break
    save_run(run)
    st.rerun()


def display_source_chip(source: str) -> str:
    css = {"chat": "source-chat", "comment": "source-comment"}.get(source, "source-import")
    return f'<span class="source-chip {css}">{html.escape(SOURCE_LABELS.get(source, source.title()))}</span>'


def render_source_banner(run: dict[str, Any]) -> None:
    summary = run.get("summary") or analysis_summary(run.get("rows", []))
    title = html.escape(run.get("title") or "Untitled conversation")
    channel = html.escape(run.get("channel") or "Channel not supplied")
    url = html.escape(run.get("url") or "")
    chips = "".join(display_source_chip(source) + f'<span class="message-meta">{count:,}</span>' for source, count in summary.get("source_counts", {}).items())
    if run.get("synthetic"):
        chips += ' <span class="synthetic">SYNTHETIC SAMPLE — not audience evidence</span>'
    warnings = run.get("warnings") or []
    warning_text = f'<div class="warning-box" style="margin-top:.7rem">{len(warnings)} warning(s): {html.escape(" · ".join(warnings[:3]))}</div>' if warnings else ""
    st.markdown(
        f'<div class="status-banner"><div class="status-title">{title}</div>'
        f'<div class="status-subtitle">{channel} · <a href="{url}" target="_blank">{url or "source URL unavailable"}</a></div>'
        f'<div style="margin-top:.65rem">{chips}</div>'
        f'<div class="status-grid"><div class="status-cell"><div class="status-label">Captured</div><div class="status-value">{summary.get("total", 0):,} records</div></div>'
        f'<div class="status-cell"><div class="status-label">Unique authors</div><div class="status-value">{summary.get("unique_authors", 0):,}</div></div>'
        f'<div class="status-cell"><div class="status-label">Questions</div><div class="status-value">{summary.get("questions", 0):,}</div></div>'
        f'<div class="status-cell"><div class="status-label">Last saved</div><div class="status-value">{html.escape(run.get("updated_at", "")[:19].replace("T", " "))} UTC</div></div>'
        f'<div class="status-cell"><div class="status-label">Run ID</div><div class="status-value">{html.escape(run.get("run_id", ""))}</div></div></div>{warning_text}</div>',
        unsafe_allow_html=True,
    )


def run_extraction(video_url: str, include_chat: bool, include_comments: bool, max_comments: int) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    chat_progress = st.progress(0, text="Live chat · waiting")
    comment_progress = st.progress(0, text="Comments · waiting")
    status = st.empty()

    def progress(stage: str, page_count: int, record_count: int) -> None:
        if stage == "chat":
            chat_progress.progress(min(98, max(3, page_count * 3)), text=f"Live chat · {record_count:,} records · page {page_count:,}")
        elif stage == "comments":
            comment_progress.progress(65, text=f"Comments · {record_count:,} records received")
        status.info(f"Working on {SOURCE_LABELS.get(stage, stage)}. Partial results remain available if the other source fails.")

    buffer_fd, buffer_name = tempfile.mkstemp(prefix="conversation-", suffix=".csv", dir=STORE.root)
    os.close(buffer_fd)
    buffer_path = Path(buffer_name)
    try:
        raw_rows, issues = extract_combined(
            video_url.strip(), buffer_path,
            include_chat=include_chat, include_comments=include_comments,
            max_comments=max_comments or None, progress_callback=progress,
        )
        rows, normalization_warnings = normalize_records(raw_rows)
        issues.extend(normalization_warnings)
        rows, ai_applied, ai_warning = ai_categorize_rows(rows)
        if ai_applied:
            issues.append(f"AI categorization applied to {ai_applied:,} records; remaining records retain deterministic categories.")
        if ai_warning:
            issues.append(ai_warning)
        metadata = {
            "video_id": next((row.get("video_id") for row in rows if row.get("video_id")), ""),
            "video_url": next((row.get("video_url") for row in rows if row.get("video_url")), video_url),
            "video_title": next((row.get("video_title") for row in rows if row.get("video_title")), ""),
            "channel_name": next((row.get("channel_name") for row in rows if row.get("channel_name")), ""),
        }
        if not metadata["video_title"]:
            try:
                metadata.update(fetch_video_metadata(video_url))
            except Exception as exc:
                issues.append(f"Video title unavailable ({type(exc).__name__}); the run uses a fallback name.")
    finally:
        buffer_path.unlink(missing_ok=True)
    chat_count = sum(row.get("source_type") == "chat" for row in rows)
    comment_count = sum(row.get("source_type") == "comment" for row in rows)
    chat_progress.progress(100 if not include_chat or chat_count else 0, text=f"Live chat · {chat_count:,} records")
    comment_progress.progress(100 if not include_comments or comment_count else 0, text=f"Comments · {comment_count:,} records")
    status.success(f"Extraction complete · {len(rows):,} records captured")
    return rows, issues, metadata


def extraction_form(form_key: str, compact: bool = False) -> tuple[bool, dict[str, Any]]:
    with st.form(form_key, clear_on_submit=False):
        url = st.text_input("YouTube video URL", value=VIDEO_URL, help="Public youtube.com, youtu.be, Shorts, or live URL.")
        col1, col2 = st.columns(2)
        with col1:
            include_chat = st.checkbox("Live-chat replay", value=True)
        with col2:
            include_comments = st.checkbox("Video comments", value=True)
        max_comments = st.number_input("Max comments", min_value=0, max_value=5000, value=1000, step=100, help="0 means the extractor's available comments; the UI caps requests at 5,000.")
        submitted = st.form_submit_button("Start extraction", type="primary", use_container_width=True)
    return submitted, {"url": url, "include_chat": include_chat, "include_comments": include_comments, "max_comments": int(max_comments)}


def import_section(key: str, compact: bool = False) -> bool:
    upload = st.file_uploader("Import CSV, JSON, or JSONL", type=["csv", "json", "jsonl", "ndjson"], key=key, help="Imported records use the same analysis, annotations, and exports as live extraction.")
    if not upload:
        return False
    payload = upload.getvalue()
    try:
        _, _, headers = parse_import_bytes(payload, upload.name)
    except Exception as exc:
        st.error(f"Could not read this file: {exc}")
        return False
    defaults = inferred_mapping(headers)
    options = ["(auto)", *headers]
    with st.expander(f"Column mapping · {len(headers)} columns detected", expanded=not compact):
        st.caption("Message is required. Other fields are optional; automatic matching is shown when available.")
        mapping = {}
        for canonical, label in (("message", "Message text"), ("author_name", "Author"), ("source_type", "Source"), ("timestamp_iso", "Timestamp")):
            default = defaults.get(canonical, "(auto)")
            mapping[canonical] = st.selectbox(label, options, index=options.index(default) if default in options else 0, key=f"{key}_{canonical}")
            if mapping[canonical] == "(auto)":
                mapping.pop(canonical)
        st.caption("Detected mapping: " + ", ".join(f"{key} → {value}" for key, value in defaults.items()) if defaults else "No canonical columns detected; choose Message text.")
    if st.button("Import and analyze", key=f"{key}_submit", type="primary", use_container_width=True):
        try:
            rows, warnings, _ = parse_import_bytes(payload, upload.name, mapping)
            if not rows:
                st.error("No usable message rows were found. Map the message column and try again.")
                return False
            rows, ai_applied, ai_warning = ai_categorize_rows(rows)
            if ai_applied:
                warnings.append(f"AI categorization applied to {ai_applied:,} records; remaining records retain deterministic categories.")
            if ai_warning:
                warnings.append(ai_warning)
            first = rows[0]
            run = make_run(rows, title=first.get("video_title") or f"Imported · {upload.name}", channel=first.get("channel_name", ""), url=first.get("video_url", ""), warnings=warnings, synthetic=all(row.get("synthetic") for row in rows))
            run["source_status"] = {"import": {"status": "complete", "count": len(rows), "filename": upload.name}}
            save_run(run)
            st.success(f"Imported {len(rows):,} records. The complete file is persisted as run {run['run_id']}.")
            return True
        except Exception as exc:
            st.error(f"Import failed: {exc}")
    return False


def render_landing() -> None:
    st.markdown('<div class="eyebrow">Canonical Streamlit application</div>', unsafe_allow_html=True)
    st.title("Conversation Ledger")
    st.markdown('<p class="lede">A calm review desk for public YouTube conversation. Extract live-chat replay and comments when available, or bring a CSV/JSON export and keep working offline.</p>', unsafe_allow_html=True)
    st.markdown("### Start with evidence")
    col1, col2, col3 = st.columns([1.15, 1, 1])
    with col1:
        st.markdown('<div class="empty-panel"><h3>New extraction</h3><p>Use yt-dlp first, with a conservative InnerTube fallback and separate source progress.</p></div>', unsafe_allow_html=True)
        submitted, values = extraction_form("landing_extraction")
        if submitted:
            valid, message, _ = validate_youtube_url(values["url"])
            if not values["include_chat"] and not values["include_comments"]:
                st.error("Select live chat, comments, or both.")
            elif not valid:
                st.error(message)
            else:
                try:
                    rows, issues, metadata = run_extraction(values["url"], values["include_chat"], values["include_comments"], values["max_comments"])
                    if rows:
                        status = {
                            "chat": {"status": "complete" if any(row.get("source_type") == "chat" for row in rows) else "failed", "count": sum(row.get("source_type") == "chat" for row in rows)},
                            "comment": {"status": "complete" if any(row.get("source_type") == "comment" for row in rows) else "failed", "count": sum(row.get("source_type") == "comment" for row in rows)},
                        }
                        run = make_run(rows, title=metadata.get("video_title") or "YouTube conversation", channel=metadata.get("channel_name", ""), url=metadata.get("video_url") or values["url"], source_status=status, warnings=issues)
                        save_run(run)
                        st.rerun()
                except Exception as exc:
                    st.error(f"Extraction unavailable: {exc}")
                    st.caption("You can still import a previously captured CSV or JSON below; no data was lost because nothing was saved as a partial run.")
    with col2:
        st.markdown('<div class="empty-panel"><h3>Load sample data</h3><p>Explore the full workspace with 240 clearly labelled synthetic records, including queues and pagination.</p></div>', unsafe_allow_html=True)
        if st.button("Open 240-row sample", key="landing_sample", use_container_width=True):
            rows = generate_sample_records(240)
            run = make_run(rows, title="Synthetic sample conversation", channel="Sample data (synthetic)", url="https://www.youtube.com/watch?v=sample00001", source_status={"chat": {"status": "complete", "count": 160}, "comment": {"status": "complete", "count": 80}}, synthetic=True)
            save_run(run)
            st.rerun()
    with col3:
        st.markdown('<div class="empty-panel"><h3>Import / recover</h3><p>Map message, author, source, and time columns, then use the same analysis and export pipeline.</p></div>', unsafe_allow_html=True)
        if import_section("landing_import"):
            st.rerun()
    st.divider()
    st.markdown("### What stays durable")
    st.markdown("Each run is saved outside Streamlit session state in the app's controlled `.conversation_runs` directory. Annotations are attached to stable record IDs; public unauthenticated deployments should be treated as single-user or ephemeral unless their host provides durable, isolated storage.")


def render_overview(run: dict[str, Any]) -> None:
    rows = run.get("rows", [])
    summary = analysis_summary(rows)
    if run.get("synthetic"):
        st.warning("Synthetic sample data is active. Counts and themes below are for interface testing, not real audience evidence.")
    st.markdown("## Overview")
    st.caption("The first read: what arrived, what needs a host decision, and where the conversation is concentrated.")
    values = [("Total feedback", summary["total"]), ("Live chat", summary["source_counts"].get("chat", 0)), ("Comments", summary["source_counts"].get("comment", 0)), ("Unique commenters", summary["unique_authors"]), ("Questions", summary["questions"]), ("Unanswered", summary["unanswered"])]
    for metric_row in (values[:3], values[3:]):
        metrics = st.columns(3)
        for col, (label, value) in zip(metrics, metric_row):
            with col:
                st.metric(label, f"{value:,}")
    left, right = st.columns([1.4, 1])
    with left:
        st.markdown("### Conversation by category")
        category_table = pd.DataFrame({"Category": list(category_counts(rows)), "Messages": list(category_counts(rows).values())})
        st.bar_chart(category_table.set_index("Category"), y="Messages", color="#2d7691", height=280)
    with right:
        st.markdown("### Source coverage")
        source_table = pd.DataFrame({"Source": [SOURCE_LABELS.get(key, key.title()) for key in summary["source_counts"]], "Records": list(summary["source_counts"].values())})
        st.dataframe(source_table, use_container_width=True, hide_index=True)
        st.metric("SuperChats", f"{summary['superchats']:,}", help="Rows with a paid amount or SuperChat/paid-message metadata.")
        st.caption(f"Captured amount: {summary['superchat_amount']:,.2f} in source-reported currency units; mixed currencies are not converted.")
    st.markdown("### Host attention")
    qrows = [row for row in rows if row.get("is_question") and not row.get("answered")]
    if qrows:
        for row in sorted(qrows, key=lambda item: (-int(item.get("importance") or 0), item.get("timestamp_iso") or ""))[:5]:
            st.markdown(f"{display_source_chip(row.get('source_type', 'import'))} **{html.escape(row.get('author_name', 'Unknown author'))}** — {html.escape(row.get('message', ''))}", unsafe_allow_html=True)
    else:
        st.success("No unanswered questions are currently flagged.")


def render_message_item(run: dict[str, Any], row: dict[str, Any], prefix: str = "row") -> None:
    rid = row.get("record_id") or row.get("message_id") or "unknown"
    with st.container(border=True):
        top = st.columns([1.1, 5.5, 1.4])
        with top[0]:
            st.markdown(display_source_chip(row.get("source_type", "import")), unsafe_allow_html=True)
            st.caption(row.get("timestamp_iso", "")[:19].replace("T", " ") or "Time unavailable")
        with top[1]:
            flags = []
            if row.get("is_question"): flags.append("Question")
            if row.get("is_superchat"): flags.append("SuperChat")
            if row.get("starred"): flags.append("Starred")
            if row.get("answered"): flags.append("Answered")
            st.markdown(f"**{html.escape(row.get('author_name', 'Unknown author'))}** · {html.escape(row.get('category', 'General'))} / {html.escape(row.get('subcategory', 'Other'))}")
            st.markdown(f'<div class="message-text">{html.escape(row.get("message", ""))}</div>', unsafe_allow_html=True)
            if flags:
                st.caption(" · ".join(flags) + (f" · {row.get('amount')}" if row.get("amount") else ""))
        with top[2]:
            if st.button("Unstar" if row.get("starred") else "Star", key=f"{prefix}_star_{rid}", use_container_width=True):
                update_row(run, rid, starred=not row.get("starred"))
            if row.get("is_question") and st.button("Mark unanswered" if row.get("answered") else "Mark answered", key=f"{prefix}_answered_{rid}", use_container_width=True):
                update_row(run, rid, answered=not row.get("answered"))
        with st.expander("Edit category and notes"):
            with st.form(f"{prefix}_edit_{rid}"):
                category = st.selectbox("Category", CATEGORIES, index=CATEGORIES.index(row.get("category")) if row.get("category") in CATEGORIES else len(CATEGORIES) - 1)
                sub_options = SUBCATEGORIES.get(category, ["Other"])
                subcategory = st.selectbox("Subcategory", sub_options, index=sub_options.index(row.get("subcategory")) if row.get("subcategory") in sub_options else 0)
                answered = st.checkbox("Answered", value=bool(row.get("answered"))) if row.get("is_question") else bool(row.get("answered"))
                notes = st.text_area("Analyst notes", value=row.get("notes", ""), placeholder="What should the host know or do?")
                submitted = st.form_submit_button("Save review state", type="primary")
                if submitted:
                    update_row(run, rid, category=category, subcategory=subcategory, answered=answered, notes=notes)
            st.caption("Copy message text")
            st.code(row.get("message", ""), language=None)


def render_paged_messages(run: dict[str, Any], rows: list[dict[str, Any]], prefix: str, page_size: int = 20) -> None:
    if not rows:
        st.info("No records match this queue. Reset filters or broaden the question criteria.")
        return
    page_count = max(1, (len(rows) + page_size - 1) // page_size)
    page_key = f"{prefix}_page"
    select_key = f"{prefix}_page_select"
    current = min(max(int(st.session_state.get(page_key, 1)), 1), page_count)
    nav_prev, nav_select, nav_next = st.columns([1, 2, 1])
    with nav_prev:
        previous_clicked = st.button("← Previous", key=f"{prefix}_previous", disabled=current <= 1, use_container_width=True)
    with nav_next:
        next_clicked = st.button("Next →", key=f"{prefix}_next", disabled=current >= page_count, use_container_width=True)
    # Buttons are evaluated before the selectbox is instantiated, so the
    # selectbox key can be synchronized safely before Streamlit registers it.
    requested_page = current - 1 if previous_clicked else current + 1 if next_clicked else None
    if requested_page is not None:
        st.session_state[page_key] = requested_page
        st.session_state[select_key] = requested_page
    with nav_select:
        select_kwargs = {
            "options": list(range(1, page_count + 1)),
            "format_func": lambda value: f"Page {value} of {page_count}",
            "key": select_key,
            "label_visibility": "collapsed",
        }
        if select_key not in st.session_state:
            select_kwargs["index"] = current - 1
        selected = st.selectbox("Page", **select_kwargs)
    if requested_page is not None:
        page = requested_page
    elif selected != current:
        st.session_state[page_key] = int(selected)
        page = int(selected)
    else:
        page = current
    start = (page - 1) * page_size
    st.caption(f"Showing {start + 1:,}–{min(start + page_size, len(rows)):,} of {len(rows):,}. Exports are not limited by this page.")
    for row in rows[start:start + page_size]:
        render_message_item(run, row, prefix=prefix)


def render_questions(run: dict[str, Any]) -> None:
    rows = run.get("rows", [])
    st.markdown("## Questions")
    st.caption("A host-ready queue built from question signals, with unanswered items kept visible until reviewed.")
    unanswered_only = st.checkbox("Show unanswered only", value=True, key="questions_unanswered")
    question_rows = [row for row in rows if row.get("is_question") and (not unanswered_only or not row.get("answered"))]
    st.markdown(f"### {len(question_rows):,} question(s) in queue")
    render_paged_messages(run, sorted(question_rows, key=lambda row: (-int(row.get("importance") or 0), row.get("timestamp_iso") or "")), "questions")


def conversation_filters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    st.markdown("## Conversation")
    st.caption("Search the full record set. Questions and unanswered questions are review queues inside Conversation; exports always use every row.")
    with st.form("conversation_filters"):
        c1, c2, c3 = st.columns([1.45, 2.2, 1])
        view = c1.selectbox("Review view", ["All conversation", "Questions to host", "Unanswered questions"])
        search = c2.text_input("Search message, author, or notes", value=st.session_state.get("filter_search", ""))
        source = c3.selectbox("Source", ["All sources", "chat", "comment", "import"], format_func=lambda value: "All sources" if value == "All sources" else SOURCE_LABELS.get(value, value.title()))
        category = c1.selectbox("Category", ["All categories", *CATEGORIES])
        c4, c5, c6, c7 = st.columns([1.5, 1.2, 1.2, 1.2])
        subcategory = c4.selectbox("Subcategory", ["All subcategories", *sorted({row.get("subcategory") for row in rows if row.get("subcategory")})])
        author = c5.selectbox("Author", ["All authors", *sorted({row.get("author_name") for row in rows if row.get("author_name")})])
        sort = c6.selectbox("Sort", ["Chronological", "Importance"])
        st_starred = c7.checkbox("Starred")
        c8, c9 = st.columns([1.2, 4])
        unanswered = c8.checkbox("Unanswered")
        superchat = c9.checkbox("SuperChat")
        submitted = st.form_submit_button("Apply filters", type="primary")
    if submitted:
        st.session_state["filter_search"] = search
        st.session_state["conversation_filter_values"] = {"view": view, "search": search, "source": source, "category": category, "subcategory": subcategory, "author": author, "sort": sort, "starred": st_starred, "unanswered": unanswered, "superchat": superchat}
    values = st.session_state.get("conversation_filter_values", {"view": "All conversation", "search": "", "source": "All sources", "category": "All categories", "subcategory": "All subcategories", "author": "All authors", "sort": "Chronological", "starred": False, "unanswered": False, "superchat": False})
    if st.button("Reset conversation filters", key="reset_filters"):
        st.session_state.pop("conversation_filter_values", None)
        st.session_state.pop("filter_search", None)
        st.rerun()
    filter_values = {key: value for key, value in values.items() if key != "view"}
    filtered = filter_rows(rows, **filter_values)
    if values.get("view") == "Questions to host":
        filtered = [row for row in filtered if row.get("is_question")]
    elif values.get("view") == "Unanswered questions":
        filtered = [row for row in filtered if row.get("is_question") and not row.get("answered")]
    st.markdown(f"### {len(filtered):,} matching record(s)")
    return filtered


def render_audience(run: dict[str, Any]) -> None:
    rows = run.get("rows", [])
    st.markdown("## Audience")
    st.caption("Find repeat voices and their recent context without flattening the conversation into a raw table.")
    summaries = audience_summary(rows)
    if not summaries:
        st.info("No author data is available.")
        return
    table = pd.DataFrame(summaries)
    st.dataframe(table, use_container_width=True, hide_index=True, column_config={"recent_message": st.column_config.TextColumn("Recent message", width="large")})
    author = st.selectbox("Review one author", ["Select an author", *[item["author"] for item in summaries]], key="audience_author")
    if author != "Select an author":
        st.markdown(f"### Messages from {html.escape(author)}")
        author_rows = [row for row in rows if row.get("author_name") == author]
        render_paged_messages(run, sorted(author_rows, key=lambda row: row.get("timestamp_iso") or "", reverse=True), "audience", page_size=10)


def render_ai(run: dict[str, Any]) -> None:
    st.markdown("## AI Assistant")
    st.caption(f"Gemini categorization is automatic for new live/imported runs when configured, using batches of {AI_BATCH_SIZE} and up to {AI_MAX_ROWS:,} non-synthetic records. Manual corrections are protected.")
    if not get_ai_key():
        st.info("AI is disabled. Add GEMINI_API_KEY through Streamlit secrets or the environment to enable bounded briefs and categorization; all non-AI analysis remains available.")
        return
    st.success("Gemini is configured for optional bounded assistance. The key is never displayed or written to run files.")
    rows = run.get("rows", [])
    sample = rows[:80]
    compact = [{"id": row.get("record_id"), "source": row.get("source_type"), "author": row.get("author_name"), "message": row.get("message")} for row in sample]
    if st.button("Draft executive brief", type="primary"):
        prompt = "You are an editorial research assistant. Summarize this public YouTube conversation in Hindi and English. Return headings: executive brief, burning topics, sample questions, host action notes. Be explicit that counts are sampled if applicable. Do not invent facts.\n\n" + json.dumps(compact, ensure_ascii=False)
        try:
            st.markdown(ai_generate(prompt))
        except Exception as exc:
            st.error(f"AI request failed: {exc}")
    if st.button(f"Re-run AI categorization for up to {AI_MAX_ROWS:,} records"):
        try:
            rows, changed, warning = ai_categorize_rows(rows)
            if warning:
                st.warning(warning)
            if changed:
                save_run(run)
                st.success(f"Applied {changed:,} AI category suggestions. Manual corrections were preserved.")
                st.rerun()
            else:
                st.warning("The model returned no usable category suggestions, or all records were already manually corrected.")
        except Exception as exc:
            st.error(f"AI categorization failed: {exc}")


def render_exports(run: dict[str, Any]) -> None:
    st.markdown("## Exports")
    st.caption("Every download here is generated from the persisted full run. Conversation pagination never truncates exports.")
    rows = run.get("rows", [])
    values = st.session_state.get("conversation_filter_values", {})
    filtered = filter_rows(rows, **{key: value for key, value in values.items() if key != "view"}) if values else list(rows)
    if values.get("view") == "Questions to host":
        filtered = [row for row in filtered if row.get("is_question")]
    elif values.get("view") == "Unanswered questions":
        filtered = [row for row in filtered if row.get("is_question") and not row.get("answered")]
    summary = analysis_summary(rows)
    st.markdown(f"**Full run:** {len(rows):,} rows · **Current filter:** {len(filtered):,} rows · **Host review:** {sum(row.get('is_question') or row.get('starred') or row.get('is_superchat') for row in rows):,} priority rows")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download full combined CSV", rows_to_csv(rows), file_name=f"conversation_{run['run_id']}.csv", mime="text/csv", type="primary", use_container_width=True)
        st.download_button("Download filtered CSV", rows_to_csv(filtered), file_name=f"conversation_{run['run_id']}_filtered.csv", mime="text/csv", use_container_width=True)
    with c2:
        st.download_button("Download full JSON", rows_to_json(rows, {"run_id": run["run_id"], "title": run.get("title"), "source_status": run.get("source_status")}), file_name=f"conversation_{run['run_id']}.json", mime="application/json", use_container_width=True)
        st.download_button("Download host review sheet", host_review_csv(rows), file_name=f"conversation_{run['run_id']}_host_review.csv", mime="text/csv", use_container_width=True)
    st.markdown("### Export notes")
    st.markdown("- Full combined CSV retains source labels, analysis state, and raw JSON metadata for every row.\n- Filtered CSV follows the last applied Conversation filters, not the visible page.\n- The concise host review sheet includes questions, starred records, and SuperChats with priority and notes.\n- Synthetic sample exports remain labelled with `synthetic=true`.")


def render_past_runs() -> None:
    st.markdown("## Past Runs")
    st.caption(f"Persisted in `{STORE.root}` outside session state. This local store is intentionally scoped to this app; public unauthenticated hosting may not provide cross-user isolation or durable storage.")
    runs = STORE.list_runs()
    if not runs:
        st.info("No persisted runs yet. Load a sample, import a file, or complete an extraction.")
        return
    for item in runs:
        with st.container(border=True):
            cols = st.columns([4, 1.3, 1.3, 1.3])
            with cols[0]:
                label = "SYNTHETIC SAMPLE · " if item.get("synthetic") else ""
                st.markdown(f"**{label}{html.escape(item.get('title') or 'Untitled run')}**")
                st.caption(f"{html.escape(item.get('channel') or 'Channel unavailable')} · {item.get('row_count', 0):,} rows · saved {html.escape((item.get('updated_at') or '')[:19].replace('T', ' '))} UTC · `{item.get('run_id')}`")
            with cols[1]:
                if st.button("Reload", key=f"reload_{item['run_id']}", use_container_width=True):
                    st.session_state["current_run_id"] = item["run_id"]
                    st.rerun()
            with cols[2]:
                run = STORE.load(item["run_id"])
                if run:
                    st.download_button("Export", rows_to_csv(run.get("rows", [])), file_name=f"conversation_{item['run_id']}.csv", mime="text/csv", key=f"export_{item['run_id']}", use_container_width=True)
            with cols[3]:
                confirm = st.checkbox("Confirm", key=f"confirm_delete_{item['run_id']}")
                if st.button("Delete", key=f"delete_{item['run_id']}", disabled=not confirm, use_container_width=True):
                    STORE.delete(item["run_id"])
                    if st.session_state.get("current_run_id") == item["run_id"]:
                        st.session_state["current_run_id"] = STORE.last_id()
                    st.rerun()


def render_workspace(run: dict[str, Any]) -> None:
    if st.button("＋ New extraction", key="workspace_new_extraction"):
        st.session_state["current_run_id"] = None
        st.rerun()
    render_source_banner(run)
    rows = run.get("rows", [])
    summary = analysis_summary(rows)
    ai_count = sum(row.get("category_source") == "ai" for row in rows)
    tabs = st.tabs([
        f"Overview ({summary['total']:,})",
        f"Conversation ({summary['total']:,})",
        f"Audience ({summary['unique_authors']:,})",
        f"AI Assistant ({ai_count:,})",
        "Exports (4)",
        f"Past Runs ({len(STORE.list_runs()):,})",
    ])
    with tabs[0]: render_overview(run)
    with tabs[1]:
        filtered = conversation_filters(run.get("rows", []))
        render_paged_messages(run, filtered, "conversation")
    with tabs[2]: render_audience(run)
    with tabs[3]: render_ai(run)
    with tabs[4]: render_exports(run)
    with tabs[5]: render_past_runs()


run = load_current_run()
if run:
    render_workspace(run)
else:
    render_landing()
