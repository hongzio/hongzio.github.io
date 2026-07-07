#!/usr/bin/env python3
"""Unit tests for the pure helpers in picker.py (file parse/render + display)."""
import unittest

import picker


class ParseFavoritesTest(unittest.TestCase):
    def test_basic(self):
        text = '1 = "w1:t1"\n2 = "w2:t3"\n'
        self.assertEqual(picker.parse_favorites(text), {1: "w1:t1", 2: "w2:t3"})

    def test_blanks_and_comments_ignored(self):
        text = (
            "# header comment\n"
            '1 = "w1:t1"\n'
            '2 = ""\n'          # empty slot -> absent
            '3 = "w1:t2"  # inline\n'
            "\n"
            "junk line without equals\n"
        )
        self.assertEqual(picker.parse_favorites(text), {1: "w1:t1", 3: "w1:t2"})

    def test_out_of_range_and_nondigit_slots_dropped(self):
        text = '0 = "x"\n10 = "y"\nfoo = "z"\n5 = "w1:t5"\n'
        self.assertEqual(picker.parse_favorites(text), {5: "w1:t5"})

    def test_single_quotes_and_whitespace(self):
        text = "  4   =   'w3:t9'   \n"
        self.assertEqual(picker.parse_favorites(text), {4: "w3:t9"})

    def test_round_trip(self):
        slots = {1: "w1:t1", 5: "w2:t2", 9: "w1:tC"}
        self.assertEqual(picker.parse_favorites(picker.render_favorites(slots)), slots)


class RenderFavoritesTest(unittest.TestCase):
    def test_all_slots_emitted(self):
        out = picker.render_favorites({1: "w1:t1"})
        for slot in range(1, picker.SLOT_COUNT + 1):
            self.assertIn(f"{slot} = ", out)
        self.assertIn('1 = "w1:t1"', out)
        self.assertIn('2 = ""', out)

    def test_starts_with_header(self):
        out = picker.render_favorites({})
        self.assertTrue(out.startswith("#"))


class SlotLineTest(unittest.TestCase):
    def setUp(self):
        self.tabs = {
            "w1:t1": {"number": 1, "label": "editor", "workspace_id": "w1"},
            "w1:t2": {"number": None, "label": "", "workspace_id": "w1"},
        }

    def test_empty_slot(self):
        self.assertEqual(picker.slot_line(3, "", self.tabs, ""), "3  —")

    def test_known_tab(self):
        line = picker.slot_line(1, "w1:t1", self.tabs, "")
        self.assertIn("w1 #1 editor", line)

    def test_unnamed_tab_without_number(self):
        line = picker.slot_line(2, "w1:t2", self.tabs, "")
        self.assertIn("(unnamed)", line)

    def test_missing_tab(self):
        line = picker.slot_line(4, "w9:t9", self.tabs, "")
        self.assertIn("(missing)", line)

    def test_current_tab_marker(self):
        line = picker.slot_line(1, "w1:t1", self.tabs, "w1:t1")
        self.assertIn("← current", line)
        other = picker.slot_line(1, "w1:t1", self.tabs, "w1:t2")
        self.assertNotIn("← current", other)


class FocusCommandTest(unittest.TestCase):
    def setUp(self):
        self._load = picker.load_favorites
        self._herdr = picker.herdr
        self.calls = []
        picker.herdr = lambda *a: self.calls.append(a)

    def tearDown(self):
        picker.load_favorites = self._load
        picker.herdr = self._herdr

    def test_bad_and_out_of_range_args_return_2(self):
        picker.load_favorites = lambda: {}
        self.assertEqual(picker.cmd_focus("x"), 2)
        self.assertEqual(picker.cmd_focus("0"), 2)
        self.assertEqual(picker.cmd_focus("10"), 2)
        self.assertEqual(self.calls, [])

    def test_empty_slot_is_noop(self):
        picker.load_favorites = lambda: {}
        self.assertEqual(picker.cmd_focus("3"), 0)
        self.assertEqual(self.calls, [])

    def test_populated_slot_focuses_tab(self):
        picker.load_favorites = lambda: {2: "w1:t7"}
        self.assertEqual(picker.cmd_focus("2"), 0)
        self.assertEqual(self.calls, [("tab", "focus", "w1:t7")])

    def test_missing_tab_swallows_error(self):
        picker.load_favorites = lambda: {1: "w9:t9"}

        def boom(*a):
            raise RuntimeError("tab gone")

        picker.herdr = boom
        self.assertEqual(picker.cmd_focus("1"), 0)  # no crash, exit 0


if __name__ == "__main__":
    unittest.main()
