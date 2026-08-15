"""Shared data, analysis, import, persistence, and export helpers for the Streamlit app.

The UI deliberately keeps this module free of Streamlit so the same normalization
and export rules can be exercised from fixtures and command-line tests.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CATEGORIES = [
    "Questions",
    "Guest/content requests",
    "Health/feedback",
    "Greetings/devotional",
    "Political commentary",
    "Celebrations/community",
    "Stream logistics",
    "Mantras/sign-offs",
    "General",
]

SUBCATEGORIES = {
    "Questions": ["Unanswered question", "Answered question", "Clarification"],
    "Guest/content requests": ["Guest request", "Topic request", "Source request"],
    "Health/feedback": ["Health", "Praise", "Critique", "Technical feedback"],
    "Greetings/devotional": ["Greeting", "Prayer/devotional", "Blessing"],
    "Political commentary": ["Domestic politics", "International politics", "Policy"],
    "Celebrations/community": ["Celebration", "Community", "Milestone"],
    "Stream logistics": ["Audio/video", "Timing", "Moderation", "Links/access"],
    "Mantras/sign-offs": ["Mantra", "Sign-off", "Chant"],
    "General": ["Comment", "Context", "Other"],
}

SOURCE_LABELS = {"chat": "Live chat", "comment": "Video comments", "import": "Imported"}

FIELD_ALIASES = {
    "message": ["message", "text", "comment", "content", "body", "message_text"],
    "author_name": ["author_name", "author", "username", "user", "name", "display_name", "person", "who"],
    "source_type": ["source_type", "source", "type", "origin", "kind"],
    "timestamp_iso": ["timestamp_iso", "timestamp", "published_at", "created_at", "date"],
    "message_id": ["message_id", "id", "comment_id", "chat_id"],
    "amount": ["amount", "superchat_amount", "purchase_amount", "paid_amount"],
    "badges": ["badges", "badge", "author_badges"],
    "video_id": ["video_id", "videoid"],
    "video_url": ["video_url", "url", "video"],
    "video_title": ["video_title", "title"],
    "channel_name": ["channel_name", "channel", "uploader", "channel_title"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " | ".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _lower(value: Any) -> str:
    return _text(value).casefold()


def _number(value: Any) -> float:
    cleaned = re.sub(r"[^0-9.,]", "", _text(value)).replace(",", "")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([A-Za-z0-9_-]{11})", _text(url))
    return match.group(1) if match else ""


def validate_youtube_url(url: str) -> tuple[bool, str, str]:
    value = _text(url)
    video_id = extract_video_id(value)
    if not video_id:
        return False, "Enter a YouTube video URL with an 11-character video ID.", ""
    if not re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", value):
        return False, "Use a youtube.com or youtu.be URL.", ""
    return True, "Valid YouTube video URL", video_id


def _lookup(raw: Mapping[str, Any], canonical: str, mapping: Mapping[str, str] | None = None) -> Any:
    if mapping and mapping.get(canonical) in raw:
        return raw.get(mapping[canonical], "")
    normalized = {re.sub(r"[^a-z0-9]", "", str(key).casefold()): key for key in raw}
    for alias in FIELD_ALIASES.get(canonical, [canonical]):
        key = normalized.get(re.sub(r"[^a-z0-9]", "", alias.casefold()))
        if key is not None:
            return raw.get(key, "")
    return ""


def _infer_source(raw: Mapping[str, Any], source_hint: str | None, message_type: str) -> str:
    explicit = _lower(_lookup(raw, "source_type"))
    if explicit in {"chat", "live chat", "live_chat", "livechat"}:
        return "chat"
    if explicit in {"comment", "comments", "video comment", "video comments"}:
        return "comment"
    if "chat" in message_type or "live" in message_type:
        return "chat"
    if "comment" in message_type:
        return "comment"
    if _lookup(raw, "amount") or _lookup(raw, "badges"):
        return "chat"
    if source_hint in {"chat", "comment", "import"}:
        return source_hint
    return "comment"


def _category(message: str, source_type: str, is_question: bool) -> tuple[str, str]:
    text = message.casefold()
    if is_question:
        if any(word in text for word in ("clarify", "मतलब", "अर्थ", "कैसे", "why", "क्यों")):
            return "Questions", "Clarification"
        return "Questions", "Unanswered question"
    if any(word in text for word in ("guest", "invite", "अतिथि", "बुलाइ", "topic", "विषय", "speak on")):
        return "Guest/content requests", "Guest request" if any(word in text for word in ("guest", "invite", "अतिथि")) else "Topic request"
    if any(word in text for word in ("health", "स्वास्थ्य", "audio", "आवाज़", "sound", "mic", "feedback", "great", "excellent", "बेहतरीन")):
        if any(word in text for word in ("audio", "आवाज़", "sound", "mic")):
            return "Stream logistics", "Audio/video"
        return "Health/feedback", "Praise" if any(word in text for word in ("great", "excellent", "बेहतरीन")) else "Feedback"
    if any(word in text for word in ("ram ram", "namaste", "नमस्ते", "जय", "हर हर", "ॐ", "om ", "प्रणाम", "🙏")):
        return "Greetings/devotional", "Greeting" if any(word in text for word in ("ram", "namaste", "नमस्ते", "प्रणाम")) else "Prayer/devotional"
    if any(word in text for word in ("modi", "rahul", "congress", "bjp", "trump", "government", "सरकार", "चुनाव", "election", "politics", "राजनीति")):
        return "Political commentary", "Domestic politics" if any(word in text for word in ("modi", "rahul", "congress", "bjp", "सरकार", "चुनाव")) else "International politics"
    if any(word in text for word in ("congrat", "शुभकामना", "birthday", "जन्मदिन", "welcome", "स्वागत", "community", "समुदाय")):
        return "Celebrations/community", "Celebration" if any(word in text for word in ("congrat", "शुभकामना", "birthday", "जन्मदिन")) else "Community"
    if any(word in text for word in ("link", "लिंक", "when", "कब", "start", "शुरू", "stream", "live", "moderator", "internet")):
        return "Stream logistics", "Links/access" if any(word in text for word in ("link", "लिंक")) else "Timing"
    if any(word in text for word in ("jai shree ram", "हर हर महादेव", "राम नाम", "जय हिंद", "शुभ रात्रि", "good night", "धन्यवाद", "thank you")):
        return "Mantras/sign-offs", "Mantra" if any(word in text for word in ("jai", "हर हर", "राम नाम", "जय हिंद")) else "Sign-off"
    return "General", "Comment"


def normalize_record(raw: Mapping[str, Any], source_hint: str | None = None,
                     synthetic: bool = False, mapping: Mapping[str, str] | None = None) -> dict[str, Any]:
    message = _text(_lookup(raw, "message", mapping))
    author = _text(_lookup(raw, "author_name", mapping)) or "Unknown author"
    message_type = _text(raw.get("message_type"))
    source_type = _infer_source(raw, source_hint, message_type)
    timestamp = _text(_lookup(raw, "timestamp_iso", mapping))
    amount = _text(_lookup(raw, "amount", mapping))
    badges = _text(_lookup(raw, "badges", mapping))
    message_id = _text(_lookup(raw, "message_id", mapping))
    video_id = _text(_lookup(raw, "video_id", mapping))
    video_url = _text(_lookup(raw, "video_url", mapping))
    video_title = _text(_lookup(raw, "video_title", mapping))
    channel_name = _text(_lookup(raw, "channel_name", mapping))
    is_question = bool(re.search(r"\?|\b(how|why|what|when|where|can|could|will|क्या|क्यों|कैसे|कब|कहाँ|कौन)\b", message, re.I))
    category, subcategory = _category(message, source_type, is_question)
    superchat = bool(amount) or any(token in (message_type + " " + badges).casefold() for token in ("paid", "superchat", "super chat"))
    if not message_id:
        stable = "|".join((source_type, video_id, timestamp, author, message))
        message_id = "local-" + hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]
    raw_json = raw.get("raw_json", "")
    if isinstance(raw_json, (dict, list)):
        raw_json = json.dumps(raw_json, ensure_ascii=False)
    row = {
        "record_id": message_id,
        "source_type": source_type,
        "video_id": video_id,
        "video_url": video_url,
        "video_title": video_title,
        "channel_name": channel_name,
        "message_type": message_type or ("Chat message" if source_type == "chat" else "Comment"),
        "message_id": message_id,
        "video_offset_ms": _text(raw.get("video_offset_ms")),
        "timestamp_usec": _text(raw.get("timestamp_usec")),
        "timestamp_iso": timestamp,
        "author_name": author,
        "author_channel_id": _text(raw.get("author_channel_id") or raw.get("author_id")),
        "message": message,
        "badges": badges,
        "amount": amount,
        "currency": _text(raw.get("currency")),
        "membership_months": _text(raw.get("membership_months")),
        "raw_json": raw_json if raw_json else json.dumps(dict(raw), ensure_ascii=False),
        "comment_like_count": _text(raw.get("comment_like_count") or raw.get("like_count")),
        "comment_parent_id": _text(raw.get("comment_parent_id") or raw.get("parent")),
        "comment_author_is_uploader": _text(raw.get("comment_author_is_uploader") or raw.get("author_is_uploader")),
        "synthetic": bool(synthetic or raw.get("synthetic")),
        "category": _text(raw.get("category")) if _text(raw.get("category")) in CATEGORIES else category,
        "subcategory": _text(raw.get("subcategory")) or subcategory,
        "is_question": bool(raw.get("is_question", is_question)),
        "answered": bool(raw.get("answered", False)),
        "starred": bool(raw.get("starred", False)),
        "notes": _text(raw.get("notes")),
        "importance": int(raw.get("importance") or (3 if superchat else 2 if is_question else 1)),
        "is_superchat": bool(raw.get("is_superchat", superchat)),
    }
    if row["answered"] and row["category"] == "Questions" and not row["subcategory"]:
        row["subcategory"] = "Answered question"
    if row["answered"] and row["category"] == "Questions" and row["subcategory"] == "Unanswered question":
        row["subcategory"] = "Answered question"
    return row


def normalize_records(records: Iterable[Mapping[str, Any]], source_hint: str | None = None,
                      synthetic: bool = False, mapping: Mapping[str, str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(records, start=1):
        row = normalize_record(raw, source_hint, synthetic, mapping)
        if not row["message"]:
            warnings.append(f"Skipped row {index}: no message text found")
            continue
        if row["record_id"] in seen:
            continue
        seen.add(row["record_id"])
        normalized.append(row)
    if not normalized:
        warnings.append("No message rows were found after validation")
    return normalized, warnings


def generate_sample_records(count: int = 240) -> list[dict[str, Any]]:
    messages = [
        ("क्या आप इस विषय पर एक अलग चर्चा कर सकते हैं?", "Questions"),
        ("Please invite a guest who can explain this history.", "Guest/content requests"),
        ("Audio is clear today, thank you.", "Health/feedback"),
        ("राम राम अनुपम जी 🙏", "Greetings/devotional"),
        ("इस चुनाव पर आपकी क्या राय है?", "Political commentary"),
        ("बहुत बहुत शुभकामनाएं पूरी टीम को!", "Celebrations/community"),
        ("The stream link is working now.", "Stream logistics"),
        ("जय श्री राम, धन्यवाद और शुभ रात्रि।", "Mantras/sign-offs"),
        ("This was a useful perspective.", "General"),
    ]
    authors = ["@ananya", "@bharat_reader", "@curious_mind", "@dharma_voice", "@editorialdesk", "@sanjay_42", "@vidya", "@yash"]
    rows = []
    for i in range(count):
        message, category = messages[i % len(messages)]
        source = "chat" if i % 3 else "comment"
        raw = {
            "source_type": source,
            "video_id": "sample00001",
            "video_url": "https://www.youtube.com/watch?v=sample00001",
            "video_title": "Synthetic sample conversation",
            "channel_name": "Sample data (synthetic)",
            "message_id": f"sample-{i + 1:04d}",
            "timestamp_iso": f"2026-08-15T{(9 + i // 60) % 24:02d}:{i % 60:02d}:00+00:00",
            "author_name": authors[i % len(authors)],
            "message": message + (f" #{i + 1}" if i % 11 == 0 else ""),
            "badges": "Top commenter" if i % 17 == 0 else "",
            "amount": "₹50" if i % 37 == 0 else "",
            "raw_json": {"synthetic": True, "index": i + 1},
            "category": category,
            "synthetic": True,
        }
        rows.append(normalize_record(raw, synthetic=True))
    return rows


def parse_import_bytes(data: bytes, filename: str, mapping: Mapping[str, str] | None = None) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Parse CSV, JSON, or JSONL and return normalized rows, warnings, and headers."""
    name = filename.casefold()
    text = data.decode("utf-8-sig", errors="replace")
    raw_records: list[Mapping[str, Any]]
    headers: list[str] = []
    if name.endswith(".jsonl") or name.endswith(".ndjson"):
        raw_records = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif name.endswith(".json"):
        payload = json.loads(text)
        if isinstance(payload, dict):
            for key in ("rows", "records", "comments", "chat", "data", "items"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        raw_records = payload if isinstance(payload, list) else []
    else:
        reader = csv.DictReader(io.StringIO(text))
        headers = list(reader.fieldnames or [])
        raw_records = list(reader)
    if raw_records and not headers:
        headers = list(raw_records[0].keys())
    rows, warnings = normalize_records(raw_records, source_hint="import", mapping=mapping)
    return rows, warnings, headers


def inferred_mapping(headers: Sequence[str]) -> dict[str, str]:
    normalized = {re.sub(r"[^a-z0-9]", "", h.casefold()): h for h in headers}
    result = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in [canonical, *aliases]:
            match = normalized.get(re.sub(r"[^a-z0-9]", "", alias.casefold()))
            if match:
                result[canonical] = match
                break
    return result


def analysis_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    source_counts = Counter(row.get("source_type", "import") for row in rows)
    authors = {row.get("author_name") for row in rows if row.get("author_name") and row.get("author_name") != "Unknown author"}
    questions = [row for row in rows if row.get("is_question")]
    superchats = [row for row in rows if row.get("is_superchat")]
    amount = sum(_number(row.get("amount")) for row in superchats)
    return {
        "total": len(rows),
        "source_counts": dict(source_counts),
        "unique_authors": len(authors),
        "questions": len(questions),
        "unanswered": sum(1 for row in questions if not row.get("answered")),
        "superchats": len(superchats),
        "superchat_amount": amount,
        "synthetic": bool(rows) and all(bool(row.get("synthetic")) for row in rows),
    }


def category_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(row.get("category") or "General" for row in rows)
    return {category: counts.get(category, 0) for category in CATEGORIES}


def subcategory_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(f"{row.get('category') or 'General'} · {row.get('subcategory') or 'Other'}" for row in rows)
    return dict(counts.most_common())


def audience_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("author_name") or "Unknown author"].append(row)
    result = []
    for author, messages in grouped.items():
        ordered = sorted(messages, key=lambda row: row.get("timestamp_iso") or "", reverse=True)
        result.append({
            "author": author,
            "messages": len(messages),
            "questions": sum(bool(row.get("is_question")) for row in messages),
            "badges": sum(bool(row.get("badges")) for row in messages),
            "superchats": sum(bool(row.get("is_superchat")) for row in messages),
            "recent_message": _text(ordered[0].get("message"))[:140] if ordered else "",
        })
    return sorted(result, key=lambda item: (-item["messages"], item["author"].casefold()))


