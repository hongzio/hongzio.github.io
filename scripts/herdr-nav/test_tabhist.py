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


class ParseMinDwellTest(unittest.TestCase):
    def test_reads_value(self):
        self.assertEqual(tabhist.parse_min_dwell("min_dwell_seconds = 3\n"), 3.0)

    def test_reads_float(self):
        self.assertEqual(tabhist.parse_min_dwell("min_dwell_seconds = 2.5\n"), 2.5)

    def test_default_when_absent(self):
        self.assertEqual(tabhist.parse_min_dwell("max = 10\n"), tabhist.DEFAULT_MIN_DWELL)

    def test_zero_allowed(self):
        self.assertEqual(tabhist.parse_min_dwell("min_dwell_seconds = 0\n"), 0.0)

    def test_negative_falls_back(self):
        self.assertEqual(
            tabhist.parse_min_dwell("min_dwell_seconds = -1\n"), tabhist.DEFAULT_MIN_DWELL
        )

    def test_non_numeric_falls_back(self):
        self.assertEqual(
            tabhist.parse_min_dwell("min_dwell_seconds = soon\n"),
            tabhist.DEFAULT_MIN_DWELL,
        )

    def test_ignores_comment(self):
        text = "# min_dwell_seconds = 99\nmin_dwell_seconds = 4\n"
        self.assertEqual(tabhist.parse_min_dwell(text), 4.0)


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


class SettleTest(unittest.TestCase):
    def test_no_pending(self):
        self.assertEqual(
            tabhist.settle(["A", "B"], 1, None, 100.0, 5, 100), (["A", "B"], 1, False)
        )

    def test_commits_when_held(self):
        # pending C held 10s, anchor is B -> committed, off_anchor False
        self.assertEqual(
            tabhist.settle(["A", "B"], 1, ("C", 0.0), 10.0, 5, 100),
            (["A", "B", "C"], 2, False),
        )

    def test_drops_flyby(self):
        # pending C held 2s (< 5) -> dropped, off_anchor True (physically on C)
        self.assertEqual(
            tabhist.settle(["A", "B"], 1, ("C", 0.0), 2.0, 5, 100),
            (["A", "B"], 1, True),
        )

    def test_echo_is_noop(self):
        # pending equals the anchor (a back/forward echo) -> no commit regardless
        self.assertEqual(
            tabhist.settle(["A", "B"], 1, ("B", 0.0), 100.0, 5, 100),
            (["A", "B"], 1, False),
        )

    def test_commit_truncates_forward_branch(self):
        # anchor B (cursor 1) with forward branch C; commit held D -> A-B-D
        self.assertEqual(
            tabhist.settle(["A", "B", "C"], 1, ("D", 0.0), 10.0, 5, 100),
            (["A", "B", "D"], 2, False),
        )

    def test_empty_history_flyby(self):
        self.assertEqual(tabhist.settle([], -1, ("A", 0.0), 1.0, 5, 100), ([], -1, True))

    def test_empty_history_commit(self):
        self.assertEqual(
            tabhist.settle([], -1, ("A", 0.0), 10.0, 5, 100), (["A"], 0, False)
        )


class DwellScenarioTest(unittest.TestCase):
    """Fly-bys dropped, held tabs kept, driven through settle()."""

    def test_flyby_sequence(self):
        limit, thr = 100, 5
        entries, cursor = ["Z"], 0  # Z already committed and the anchor
        # Focus A (staged). settle with pending None is a no-op.
        entries, cursor, _ = tabhist.settle(entries, cursor, None, 30.0, thr, limit)
        pending = ("A", 30.0)
        # Fly A -> B -> C -> E at 1s intervals (each < threshold): all dropped.
        for tab, t in (("B", 31.0), ("C", 32.0), ("E", 33.0)):
            entries, cursor, _ = tabhist.settle(entries, cursor, pending, t, thr, limit)
            pending = (tab, t)
        # Sit on E for 20s, then a further focus resolves it -> E committed.
        entries, cursor, _ = tabhist.settle(entries, cursor, pending, 53.0, thr, limit)
        self.assertEqual((entries, cursor), (["Z", "E"], 1))


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
