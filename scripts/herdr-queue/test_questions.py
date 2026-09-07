"""Tests for questions.py (queued questions plugin).

Run with the system python (plugin hooks run under it):
    /usr/bin/python3 -m unittest discover scripts/herdr-queue
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

import questions


RULE = "─" * 120


def snapshot(*body: str, above: str = "  some transcript content", below: str = "  ~/path │ Fable 5\n  ⏵⏵ auto mode on") -> str:
    """A detection-buffer snapshot shaped like Claude Code's bottom screen."""
    return "\n".join([above, RULE, *body, RULE, below])


class ParsePromptBoxTest(unittest.TestCase):
    def test_empty_box_yields_empty_text(self):
        box = questions.parse_prompt_box(snapshot("❯"))
        self.assertIsNotNone(box)
        self.assertEqual(box.text, "")

    def test_single_line_draft(self):
        box = questions.parse_prompt_box(snapshot("❯ a test question - should stay"))
        self.assertEqual(box.text, "a test question - should stay")

    def test_nbsp_after_prompt_glyph(self):
        # while the agent is working Claude renders "❯\xa0draft"
        box = questions.parse_prompt_box(snapshot("❯\xa0queued question: about refactoring?"))
        self.assertEqual(box.text, "queued question: about refactoring?")

    def test_continuation_rows_join_with_space(self):
        # hard newlines and soft wraps both render as 2-space-indented rows
        box = questions.parse_prompt_box(snapshot("❯ first line", "  second line"))
        self.assertEqual(box.text, "first line second line")

    def test_rules_inside_transcript_do_not_confuse_the_parser(self):
        text = "\n".join(["  older content", RULE, "  more content",
                          RULE, "❯ draft here", RULE, "  status line"])
        box = questions.parse_prompt_box(text)
        self.assertEqual(box.text, "draft here")

    def test_no_prompt_glyph_means_no_box(self):
        # a menu/dialog between rules is not the composer
        self.assertIsNone(questions.parse_prompt_box(snapshot("  1. Yes, I trust")))

    def test_fewer_than_two_rules_means_no_box(self):
        self.assertIsNone(questions.parse_prompt_box("just some text\nno rules"))

    def test_clear_count_overshoots_visible_length(self):
        box = questions.parse_prompt_box(snapshot("❯ abc def", "  ghi"))
        # 12 visible draft chars over 2 rows; must exceed chars + boundaries
        self.assertGreaterEqual(questions.clear_count(box), 12 + 1)

    def test_clear_count_zero_for_empty_box(self):
        box = questions.parse_prompt_box(snapshot("❯"))
        self.assertEqual(questions.clear_count(box), 0)


class QueueStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_load_missing_file_is_empty(self):
        self.assertEqual(questions.load_queue("553ea145-39a3"), [])

    def test_save_then_load_round_trips(self):
        items = questions.add_question([], "first question")
        questions.save_queue("553ea145-39a3", items)
        loaded = questions.load_queue("553ea145-39a3")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["text"], "first question")

    def test_sessions_are_isolated(self):
        questions.save_queue("sess-a", questions.add_question([], "question from a"))
        self.assertEqual(questions.load_queue("sess-b"), [])

    def test_corrupt_file_is_tolerated(self):
        questions.save_queue("sess-c", questions.add_question([], "x"))
        with open(questions.queue_path("sess-c"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(questions.load_queue("sess-c"), [])

    def test_session_id_is_sanitized_for_filenames(self):
        path = questions.queue_path("../../evil id")
        self.assertNotIn("..", os.path.basename(path))
        self.assertNotIn("/", os.path.basename(path).replace(".json", ""))
        self.assertTrue(path.startswith(self.tmp.name))

    def test_add_question_assigns_growing_ids(self):
        items = questions.add_question([], "one")
        items = questions.add_question(items, "two")
        self.assertEqual([i["text"] for i in items], ["one", "two"])
        self.assertLess(items[0]["id"], items[1]["id"])

    def test_add_question_skips_blank_text(self):
        self.assertEqual(questions.add_question([], "   "), [])


class ItemLabelTest(unittest.TestCase):
    def test_newlines_render_as_return_symbol(self):
        self.assertEqual(questions.item_label("a\nb", 40), "a⏎b")

    def test_wide_chars_truncate_by_display_width(self):
        label = questions.item_label("ＡＢＣＤＥＦＧ", 8)
        self.assertTrue(label.endswith("…"))
        # 3 wide chars (6 cols) + ellipsis fits in 8
        self.assertLessEqual(questions.disp_width(label), 8)


class EditKeyTest(unittest.TestCase):
    def test_printable_inserts_at_cursor(self):
        text, cur, done = questions.edit_key("ac", 1, "b")
        self.assertEqual((text, cur, done), ("abc", 2, None))

    def test_backspace_deletes_before_cursor(self):
        text, cur, done = questions.edit_key("abc", 2, "\x7f")
        self.assertEqual((text, cur, done), ("ac", 1, None))

    def test_enter_commits(self):
        _, _, done = questions.edit_key("abc", 3, "\n")
        self.assertEqual(done, "commit")

    def test_esc_cancels(self):
        _, _, done = questions.edit_key("abc", 3, "\x1b")
        self.assertEqual(done, "cancel")

    def test_arrows_move_cursor_within_bounds(self):
        import curses
        _, cur, _ = questions.edit_key("abc", 0, curses.KEY_LEFT)
        self.assertEqual(cur, 0)
        _, cur, _ = questions.edit_key("abc", 3, curses.KEY_RIGHT)
        self.assertEqual(cur, 3)
        _, cur, _ = questions.edit_key("abc", 1, curses.KEY_RIGHT)
        self.assertEqual(cur, 2)


if __name__ == "__main__":
    unittest.main()