def filter_rows(rows: Sequence[Mapping[str, Any]], *, search: str = "", source: str = "All sources",
                category: str = "All categories", subcategory: str = "All subcategories",
                author: str = "All authors", unanswered: bool = False, starred: bool = False,
                superchat: bool = False, sort: str = "Chronological") -> list[dict[str, Any]]:
    needle = search.casefold().strip()
    filtered = []
    for row in rows:
        haystack = " ".join((_text(row.get("message")), _text(row.get("author_name")), _text(row.get("notes")))).casefold()
        if needle and needle not in haystack:
            continue
        if source != "All sources" and row.get("source_type") != source:
            continue
        if category != "All categories" and row.get("category") != category:
            continue
        if subcategory != "All subcategories" and row.get("subcategory") != subcategory:
            continue
        if author != "All authors" and row.get("author_name") != author:
            continue
        if unanswered and (not row.get("is_question") or row.get("answered")):
            continue
        if starred and not row.get("starred"):
            continue
        if superchat and not row.get("is_superchat"):
            continue
        filtered.append(dict(row))
    if sort == "Importance":
        filtered.sort(key=lambda row: (-int(row.get("importance") or 0), row.get("timestamp_iso") or ""))
    else:
        filtered.sort(key=lambda row: (row.get("timestamp_iso") or "", row.get("record_id") or ""))
    return filtered


