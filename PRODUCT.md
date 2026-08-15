# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Streamlit Python application; the existing Streamlit surface is the canonical/default application path.

## Users

Primary users are hosts, editors, and research analysts reviewing audience conversation around a YouTube video or live stream. They need to move from raw public messages to a trustworthy queue of questions, themes, and follow-up actions.

## Product Purpose

Turn publicly available YouTube live-chat replay and video comments into an editorial analysis workspace. Success means a user can import or extract conversation, understand source coverage and limitations, find high-value questions and themes, annotate items, and export a complete review pack.

## Positioning

The product combines chat and comments in one source-labelled record model, preserves raw metadata for auditability, and keeps analysis useful when YouTube extraction is unavailable through CSV/JSON import and persisted past runs.

## Operating Context

The app is used from a desktop or laptop browser during editorial review. Extraction is conservative and public-data-only: yt-dlp is preferred, InnerTube is a fallback, and no IP rotation or evasion is used. An unauthenticated public deployment cannot promise private ownership, cross-user isolation, or durable shared storage; the local app persists runs in its controlled data directory.

## Capabilities and Constraints

- Validate YouTube video URLs and select live chat replay, comments, or both.
- Show separate source progress, partial results, actionable errors, source/status metadata, and safe extraction limits.
- Normalize extracted rows and imported CSV, JSON, or JSONL into one analysis pipeline.
- Provide Overview, Questions, Conversation, Audience, AI Assistant, Exports, and Past Runs workspaces.
- Persist per-item star, answered, notes, and category/subcategory corrections outside Streamlit session state.
- UI pagination is allowed, but exports must include every normalized row.
- AI is optional, bounded, and disabled without a Gemini key; non-AI analysis remains complete.
- Synthetic sample records must be visibly labelled and never presented as factual audience evidence.

## Evidence on Hand

- Existing yt-dlp-first and InnerTube live-chat extraction code in `scrape_youtube_live_chat.py`.
- Existing public live-chat CSV fixture `vhEJQ3l8G_E_livechat.csv`.
- Existing channel inventory CSVs and transcript artifacts in this repository.
- The user explicitly supplied the product requirements and the decision to retire Render and the sibling local-installable app as product paths.

## Product Principles

- Source truth before interpretation: show what was captured, from where, and what failed.
- Analysis before raw data: the first viewport should help a host decide what matters.
- Partial is useful: preserve and expose usable results even when one source fails.
- Reversible editorial judgment: annotations persist but raw evidence remains intact.
- Public-data boundaries are explicit: no claims beyond the captured, imported, or synthetic records.

## Accessibility & Inclusion

Use labelled controls, keyboard-visible focus, high-contrast states, readable dense tables, responsive narrow-width behavior, and a big-text mode. Support Hindi/English content without assuming a single language.
