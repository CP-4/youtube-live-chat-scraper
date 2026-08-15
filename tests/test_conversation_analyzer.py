import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from streamlit_app.conversation_analyzer import (
    CATEGORIES,
    RunStore,
    analysis_summary,
    filter_rows,
    generate_sample_records,
    make_run,
    parse_import_bytes,
    rows_to_csv,
    rows_to_json,
)
from streamlit_app.scrape_youtube_live_chat import comment_to_row, renderer_to_row, runs_text


class ConversationAnalyzerTests(unittest.TestCase):
    def test_json3_chat_renderer_and_comment_fixture(self):
        renderer = {
            "liveChatTextMessageRenderer": {
                "id": "chat-1",
                "message": {"runs": [{"text": "राम राम "}, {"emoji": {"shortcuts": [":pray:"]}}]},
                "authorName": {"simpleText": "@reader"},
                "authorExternalChannelId": "UC1",
                "timestampUsec": "1700000000000000",
                "authorBadges": [{"liveChatAuthorBadgeRenderer": {"accessibility": {"accessibilityData": {"label": "Top fan"}}}}],
            }
        }
        self.assertEqual(runs_text(renderer["liveChatTextMessageRenderer"]["message"]), "राम राम :pray:")
        row = renderer_to_row(renderer, {"video_id": "abc", "video_url": "https://youtu.be/abc", "video_title": "T", "channel_name": "C", "duration_seconds": 10}, "42")
        self.assertEqual(row["source_type"], "chat")
        self.assertEqual(row["author_name"], "@reader")
        self.assertIn("Top fan", row["badges"])
        comment = comment_to_row({"id": "comment-1", "author": "A", "text": "Can you explain this?", "timestamp": 1700000000, "like_count": 4}, row)
        self.assertEqual(comment["source_type"], "comment")
        self.assertEqual(comment["comment_like_count"], 4)

    def test_sample_categorization_covers_required_categories_and_questions(self):
        rows = generate_sample_records(240)
        categories = {row["category"] for row in rows}
        self.assertTrue(set(CATEGORIES).issubset(categories))
        summary = analysis_summary(rows)
        self.assertEqual(summary["total"], 240)
        self.assertGreater(summary["questions"], 0)
        self.assertGreater(summary["unanswered"], 0)
        self.assertGreater(summary["superchats"], 0)
        self.assertTrue(all(row["synthetic"] for row in rows))

    def test_csv_mapping_json_and_jsonl_import(self):
        csv_data = "text,person,kind\nCan you cover this?,A,comment\nराम राम,@b,chat\n"
        rows, warnings, headers = parse_import_bytes(csv_data.encode(), "messages.csv")
        self.assertEqual(headers, ["text", "person", "kind"])
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source_type"], "comment")
        self.assertEqual(rows[1]["source_type"], "chat")

        json_data = json.dumps({"records": [{"message": "What next?", "author": "A", "source": "comment"}]})
        rows, _, _ = parse_import_bytes(json_data.encode(), "messages.json")
        self.assertEqual(rows[0]["category"], "Questions")

        jsonl = b'{"message":"Jai Hind","author":"A","source_type":"chat"}\n{"message":"Great stream","author":"B","source_type":"comment"}\n'
        rows, _, _ = parse_import_bytes(jsonl, "messages.jsonl")
        self.assertEqual(len(rows), 2)

    def test_manual_mapping_and_filtering(self):
        data = b"body,who,origin\nPlease invite a guest,Editor,comment\nAudio is clear,Viewer,chat\n"
        rows, _, _ = parse_import_bytes(data, "mapped.csv", {"message": "body", "author_name": "who", "source_type": "origin"})
        self.assertEqual(rows[0]["author_name"], "Editor")
        filtered = filter_rows(rows, source="chat")
        self.assertEqual(len(filtered), 1)

    def test_persistence_roundtrip_and_full_export_count(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(directory)
            rows = generate_sample_records(241)
            run = make_run(rows, title="Fixture", channel="Synthetic", synthetic=True)
            run_id = store.save(run)
            loaded = store.load(run_id)
            self.assertEqual(loaded["row_count"], 241)
            self.assertEqual(store.last_id(), run_id)
            exported = rows_to_csv(loaded["rows"])
            self.assertEqual(sum(1 for _ in csv.DictReader(io.StringIO(exported.decode()))), 241)
            payload = json.loads(rows_to_json(loaded["rows"], {"run_id": run_id}))
            self.assertEqual(payload["row_count"], 241)
            store.delete(run_id)
            self.assertIsNone(store.load(run_id))

    def test_run_keys_are_unique_for_extracted_rows_without_record_ids(self):
        raw_rows = [
            {"source_type": "chat", "message_id": "same-id", "author_name": "A", "message": "hello"},
            {"source_type": "comment", "message_id": "same-id", "author_name": "B", "message": "hello"},
            {"source_type": "chat", "message_id": "", "author_name": "C", "message": "another"},
        ]
        run = make_run(raw_rows, title="Key fixture")
        keys = [row["record_id"] for row in run["rows"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(key != "unknown" for key in keys))


if __name__ == "__main__":
    unittest.main()