def rows_to_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    fields = [
        "record_id", "source_type", "video_id", "video_url", "video_title", "channel_name", "message_type",
        "message_id", "video_offset_ms", "timestamp_usec", "timestamp_iso", "author_name", "author_channel_id",
        "message", "badges", "amount", "currency", "membership_months", "comment_like_count",
        "comment_parent_id", "comment_author_is_uploader", "category", "subcategory", "is_question",
        "answered", "starred", "notes", "importance", "is_superchat", "synthetic", "raw_json",
    ]
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode("utf-8")


def rows_to_json(rows: Sequence[Mapping[str, Any]], metadata: Mapping[str, Any] | None = None) -> bytes:
    payload = {"metadata": dict(metadata or {}), "row_count": len(rows), "rows": list(rows)}
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def host_review_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    fields = ["priority", "source_type", "author_name", "message", "category", "subcategory", "answered", "starred", "notes", "timestamp_iso", "amount"]
    questions = [row for row in rows if row.get("is_question") or row.get("starred") or row.get("is_superchat")]
    questions.sort(key=lambda row: (-int(row.get("importance") or 0), row.get("timestamp_iso") or ""))
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in questions:
        writer.writerow({**row, "priority": "High" if row.get("is_superchat") or row.get("starred") else "Review"})
    return handle.getvalue().encode("utf-8")


