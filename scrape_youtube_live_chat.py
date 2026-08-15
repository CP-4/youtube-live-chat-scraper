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


VIDEO_URL = "https://www.youtube.com/watch?v=vhEJQ3l8G_E"
CSV_FIELDS = [
    "video_id", "video_url", "video_title", "channel_name", "duration_seconds",
    "message_type", "message_id", "video_offset_ms", "timestamp_usec",
    "timestamp_iso", "author_name", "author_channel_id", "message",
    "badges", "amount", "currency", "membership_months", "raw_json",
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
    return {**metadata, "message_type": kind.replace("liveChat", "").replace("Renderer", ""),
            "message_id": item.get("id", ""), "video_offset_ms": offset_ms,
            "timestamp_usec": timestamp_usec, "timestamp_iso": timestamp_iso,
            "author_name": author, "author_channel_id": author_id, "message": message,
            "badges": " | ".join(badges), "amount": amount, "currency": currency,
            "membership_months": months, "raw_json": json.dumps(item, ensure_ascii=False)}


def extract(video_url, output, progress_callback: Optional[Callable[[int, int], None]] = None):
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
    with Path(output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    if not progress_callback:
        print(f"\nWrote {len(rows):,} records to {output}")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video_url", nargs="?", default=VIDEO_URL)
    parser.add_argument("--output", default="vhEJQ3l8G_E_livechat.csv")
    args = parser.parse_args()
    VIDEO_URL = args.video_url
    extract(args.video_url, args.output)
