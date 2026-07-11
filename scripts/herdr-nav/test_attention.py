#!/usr/bin/env python3
"""Unit tests for the pure helpers in attention.py (event parse / select / trim)."""
import unittest

import attention as recent


class ExtractEventTest(unittest.TestCase):
    def test_real_payload(self):
        obj = {
            "event": "pane_agent_status_changed",
            "data": {
                "type": "pane_agent_status_changed",
                "pane_id": "w1:p1",
                "workspace_id": "w1",
                "agent_status": "done",
                "agent": "claude",
            },
        }
        self.assertEqual(recent.extract_event(obj), ("w1:p1", "done"))

    def test_missing_data(self):
        self.assertEqual(recent.extract_event({"event": "x"}), (None, None))

    def test_missing_fields(self):
        self.assertEqual(
            recent.extract_event({"data": {"pane_id": "w1:p1"}}), (None, None)
        )
        self.assertEqual(
            recent.extract_event({"data": {"agent_status": "idle"}}), (None, None)
        )

    def test_non_dict(self):
        self.assertEqual(recent.extract_event(None), (None, None))
        self.assertEqual(recent.extract_event("nope"), (None, None))


class ParseRecentsTest(unittest.TestCase):
    def test_full_lines(self):
        text = "111\tw1:p1\tdone\n222\tw2:p5\tidle\n"
        self.assertEqual(recent.parse_recents(text), ["w1:p1", "w2:p5"])

    def test_blank_and_bare_lines(self):
        text = "\n  \nw5:p1\n333\tw1:p1\tblocked\n"
        self.assertEqual(recent.parse_recents(text), ["w5:p1", "w1:p1"])

    def test_empty(self):
        self.assertEqual(recent.parse_recents(""), [])


class NewestUniqueTest(unittest.TestCase):
    def test_dedup_keeps_recent(self):
        # oldest -> newest: A, B, A  => newest-first unique: A, B
        self.assertEqual(recent.newest_unique(["A", "B", "A"]), ["A", "B"])

    def test_order(self):
        self.assertEqual(
            recent.newest_unique(["w1:p1", "w2:p5", "w5:p1"]),
            ["w5:p1", "w2:p5", "w1:p1"],
        )

    def test_empty(self):
        self.assertEqual(recent.newest_unique([]), [])


class WaitingPanesTest(unittest.TestCase):
    def test_keeps_only_attention_states_in_order(self):
        order = ["w5:p1", "w2:p5", "w1:p1"]  # newest-first
        live = {"w5:p1": "done", "w2:p5": "working", "w1:p1": "blocked"}
        self.assertEqual(recent.waiting_panes(order, live), ["w5:p1", "w1:p1"])

    def test_idle_is_not_an_attention_state(self):
        order = ["w5:p1", "w2:p5"]
        live = {"w5:p1": "idle", "w2:p5": "done"}
        self.assertEqual(recent.waiting_panes(order, live), ["w2:p5"])

    def test_skips_gone_panes(self):
        order = ["w9:p9", "w2:p5"]  # w9:p9 no longer exists
        live = {"w2:p5": "done"}
        self.assertEqual(recent.waiting_panes(order, live), ["w2:p5"])


class NextInCycleTest(unittest.TestCase):
    def test_no_cursor_starts_at_newest(self):
        order = ["w5:p1", "w2:p5", "w1:p1"]
        live = {"w5:p1": "done", "w2:p5": "blocked", "w1:p1": "done"}
        self.assertEqual(recent.next_in_cycle(order, live, None), "w5:p1")

    def test_advances_past_cursor(self):
        order = ["w5:p1", "w2:p5", "w1:p1"]
        live = {"w5:p1": "done", "w2:p5": "blocked", "w1:p1": "done"}
        self.assertEqual(recent.next_in_cycle(order, live, "w5:p1"), "w2:p5")
        self.assertEqual(recent.next_in_cycle(order, live, "w2:p5"), "w1:p1")

    def test_wraps_at_end(self):
        order = ["w5:p1", "w2:p5", "w1:p1"]
        live = {"w5:p1": "done", "w2:p5": "blocked", "w1:p1": "done"}
        self.assertEqual(recent.next_in_cycle(order, live, "w1:p1"), "w5:p1")

    def test_skips_non_waiting_when_advancing(self):
        # cursor's neighbour resumed working -> land on the next waiting one
        order = ["w5:p1", "w2:p5", "w1:p1"]
        live = {"w5:p1": "done", "w2:p5": "working", "w1:p1": "blocked"}
        self.assertEqual(recent.next_in_cycle(order, live, "w5:p1"), "w1:p1")

    def test_stale_cursor_restarts_at_newest(self):
        # cursor pane resumed working (no longer waiting) -> restart at newest
        order = ["w5:p1", "w2:p5", "w1:p1"]
        live = {"w5:p1": "done", "w2:p5": "working", "w1:p1": "blocked"}
        self.assertEqual(recent.next_in_cycle(order, live, "w2:p5"), "w5:p1")
        # cursor pane no longer exists at all -> restart at newest
        self.assertEqual(recent.next_in_cycle(order, live, "w9:p9"), "w5:p1")

    def test_single_waiting_is_idempotent(self):
        order = ["w5:p1", "w2:p5"]
        live = {"w5:p1": "working", "w2:p5": "done"}
        self.assertEqual(recent.next_in_cycle(order, live, "w2:p5"), "w2:p5")

    def test_none_when_nothing_waiting(self):
        order = ["w5:p1", "w2:p5"]
        live = {"w5:p1": "working", "w2:p5": "idle"}
        self.assertIsNone(recent.next_in_cycle(order, live, None))

    def test_none_when_empty(self):
        self.assertIsNone(recent.next_in_cycle([], {"w1:p1": "done"}, None))


class TrimTextTest(unittest.TestCase):
    def test_keeps_last_n(self):
        text = "".join(f"{i}\tw1:p{i}\tidle\n" for i in range(10))
        out = recent.trim_text(text, 3)
        self.assertEqual(out.splitlines(), ["7\tw1:p7\tidle", "8\tw1:p8\tidle", "9\tw1:p9\tidle"])
        self.assertTrue(out.endswith("\n"))

    def test_drops_blank_lines(self):
        self.assertEqual(recent.trim_text("\n\n", 5), "")

    def test_under_limit_unchanged(self):
        text = "1\tw1:p1\tidle\n2\tw2:p5\tdone\n"
        self.assertEqual(recent.trim_text(text, 5).splitlines(), text.splitlines())


if __name__ == "__main__":
    unittest.main()