class RunStore:
    """Small JSON-file store scoped to this app, independent of Streamlit session state."""

    def __init__(self, root: str | Path | None = None):
        configured = root or os.environ.get("YT_ANALYZER_DATA_DIR")
        self.root = Path(configured) if configured else Path(__file__).resolve().parent / ".conversation_runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.pointer = self.root / "last_run.txt"

    def path_for(self, run_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", run_id):
            raise ValueError("Invalid run identifier")
        return self.root / f"{run_id}.json"

    def save(self, run: Mapping[str, Any]) -> str:
        run_id = _text(run.get("run_id")) or uuid.uuid4().hex[:12]
        payload = dict(run)
        payload["run_id"] = run_id
        payload["updated_at"] = utc_now()
        target = self.path_for(run_id)
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)
        self.pointer.write_text(run_id, encoding="utf-8")
        return run_id

    def load(self, run_id: str) -> dict[str, Any] | None:
        path = self.path_for(run_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def last_id(self) -> str | None:
        if self.pointer.exists():
            value = self.pointer.read_text(encoding="utf-8").strip()
            if value and self.path_for(value).exists():
                return value
        runs = self.list_runs()
        return runs[0]["run_id"] if runs else None

    def list_runs(self) -> list[dict[str, Any]]:
        summaries = []
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                summary = {key: payload.get(key) for key in ("run_id", "created_at", "updated_at", "title", "channel", "row_count", "synthetic", "warnings", "source_status")}
                summaries.append(summary)
            except (OSError, ValueError, TypeError):
                continue
        return sorted(summaries, key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)

    def delete(self, run_id: str) -> None:
        self.path_for(run_id).unlink(missing_ok=True)
        if self.pointer.exists() and self.pointer.read_text(encoding="utf-8").strip() == run_id:
            self.pointer.unlink(missing_ok=True)


def make_run(rows: Sequence[Mapping[str, Any]], *, title: str = "Untitled conversation", channel: str = "",
             url: str = "", source_status: Mapping[str, Any] | None = None, warnings: Sequence[str] = (),
             synthetic: bool = False) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    cloned = [dict(row) for row in rows]
    summary = analysis_summary(cloned)
    return {
        "run_id": run_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "title": title or "Untitled conversation",
        "channel": channel,
        "url": url,
        "rows": cloned,
        "row_count": len(cloned),
        "summary": summary,
        "source_status": dict(source_status or {}),
        "warnings": list(warnings),
        "synthetic": bool(synthetic or summary.get("synthetic")),
    }
