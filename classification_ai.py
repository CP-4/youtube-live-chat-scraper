"""Optional, bounded AI assistance for conversation classification.

The deterministic classifier is the core path.  This module is deliberately
free of Streamlit so the same bounded provider call can be used by the UI and
by development-set evaluation scripts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


def _bounded_env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, lower), upper)


AI_BATCH_SIZE = _bounded_env_int("GEMINI_CLASSIFICATION_BATCH_SIZE", 100, 40, 1500)
AI_MAX_ROWS = _bounded_env_int("GEMINI_CLASSIFICATION_MAX_ROWS", 1500, AI_BATCH_SIZE, 1500)
AI_REQUEST_TIMEOUT_SECONDS = _bounded_env_int("GEMINI_REQUEST_TIMEOUT_SECONDS", 90, 30, 180)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

CATEGORY_SCHEMA = {
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

JSON_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "record_id": {"type": "string"},
            "category": {"type": "string"},
            "subcategory": {"type": "string"},
        },
        "required": ["record_id", "category", "subcategory"],
    },
}


def _load_local_env() -> None:
    """Load an ignored local .env when python-dotenv is available.

    Streamlit secrets and real environment variables remain authoritative.  A
    missing optional dependency simply means the host must provide the key via
    Streamlit secrets/environment, which is a safe degradation.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        env_path = Path(__file__).with_name(".env")
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            name = name.strip()
            if name not in {"GEMINI_API_KEY", "GEMINI_MODEL"} or name in os.environ:
                continue
            value = value.strip().strip("\"'")
            os.environ[name] = value
        return
    load_dotenv(Path(__file__).with_name(".env"), override=False)


_load_local_env()


def get_ai_key() -> str:
    return str(os.environ.get("GEMINI_API_KEY", "")).strip()


def get_ai_model() -> str:
    return str(os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)).strip() or DEFAULT_GEMINI_MODEL


def _safe_error(exc: Exception, key: str) -> str:
    return str(exc).replace(key, "[redacted]")


def _output_text(value: Any) -> str:
    text = str(getattr(value, "output_text", "") or "").strip()
    if text:
        return text
    for step in reversed(getattr(value, "steps", []) or []):
        for block in reversed(getattr(step, "content", []) or []):
            text = str(getattr(block, "text", "") or "").strip()
            if text:
                return text
    return ""


