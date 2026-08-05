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


class TestIsValidAgentName(unittest.TestCase):
    def test_accepts_herdr_slugs(self):
        for name in ("a", "backend", "backend-refactor", "web_2", "x" * 32):
            self.assertTrue(titles.is_valid_agent_name(name), name)

    def test_rejects_what_herdr_rejects(self):
        for name in ("", "Backend", "2fast", "-lead", "has space", "백엔드", "x" * 33):
            self.assertFalse(titles.is_valid_agent_name(name), name)


class TestNameToken(unittest.TestCase):
    def test_name_passes_through(self):
        self.assertEqual(titles.name_token("backend"), "backend")

    def test_empty_when_unset(self):
        # empty clears the token, so an unnamed agent shows nothing on its row
        self.assertEqual(titles.name_token(""), "")
        self.assertEqual(titles.name_token(None), "")
        self.assertEqual(titles.name_token("   "), "")


class TestContextPane(unittest.TestCase):
    def test_focused_pane_id(self):
        ctx = json.dumps({"tab_id": "w1:t1", "focused_pane_id": "w1:p3",
                          "focused_pane_agent": "claude"})
        self.assertEqual(titles.context_pane(ctx), "w1:p3")

    def test_empty_when_absent_or_junk(self):
        self.assertEqual(titles.context_pane(""), "")
        self.assertEqual(titles.context_pane("not json"), "")
        self.assertEqual(titles.context_pane(json.dumps({"tab_id": "w1:t1"})), "")


class TestResolveTargetPane(unittest.TestCase):
    AGENTS = [{"pane_id": "w1:p1", "focused": False}, {"pane_id": "w2:p3", "focused": True}]

    def test_caller_pane_wins(self):
        self.assertEqual(titles.resolve_target_pane(self.AGENTS, "w1:p1"), "w1:p1")

    def test_focused_agent_when_no_caller_pane(self):
        self.assertEqual(titles.resolve_target_pane(self.AGENTS, ""), "w2:p3")

    def test_caller_pane_without_agent_never_retargets(self):
        # a keypress from a shell pane must not rename somebody else's agent
        self.assertEqual(titles.resolve_target_pane(self.AGENTS, "w1:p9"), "")

    def test_empty_when_nothing_focused(self):
        self.assertEqual(titles.resolve_target_pane([{"pane_id": "w1:p1"}], ""), "")
        self.assertEqual(titles.resolve_target_pane([], ""), "")


class TestErrorMessage(unittest.TestCase):
    def test_extracts_herdr_error_message(self):
        err = json.dumps({"error": {"code": "invalid_agent_name", "message": "bad slug"},
                          "id": "cli:agent:rename"})
        self.assertEqual(titles.error_message(err), "bad slug")

    def test_falls_back_to_raw_line(self):
        self.assertEqual(titles.error_message("boom\n"), "boom")

    def test_falls_back_across_streams(self):
        self.assertEqual(titles.error_message("", "  \n", "from stdout"), "from stdout")

    def test_default_when_silent(self):
        self.assertEqual(titles.error_message("", ""), "rename failed")


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
