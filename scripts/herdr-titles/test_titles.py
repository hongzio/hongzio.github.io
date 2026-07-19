import json
import unittest
from unittest import mock

import titles


class TestMessageText(unittest.TestCase):
    def test_plain_string(self):
        self.assertEqual(titles.message_text("hi"), "hi")

    def test_content_blocks(self):
        content = [{"type": "text", "text": "a"}, {"type": "input_text", "text": "b"}]
        self.assertEqual(titles.message_text(content), "a b")

    def test_non_text_blocks_ignored(self):
        content = [{"type": "image"}, {"type": "text", "text": "only"}]
        self.assertEqual(titles.message_text(content), "only")


class TestCleanTitle(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(titles.clean_title("  a   b\n c "), "a b c")

    def test_truncates_with_ellipsis(self):
        out = titles.clean_title("x" * 100)
        self.assertEqual(len(out), titles.TITLE_MAX)
        self.assertTrue(out.endswith("…"))


class TestCleanTabLabel(unittest.TestCase):
    def test_truncates_to_tab_cap(self):
        out = titles.clean_tab_label("x" * 100)
        self.assertEqual(len(out), titles.TAB_LABEL_MAX)
        self.assertTrue(out.endswith("…"))

    def test_short_label_untouched(self):
        self.assertEqual(titles.clean_tab_label("data-onboard"), "data-onboard")


class TestAgentTabLabel(unittest.TestCase):
    def test_prefixes_robot(self):
        self.assertEqual(titles.agent_tab_label("data-onboard"),
                         titles.AGENT_TAB_PREFIX + "data-onboard")

    def test_cap_applies_to_title_not_prefix(self):
        out = titles.agent_tab_label("x" * 100)
        self.assertTrue(out.startswith(titles.AGENT_TAB_PREFIX))
        self.assertEqual(out[len(titles.AGENT_TAB_PREFIX):], "x" * (titles.TAB_LABEL_MAX - 1) + "…")

    def test_empty_title_yields_no_label(self):
        self.assertEqual(titles.agent_tab_label(""), "")


class TestParseTabRename(unittest.TestCase):
    def test_default_on_when_absent(self):
        self.assertTrue(titles.parse_tab_rename(""))
        self.assertTrue(titles.parse_tab_rename("[tab]\n"))
        self.assertTrue(titles.parse_tab_rename("[other]\nrename = false\n"))

    def test_explicit_false_disables(self):
        self.assertFalse(titles.parse_tab_rename("[tab]\nrename = false\n"))
        self.assertFalse(titles.parse_tab_rename("[tab]\nrename = off  # comment\n"))

    def test_explicit_true(self):
        self.assertTrue(titles.parse_tab_rename("[tab]\nrename = true\n"))

    def test_quoted_and_whitespace(self):
        self.assertFalse(titles.parse_tab_rename("[tab]\n  rename   =  'false' \n"))

    def test_rename_outside_tab_section_ignored(self):
        self.assertTrue(titles.parse_tab_rename("rename = false\n[tab]\n"))


class TestHumanizeAgo(unittest.TestCase):
    def test_just_now(self):
        self.assertEqual(titles.humanize_ago(0), "just now")
        self.assertEqual(titles.humanize_ago(29), "just now")   # <30s rounds to 0 min

    def test_minutes_round_half_up(self):
        self.assertEqual(titles.humanize_ago(30), "1m ago")     # 0.5 -> 1
        self.assertEqual(titles.humanize_ago(60), "1m ago")
        self.assertEqual(titles.humanize_ago(89), "1m ago")     # 1.48 -> 1
        self.assertEqual(titles.humanize_ago(90), "2m ago")     # 1.5 -> 2

    def test_hours_round_on_minutes(self):
        # the spec's examples: 3h29m -> 3h ago, 3h31m -> 4h ago
        self.assertEqual(titles.humanize_ago(3 * 3600 + 29 * 60), "3h ago")
        self.assertEqual(titles.humanize_ago(3 * 3600 + 31 * 60), "4h ago")

    def test_days_and_weeks(self):
        self.assertEqual(titles.humanize_ago(3 * 86400 + 11 * 3600), "3d ago")  # 3.46 -> 3
        self.assertEqual(titles.humanize_ago(3 * 86400 + 13 * 3600), "4d ago")  # 3.54 -> 4
        self.assertEqual(titles.humanize_ago(9 * 86400), "1w ago")              # 9d -> 1.29w -> 1

    def test_carry_up_to_next_unit(self):
        self.assertEqual(titles.humanize_ago(59 * 60 + 40), "1h ago")           # 59.67m -> 60 -> 1h
        self.assertEqual(titles.humanize_ago(23 * 3600 + 59 * 60), "1d ago")    # ~24h -> 1d


class TestSecondsToNextAgoChange(unittest.TestCase):
    def _flips_at(self, age):
        """The string humanize_ago renders at `age` differs from at `age + dt`."""
        dt = titles.seconds_to_next_ago_change(age)
        before = titles.humanize_ago(age)
        # just below the boundary the string still matches; at/above it differs
        self.assertEqual(titles.humanize_ago(age + dt - 0.5), before)
        self.assertNotEqual(titles.humanize_ago(age + dt + 0.5), before)
        return dt

    def test_just_now_flips_to_1m_at_30s(self):
        self.assertAlmostEqual(titles.seconds_to_next_ago_change(0), 30.0)

    def test_minute_bucket_ticks_about_once_a_minute(self):
        dt = self._flips_at(5 * 60)          # "5m ago"
        self.assertLessEqual(dt, 60.0)

    def test_hour_bucket_ticks_about_once_an_hour(self):
        dt = self._flips_at(3 * 3600)        # "3h ago" -> "4h ago" at 3.5h
        self.assertAlmostEqual(dt, 1800.0)

    def test_day_bucket_ticks_about_once_a_day(self):
        dt = self._flips_at(2 * 86400)       # "2d ago"
        self.assertGreater(dt, 3600.0)

    def test_never_returns_nonpositive(self):
        for age in (0, 29, 30, 59, 3599, 3600, 86399, 700000):
            self.assertGreaterEqual(titles.seconds_to_next_ago_change(age), 1.0)

    def test_across_unit_rollover(self):
        # ~59.7m renders as "1h"; next flip is at 1.5h, not a minute away
        self._flips_at(59 * 60 + 40)


class TestLastActivityTs(unittest.TestCase):
    def _write(self, records):
        import tempfile
        fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
        for r in records:
            fh.write(json.dumps(r) + "\n")
        fh.close()
        self.addCleanup(lambda: __import__("os").remove(fh.name))
        return fh.name

    def test_uses_last_real_turn_not_metadata(self):
        # a real turn yesterday, then rename/restore metadata writes with no/newer stamp
        path = self._write([
            {"type": "assistant", "timestamp": "2026-07-18T13:39:02.000Z"},
            {"type": "custom-title", "customTitle": "New SMO PR"},          # /rename, no ts
            {"type": "agent-name"},
            {"type": "system", "timestamp": "2026-07-19T09:00:00.000Z"},    # restore, not a turn
            {"type": "user", "timestamp": "2026-07-19T09:00:00.000Z",
             "message": {"content": "<system-reminder>named session"}},     # synthetic user
        ])
        ts = titles.last_activity_ts(path)
        self.assertEqual(ts, titles._parse_iso("2026-07-18T13:39:02.000Z"))

    def test_real_user_message_counts(self):
        path = self._write([
            {"type": "assistant", "timestamp": "2026-07-18T10:00:00.000Z"},
            {"type": "user", "timestamp": "2026-07-18T12:00:00.000Z",
             "message": {"content": "do the thing"}},
        ])
        self.assertEqual(titles.last_activity_ts(path),
                         titles._parse_iso("2026-07-18T12:00:00.000Z"))

    def test_no_turns_returns_zero(self):
        path = self._write([{"type": "custom-title", "customTitle": "x"}])
        self.assertEqual(titles.last_activity_ts(path), 0.0)


class TestParseIso(unittest.TestCase):
    def test_z_suffix(self):
        self.assertGreater(titles._parse_iso("2026-07-18T13:39:02.000Z"), 0)

    def test_garbage_is_zero(self):
        self.assertEqual(titles._parse_iso("not-a-date"), 0.0)
        self.assertEqual(titles._parse_iso(""), 0.0)


class TestIsShellTitle(unittest.TestCase):
    def test_shell_prompt_is_shell(self):
        self.assertTrue(titles.is_shell_title("hongzio@host:~/Projects/x"))

    def test_task_summary_is_not_shell(self):
        self.assertFalse(titles.is_shell_title("온보드 페이지 다시 만들기"))
        self.assertFalse(titles.is_shell_title("New Balancer Impl"))


class TestClaudeTitles(unittest.TestCase):
    def test_custom_title_is_explicit_and_wins(self):
        recs = [
            {"type": "user", "message": {"content": "first task"}},
            {"type": "ai-title", "aiTitle": "AI summary"},
            {"type": "custom-title", "customTitle": "My Name"},
        ]
        self.assertEqual(titles.claude_titles(recs), ("My Name", "AI summary"))

    def test_derived_is_ai_over_first_user(self):
        recs = [
            {"type": "user", "message": {"content": "first task"}},
            {"type": "ai-title", "aiTitle": "AI summary"},
        ]
        self.assertEqual(titles.claude_titles(recs), ("", "AI summary"))

    def test_derived_falls_back_to_first_user(self):
        recs = [{"type": "user", "message": {"content": "build the thing"}}]
        self.assertEqual(titles.claude_titles(recs), ("", "build the thing"))

    def test_skips_synthetic_user_records(self):
        recs = [
            {"type": "user", "message": {"content": "<command-name>/clear"}},
            {"type": "user", "message": {"content": "real request"}},
        ]
        self.assertEqual(titles.claude_titles(recs), ("", "real request"))

    def test_empty_when_nothing(self):
        self.assertEqual(titles.claude_titles([]), ("", ""))


class TestCodexTitles(unittest.TestCase):
    def test_thread_name_is_explicit(self):
        recs = [{"type": "response_item", "payload": {"role": "user", "content": "hi"}}]
        self.assertEqual(titles.codex_titles(recs, "Named Thread"), ("Named Thread", "hi"))

    def test_first_user_message_is_derived(self):
        recs = [
            {"type": "session_meta", "payload": {"cwd": "/x"}},
            {"type": "response_item", "payload": {"role": "user",
                                                  "content": [{"type": "input_text", "text": "do it"}]}},
        ]
        self.assertEqual(titles.codex_titles(recs, ""), ("", "do it"))

    def test_skips_synthetic(self):
        recs = [
            {"type": "response_item", "payload": {"role": "user", "content": "<system-reminder>x"}},
            {"type": "response_item", "payload": {"role": "user", "content": "actual"}},
        ]
        self.assertEqual(titles.codex_titles(recs, ""), ("", "actual"))


class TestPickCodexSession(unittest.TestCase):
    def test_newest_matching_cwd_wins(self):
        entries = [
            {"id": "old", "cwd": "/repo", "updated_at": "2026-07-18T10:00:00Z"},
            {"id": "new", "cwd": "/repo", "updated_at": "2026-07-19T10:00:00Z"},
            {"id": "other", "cwd": "/elsewhere", "updated_at": "2026-07-20T10:00:00Z"},
        ]
        self.assertEqual(titles.pick_codex_session(entries, "/repo"), "new")

    def test_no_match_returns_none(self):
        entries = [{"id": "x", "cwd": "/a", "updated_at": "1"}]
        self.assertIsNone(titles.pick_codex_session(entries, "/b"))
        self.assertIsNone(titles.pick_codex_session([], "/a"))

    def test_empty_cwd_never_matches(self):
        self.assertIsNone(titles.pick_codex_session([{"id": "x", "cwd": "", "updated_at": "1"}], ""))


class TestCodexThreadName(unittest.TestCase):
    def _index(self, lines):
        import tempfile
        fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
        for r in lines:
            fh.write(json.dumps(r) + "\n")
        fh.close()
        self.addCleanup(lambda: __import__("os").remove(fh.name))
        return fh.name

    def test_latest_rename_wins(self):
        # append-only index: two renames of the same session, newest updated_at wins
        path = self._index([
            {"id": "s1", "thread_name": "ttt123", "updated_at": "2026-07-18T22:30:46Z"},
            {"id": "s1", "thread_name": "ttt234", "updated_at": "2026-07-18T22:45:45Z"},
            {"id": "other", "thread_name": "nope", "updated_at": "2026-07-19T00:00:00Z"},
        ])
        with mock.patch.object(titles, "CODEX_INDEX", path):
            self.assertEqual(titles.codex_thread_name("s1"), "ttt234")

    def test_missing_session_is_empty(self):
        path = self._index([{"id": "s1", "thread_name": "x", "updated_at": "1"}])
        with mock.patch.object(titles, "CODEX_INDEX", path):
            self.assertEqual(titles.codex_thread_name("s2"), "")


class TestResolveSession(unittest.TestCase):
    def test_agent_session_value_used_directly(self):
        pane = {"agent": "claude", "agent_session": {"value": "sid1"}}
        self.assertEqual(titles.resolve_session(pane), ("claude", "sid1"))

    def test_codex_falls_back_to_cwd_when_unbound(self):
        pane = {"agent": "codex", "cwd": "/repo"}  # herdr never bound a session
        with mock.patch.object(titles, "codex_session_for_cwd", return_value="cx-sid") as m:
            self.assertEqual(titles.resolve_session(pane), ("codex", "cx-sid"))
            m.assert_called_once_with("/repo")

    def test_claude_without_session_does_not_fall_back(self):
        pane = {"agent": "claude", "cwd": "/repo"}
        with mock.patch.object(titles, "codex_session_for_cwd") as m:
            self.assertEqual(titles.resolve_session(pane), ("claude", None))
            m.assert_not_called()


class TestTitleForPaneWithSess(unittest.TestCase):
    def test_precomputed_sess_skips_lookup(self):
        pane = {"agent": "codex", "terminal_title_stripped": "hongzio.github.io"}
        with mock.patch.object(titles, "session_titles") as m:
            # explicit thread_name passed in beats the cwd-basename terminal title
            self.assertEqual(titles.title_for_pane(pane, ("ttt123", "")), "ttt123")
            m.assert_not_called()


class TestEventPaneId(unittest.TestCase):
    def test_extracts_pane_id(self):
        obj = {"event": "pane_agent_status_changed",
               "data": {"pane_id": "w1:p3", "agent_status": "working"}}
        self.assertEqual(titles.event_pane_id(obj), "w1:p3")

    def test_none_when_missing(self):
        self.assertIsNone(titles.event_pane_id({"data": {}}))
        self.assertIsNone(titles.event_pane_id({}))
        self.assertIsNone(titles.event_pane_id("nope"))


class TestTitleForPane(unittest.TestCase):
    def _pane(self, tt="", sess="s1", agent="claude"):
        p = {"agent": agent, "agent_session": {"value": sess}}
        if tt:
            p["terminal_title_stripped"] = tt
        return p

    def test_explicit_rename_beats_terminal_title(self):
        # the whole point: /rename must win over Claude's live terminal summary.
        pane = self._pane(tt="Live auto summary")
        with mock.patch.object(titles, "session_titles", return_value=("data-onboard", "first msg")):
            self.assertEqual(titles.title_for_pane(pane), "data-onboard")

    def test_terminal_title_beats_derived_when_no_explicit(self):
        pane = self._pane(tt="Refactor auth")
        with mock.patch.object(titles, "session_titles", return_value=("", "old first msg")):
            self.assertEqual(titles.title_for_pane(pane), "Refactor auth")

    def test_derived_used_when_terminal_is_shell_default(self):
        pane = self._pane(tt="hongzio@host:~/Projects/x")
        with mock.patch.object(titles, "session_titles", return_value=("", "build the thing")):
            self.assertEqual(titles.title_for_pane(pane), "build the thing")

    def test_no_agent_session_yields_empty(self):
        pane = {"terminal_title_stripped": "hongzio@host:~/Projects/x"}
        self.assertEqual(titles.title_for_pane(pane), "")

    def test_empty_when_no_signal(self):
        self.assertEqual(titles.title_for_pane({}), "")


if __name__ == "__main__":
    unittest.main()
