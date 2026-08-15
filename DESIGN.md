# Conversation Ledger design system

## Direction

The app is an editorial evidence ledger: a host or analyst should immediately see what was captured, what needs attention, and what can be exported without losing source evidence. The direction seed was `7b784ff2`, assigned candidate 5, with a degraded roll and no challengers. The visual world is intentionally restrained and operational rather than decorative.

## Physical scene

A host or editor reviews a live conversation at a desk in daylight or a moderately lit edit room. The surface uses a paper-white reading field, a cool slate utility rail, ink-dark text, and a single signal-orange action color. Source chips carry the only additional color: blue for live chat and umber for video comments.

## Tokens

- Paper: `#f5f7f8`
- Panel: `#ffffff`
- Utility rail: `#e9eef0`
- Ink: `#15212b`
- Muted: `#61707a`
- Line: `#d9e1e5`
- Action: `#d95d38`
- Live chat: `#2d7691`
- Video comments: `#8f5b38`
- Success: `#28785b`
- Warning: `#8b5c17`

## Composition

The first viewport is status-first: source banner, counts, category distribution, source coverage, and host attention. The workbench uses six stable tabs: Overview, Conversation, Audience, AI Assistant, Exports, and Past Runs. Questions and Unanswered Questions are review views inside Conversation. Raw metadata is retained in exports but is not shown in the everyday review UI; raw CSV is never the opening surface.

## Components

- Status banner: title, channel, linked URL, source chips/counts, synthetic warning, saved timestamp, and run ID.
- Evidence item: source/time, author, category/subcategory, message, flags, star/answer actions, editable review state, and copyable text.
- Queue: bounded pagination with explicit “showing x–y of n”; all exports use the full persisted run.
- Source chip: blue live-chat, umber comments, neutral imported data.
- Empty state: three direct paths—new extraction, synthetic sample, and import/recover.

## Responsive and accessibility rules

The desktop view keeps the utility rail visible. At narrow widths it collapses the rail and exposes a main “New extraction” action; status fields stack vertically, and metric rows use three columns. Controls have explicit labels, focus outlines, high contrast, big-text mode, and visible empty/loading/error/partial states.

## Honest boundaries

Sample records are labelled synthetic. AI is optional and bounded; no key means no AI dependency in the core workflow. Public unauthenticated hosting may not provide durable, isolated cross-user storage; local runs are stored in `.conversation_runs` outside Streamlit session state.
