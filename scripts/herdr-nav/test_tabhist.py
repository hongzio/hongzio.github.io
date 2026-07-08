#!/usr/bin/env python3
"""Unit tests for the pure helpers in tabhist.py (config/event parse, history)."""
import unittest

import tabhist


class ParseMaxTest(unittest.TestCase):
    def test_reads_value(self):
        self.assertEqual(tabhist.parse_max("max = 42\n"), 42)

    def test_ignores_comments_and_junk(self):
        text = "# max = 999\nfoo = 1\nmax = 30  # inline\n"
        self.assertEqual(tabhist.parse_max(text), 30)

    def test_default_when_absent(self):
        self.assertEqual(tabhist.parse_max("nope = 1\n"), tabhist.DEFAULT_MAX)

    def test_clamps_to_minimum(self):
        self.assertEqual(tabhist.parse_max("max = 1\n"), tabhist.MIN_MAX)

    def test_non_numeric_falls_back(self):
        self.assertEqual(tabhist.parse_max("max = lots\n"), tabhist.DEFAULT_MAX)


class ExtractTabTest(unittest.TestCase):
    def test_real_payload(self):
        obj = {
            "event": "tab_focused",
            "data": {"type": "tab_focused", "tab_id": "w1:t1", "previous_tab_id": "w1:t2"},
        }
        self.assertEqual(tabhist.extract_tab(obj), "w1:t1")

    def test_missing(self):
        self.assertIsNone(tabhist.extract_tab({"event": "x"}))
        self.assertIsNone(tabhist.extract_tab({"data": {"previous_tab_id": "w1:t2"}}))
        self.assertIsNone(tabhist.extract_tab(None))
        self.assertIsNone(tabhist.extract_tab({"data": {"tab_id": ""}}))


class RecordFocusTest(unittest.TestCase):
    def test_first_focus(self):
        self.assertEqual(tabhist.record_focus([], -1, "A", 100), (["A"], 0))

    def test_append_at_end(self):
        self.assertEqual(
            tabhist.record_focus(["A", "B"], 1, "C", 100), (["A", "B", "C"], 2)
        )

    def test_noop_on_current(self):
        # focusing the tab the cursor already points at (the back/forward echo)
        entries, cursor = ["A", "B", "C"], 1
        self.assertEqual(
            tabhist.record_focus(entries, cursor, "B", 100), (entries, cursor)
        )

    def test_truncates_forward_branch(self):
        # A-B(*)-C then focus D  =>  A-B-D(*)   (the required semantic)
        self.assertEqual(
            tabhist.record_focus(["A", "B", "C"], 1, "D", 100), (["A", "B", "D"], 2)
        )

    def test_trims_oldest_past_limit(self):
        entries, cursor = tabhist.record_focus(["A", "B", "C"], 2, "D", 3)
        self.assertEqual((entries, cursor), (["B", "C", "D"], 2))

    def test_revisiting_older_tab_appends(self):
        # not a consecutive-current no-op: A is not entries[cursor]
        self.assertEqual(
            tabhist.record_focus(["A", "B"], 1, "A", 100), (["A", "B", "A"], 2)
        )

    def test_corrupt_cursor_clamped(self):
        self.assertEqual(
            tabhist.record_focus(["A", "B"], 99, "C", 100), (["A", "B", "C"], 2)
        )


class StepTest(unittest.TestCase):
    def test_back_simple(self):
        self.assertEqual(tabhist.step_back(["A", "B", "C"], 2, {"A", "B", "C"}), 1)

    def test_back_skips_closed(self):
        # B is gone -> back from C lands on A
        self.assertEqual(tabhist.step_back(["A", "B", "C"], 2, {"A", "C"}), 0)

    def test_back_none_at_start(self):
        self.assertIsNone(tabhist.step_back(["A", "B"], 0, {"A", "B"}))

    def test_back_none_when_all_closed(self):
        self.assertIsNone(tabhist.step_back(["A", "B", "C"], 2, {"C"}))

    def test_forward_simple(self):
        self.assertEqual(tabhist.step_forward(["A", "B", "C"], 0, {"A", "B", "C"}), 1)

    def test_forward_skips_closed(self):
        self.assertEqual(tabhist.step_forward(["A", "B", "C"], 0, {"A", "C"}), 2)

    def test_forward_none_at_end(self):
        self.assertIsNone(tabhist.step_forward(["A", "B"], 1, {"A", "B"}))


class ScenarioTest(unittest.TestCase):
    """The end-to-end semantic from the spec, driven through the pure core."""

    def test_full_flow(self):
        live = {"A", "B", "C", "D"}
        entries, cursor = [], -1
        for tab in ("A", "B", "C"):  # visit A, B, C
            entries, cursor = tabhist.record_focus(entries, cursor, tab, 100)
        self.assertEqual((entries, cursor), (["A", "B", "C"], 2))

        cursor = tabhist.step_back(entries, cursor, live)  # back -> B
        self.assertEqual(cursor, 1)
        # the focus echo for B is a no-op
        entries, cursor = tabhist.record_focus(entries, cursor, "B", 100)
        self.assertEqual((entries, cursor), (["A", "B", "C"], 1))

        # now navigate to D -> A-B-D(*)
        entries, cursor = tabhist.record_focus(entries, cursor, "D", 100)
        self.assertEqual((entries, cursor), (["A", "B", "D"], 2))


if __name__ == "__main__":
    unittest.main()