def ai_generate(prompt: str, json_output: bool = False, *, key: str | None = None,
                model: str | None = None) -> str:
    """Call Gemini with a hard request timeout and no implicit retry storm.

    Supports the newer Interactions API and the installed 1.x SDK's
    ``models.generate_content`` API.  The provider call is never required for
    deterministic extraction to succeed.
    """
    resolved_key = (get_ai_key() if key is None else key).strip()
    if not resolved_key:
        raise RuntimeError("Gemini is disabled because GEMINI_API_KEY is not configured.")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Gemini support is not installed; install the google-genai dependency.") from exc

    resolved_model = (model or get_ai_model()).strip() or DEFAULT_GEMINI_MODEL
    http_options = None
    try:
        http_options = types.HttpOptions(
            timeout=AI_REQUEST_TIMEOUT_SECONDS * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
        )
    except (AttributeError, TypeError):
        # Keep compatibility with older SDKs that do not expose HttpOptions.
        http_options = None
    client_kwargs = {"api_key": resolved_key}
    if http_options is not None:
        client_kwargs["http_options"] = http_options
    client = genai.Client(**client_kwargs)
    try:
        interactions = getattr(client, "interactions", None)
        if interactions is not None and hasattr(interactions, "create"):
            request: dict[str, Any] = {"model": resolved_model, "input": prompt, "store": False}
            if json_output:
                request["response_format"] = {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": JSON_SCHEMA,
                }
            return_text = _output_text(interactions.create(**request))
        else:
            config_kwargs: dict[str, Any] = {"temperature": 0.1}
            if json_output:
                # Classification only needs exact labels; allowing a large
                # unconstrained thinking/output budget makes long batches
                # needlessly slow and increases timeout risk.
                record_count = prompt.count('"record_id"')
                config_kwargs.update({
                    "response_mime_type": "application/json",
                    "response_schema": JSON_SCHEMA,
                    "max_output_tokens": min(65536, max(4096, record_count * 80)),
                    "thinking_config": types.ThinkingConfig(thinking_budget=0),
                })
            response = client.models.generate_content(
                model=resolved_model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            return_text = str(getattr(response, "text", "") or "").strip()
        if return_text:
            return return_text
        raise RuntimeError("Gemini returned no text output.")
    except Exception as exc:
        message = _safe_error(exc, resolved_key)
        if "404" in message or "not found" in message.casefold() or "not available" in message.casefold():
            raise RuntimeError(f"Gemini model {resolved_model} is unavailable; set GEMINI_MODEL to a supported model.") from exc
        raise RuntimeError(message) from exc


def parse_ai_array(response: str) -> list[dict[str, Any]]:
    """Extract a JSON array while rejecting prose and malformed responses."""
    cleaned = response.strip().replace("```json", "").replace("```", "").strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("Gemini did not return a JSON array")
    payload = json.loads(cleaned[start:end + 1])
    return payload if isinstance(payload, list) else []


ProgressCallback = Callable[[Mapping[str, Any]], None]


def ai_categorize_rows(rows: list[dict[str, Any]], limit: int = AI_MAX_ROWS,
                       progress_callback: ProgressCallback | None = None,
                       *, key: str | None = None, model: str | None = None) -> tuple[list[dict[str, Any]], int, str | None]:
    """Apply bounded AI suggestions, preserving deterministic/manual state.

    A provider failure stops the optional enrichment and returns the rows
    already updated plus a warning.  Remaining rows retain deterministic labels.
    """
    resolved_key = (get_ai_key() if key is None else key).strip()
    greeting_skipped = sum(1 for row in rows if row.get("ai_excluded"))
    candidates = [
        row for row in rows
        if row.get("message") and not row.get("synthetic")
        and row.get("category_source") not in {"manual", "imported"}
        and not row.get("ai_excluded")
    ][:max(0, limit)]
    if not resolved_key:
        return rows, 0, "AI classification was not run; deterministic classification remains active."
    if not candidates:
        note = f"Skipped {greeting_skipped:,} high-confidence greetings/wishes." if greeting_skipped else None
        return rows, 0, note

    total = len(candidates)
    batches = (total + AI_BATCH_SIZE - 1) // AI_BATCH_SIZE
    by_id = {str(row.get("record_id")): row for row in candidates}
    applied = 0
    if progress_callback:
        progress_callback({"stage": "ai", "event": "start", "processed": 0, "total": total, "batch": 0, "batches": batches, "applied": 0})
    try:
        for start in range(0, total, AI_BATCH_SIZE):
            batch_number = start // AI_BATCH_SIZE + 1
            batch = candidates[start:start + AI_BATCH_SIZE]
            compact = [{"record_id": row.get("record_id"), "source": row.get("source_type"), "message": row.get("message")} for row in batch]
            prompt = (
                "Classify each public YouTube chat/comment message for editorial review. Use exactly one category and one subcategory from this schema: "
                + json.dumps(CATEGORY_SCHEMA, ensure_ascii=False)
                + ". Return only a JSON array with record_id, category, and subcategory. Preserve record_id exactly. Do not infer facts beyond the message.\n\n"
                + json.dumps(compact, ensure_ascii=False)
            )
            if progress_callback:
                progress_callback({"stage": "ai", "event": "request", "processed": start, "total": total, "batch": batch_number, "batches": batches, "applied": applied})
            suggestions = parse_ai_array(ai_generate(prompt, json_output=True, key=resolved_key, model=model))
            batch_applied = 0
            for suggestion in suggestions:
                row = by_id.get(str(suggestion.get("record_id")))
                category = suggestion.get("category")
                subcategory = suggestion.get("subcategory")
                if not row or category not in CATEGORY_SCHEMA:
                    continue
                allowed = CATEGORY_SCHEMA[category]
                row["category"] = category
                row["subcategory"] = subcategory if subcategory in allowed else allowed[0]
                row["category_source"] = "ai"
                row["importance"] = max(int(row.get("importance") or 1), 2 if category == "Questions" else 1)
                applied += 1
                batch_applied += 1
            if progress_callback:
                progress_callback({"stage": "ai", "event": "complete", "processed": min(start + len(batch), total), "total": total, "batch": batch_number, "batches": batches, "applied": applied, "batch_applied": batch_applied})
    except Exception as exc:
        skipped_note = f" Skipped {greeting_skipped:,} high-confidence greetings/wishes." if greeting_skipped else ""
        return rows, applied, f"AI categorization stopped after {applied:,} applied suggestion(s): {type(exc).__name__}: {exc}.{skipped_note} Deterministic labels were retained for the rest."
    note = f"Skipped {greeting_skipped:,} high-confidence greetings/wishes before AI classification." if greeting_skipped else None
    return rows, applied, note
