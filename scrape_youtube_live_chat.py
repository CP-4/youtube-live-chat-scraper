#!/usr/bin/env python3
"""Download a YouTube live-chat replay and flatten it to an auditable CSV."""

import argparse
import csv
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import requests
from yt_dlp import YoutubeDL


VIDEO_URL = "https://www.youtube.com/watch?v=vhEJQ3l8G_E"
CSV_FIELDS = [
    "source_type", "video_id", "video_url", "video_title", "channel_name", "duration_seconds",
    "message_type", "message_id", "video_offset_ms", "timestamp_usec",
    "timestamp_iso", "author_name", "author_channel_id", "message",
    "badges", "amount", "currency", "membership_months", "raw_json",
    "comment_like_count", "comment_parent_id", "comment_author_is_uploader",
]


def runs_text(value):
    if not isinstance(value, dict):
        return ""
    out = []
    for run in value.get("runs", []):
        if "text" in run:
            out.append(run["text"])
        elif "emoji" in run:
            emoji = run["emoji"]
            out.append(emoji.get("shortcuts", [emoji.get("emojiId", "")])[0])
    return "".join(out)


def first(pattern, text, default=""):
    match = re.search(pattern, text)
    return html.unescape(match.group(1)) if match else default


def page_metadata(page, video_id, video_url):
    title = first(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', page)
    channel = first(r'<link itemprop="name" content="([^"]*)"', page)
    duration = first(r'<meta itemprop="duration" content="PT([^\"]+)"', page)
    duration_seconds = ""
    if duration:
        hours = int(first(r"(\d+)H", duration, "0"))
        minutes = int(first(r"(\d+)M", duration, "0"))
        seconds = float(first(r"([\d.]+)S", duration, "0"))
        duration_seconds = int(hours * 3600 + minutes * 60 + seconds)
    return {"video_id": video_id, "video_url": video_url, "video_title": title,
            "channel_name": channel, "duration_seconds": duration_seconds}


def renderer_to_row(renderer, metadata, offset_ms):
    kind = next(iter(renderer))
    item = renderer[kind]
    message = runs_text(item.get("message", {}))
    author = item.get("authorName", {}).get("simpleText", "")
    author_id = item.get("authorExternalChannelId", "")
    badges = []
    for badge in item.get("authorBadges", []):
        badge_data = badge.get("liveChatAuthorBadgeRenderer", {})
        label = badge_data.get("accessibility", {}).get("accessibilityData", {}).get("label")
        if label:
            badges.append(label)
    timestamp_usec = item.get("timestampUsec", "")
    timestamp_iso = ""
    if timestamp_usec:
        timestamp_iso = datetime.fromtimestamp(int(timestamp_usec) / 1_000_000, timezone.utc).isoformat()
    purchase = item.get("purchaseAmountText", {}).get("simpleText", "")
    amount = item.get("amountText", {}).get("simpleText", "") or purchase
    currency = item.get("currency", "")
    months = item.get("months", "")
    return {**metadata, "source_type": "chat", "message_type": kind.replace("liveChat", "").replace("Renderer", ""),
            "message_id": item.get("id", ""), "video_offset_ms": offset_ms,
            "timestamp_usec": timestamp_usec, "timestamp_iso": timestamp_iso,
            "author_name": author, "author_channel_id": author_id, "message": message,
            "badges": " | ".join(badges), "amount": amount, "currency": currency,
            "membership_months": months, "raw_json": json.dumps(item, ensure_ascii=False),
            "comment_like_count": "", "comment_parent_id": "",
            "comment_author_is_uploader": ""}


def comment_to_row(comment, metadata):
    timestamp = comment.get("timestamp")
    timestamp_usec = ""
    timestamp_iso = ""
    if timestamp is not None:
        timestamp_usec = str(int(float(timestamp) * 1_000_000))
        timestamp_iso = datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat()
    uploader = comment.get("author_is_uploader")
    return {
        **metadata,
        "source_type": "comment",
        "message_type": "Comment",
        "message_id": comment.get("id", ""),
        "video_offset_ms": "",
        "timestamp_usec": timestamp_usec,
        "timestamp_iso": timestamp_iso,
        "author_name": comment.get("author", ""),
        "author_channel_id": comment.get("author_id", ""),
        "message": comment.get("text", "") or comment.get("html", ""),
        "badges": "",
        "amount": "",
        "currency": "",
        "membership_months": "",
        "raw_json": json.dumps(comment, ensure_ascii=False),
        "comment_like_count": comment.get("like_count", ""),
        "comment_parent_id": comment.get("parent", ""),
        "comment_author_is_uploader": "" if uploader is None else str(bool(uploader)).lower(),
    }


def write_rows(rows, output):
    with Path(output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def extract(video_url, output=None, progress_callback: Optional[Callable[[int, int], None]] = None):
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", video_url)
    if not match:
        raise ValueError("Enter a valid YouTube video URL with an 11-character video ID.")
    video_id = match.group(1)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"})
    page_response = session.get(video_url, timeout=45)
    page_response.raise_for_status()
    page = page_response.text
    api_key = first(r'"INNERTUBE_API_KEY":"([^"]+)', page)
    client_version = first(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)', page)
    continuation = first(r'"liveChatRenderer":\{"continuations":\[\{"reloadContinuationData":\{"continuation":"([^"]+)', page)
    if not all((api_key, client_version, continuation)):
        raise RuntimeError("Could not find YouTube live-chat replay continuation")
    metadata = page_metadata(page, video_id, video_url)
    endpoint = "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat_replay?key=" + api_key
    rows, seen = [], set()
    page_count = 0
    while continuation:
        page_count += 1
        response = session.post(endpoint, json={"context": {"client": {
            "clientName": "WEB", "clientVersion": client_version}},
            "continuation": continuation}, timeout=45)
        response.raise_for_status()
        data = response.json().get("continuationContents", {}).get("liveChatContinuation", {})
        for action in data.get("actions", []):
            replay = action.get("replayChatItemAction", {})
            offset = replay.get("videoOffsetTimeMsec", "")
            for nested in replay.get("actions", []):
                item = nested.get("addChatItemAction", {}).get("item", {})
                for renderer in item.values():
                    if not isinstance(renderer, dict) or not renderer:
                        continue
                    row = renderer_to_row({next(iter(item)): renderer}, metadata, offset)
                    key = row["message_id"] or (row["video_offset_ms"], row["message"], row["author_name"])
                    if key not in seen and (row["message"] or row["message_type"] not in {"ViewerEngagementMessage"}):
                        seen.add(key)
                        rows.append(row)
        next_cont = ""
        for cont in data.get("continuations", []):
            candidate = cont.get("liveChatReplayContinuationData", {}).get("continuation")
            if candidate:
                next_cont = candidate
                break
        continuation = next_cont
        if progress_callback:
            progress_callback(page_count, len(rows))
        else:
            print(f"pages={page_count:,} records={len(rows):,}", end="\r", flush=True)
        time.sleep(0.05)
    rows.sort(key=lambda row: (int(row["video_offset_ms"] or 0), row["timestamp_usec"], row["message_id"]))
    if output:
        write_rows(rows, output)
    if not progress_callback:
        if output:
            print(f"\nWrote {len(rows):,} records to {output}")
    return rows


def extract_comments(video_url, progress_callback=None, max_comments=None):
    """Retrieve YouTube comments through yt-dlp and normalize them to CSV rows."""
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", video_url)
    if not match:
        raise ValueError("Enter a valid YouTube video URL with an 11-character video ID.")

    options = {
        "getcomments": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": {"youtube": {"player_client": ["android_vr"]}},
    }
    if max_comments:
        options["extractor_args"]["youtube"]["max_comments"] = [str(max_comments)]
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(video_url, download=False)

    video_id = info.get("id", match.group(1))
    resolved_url = info.get("webpage_url") or video_url
    metadata = {
        "video_id": video_id,
        "video_url": resolved_url,
        "video_title": info.get("title", ""),
        "channel_name": info.get("channel") or info.get("uploader", ""),
        "duration_seconds": info.get("duration", ""),
    }
    comments = list(info.get("comments") or [])
    rows = [comment_to_row(comment, metadata) for comment in comments]
    if progress_callback:
        progress_callback("comments", len(rows))
    return rows


def extract_combined(video_url, output, include_chat=True, include_comments=True,
                     max_comments=None, progress_callback=None):
    """Extract enabled sources and write one combined, source-labelled CSV."""
    rows = []
    issues = []

    if include_chat:
        try:
            def chat_progress(page_count, record_count):
                if progress_callback:
                    progress_callback("chat", page_count, record_count)
            rows.extend(extract(video_url, progress_callback=chat_progress))
        except Exception as exc:
            issues.append(f"Live chat: {exc}")

    if include_comments:
        try:
            def comment_progress(stage, record_count):
                if progress_callback:
                    progress_callback(stage, 0, record_count)
            rows.extend(extract_comments(
                video_url, progress_callback=comment_progress, max_comments=max_comments
            ))
        except Exception as exc:
            issues.append(f"Comments: {exc}")

    rows.sort(key=lambda row: (row["timestamp_usec"] or "", row["source_type"], row["message_id"]))
    if not rows:
        raise RuntimeError("No rows were extracted. " + " | ".join(issues))
    write_rows(rows, output)
    return rows, issues


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video_url", nargs="?", default=VIDEO_URL)
    parser.add_argument("--output", default="vhEJQ3l8G_E_livechat.csv")
    args = parser.parse_args()
    VIDEO_URL = args.video_url
    rows, issues = extract_combined(args.video_url, args.output)
    print(f"Wrote {len(rows):,} combined records to {args.output}")
    for issue in issues:
        print(f"Warning: {issue}")
