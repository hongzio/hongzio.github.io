#!/usr/bin/env python3
"""Unit tests for the pure logic in picker.py (no herdr / fzf needed).

Run: python3 test_picker.py
"""
import os
import tempfile
import unittest

import picker
from picker import Conversation


class TokenCodec(unittest.TestCase):
    def test_roundtrip(self):
        conv = Conversation(agent="claude", session_id="abc-123", path="/p/x.jsonl",
                            mtime=0.0, cwd="/Users/me/proj")
        back = picker.decode_token(picker.encode_token(conv))
        self.assertEqual((back.agent, back.session_id, back.path, back.cwd),
                         ("claude", "abc-123", "/p/x.jsonl", "/Users/me/proj"))


class TextHelpers(unittest.TestCase):
    def test_message_text_string(self):
        self.assertEqual(picker.message_text("hello"), "hello")

    def test_message_text_blocks(self):
        content = [{"type": "text", "text": "a"}, {"type": "tool_use"}, {"type": "text", "text": "b"}]
        self.assertEqual(picker.message_text(content), "a b")

    def test_message_text_tool_result_empty(self):
        self.assertEqual(picker.message_text([{"type": "tool_result", "content": "x"}]), "")

    def test_synthetic(self):
        self.assertTrue(picker.is_synthetic_user_text("<local-command-caveat>..."))
        self.assertTrue(picker.is_synthetic_user_text("  <command-name>/login</command-name>"))
        self.assertTrue(picker.is_synthetic_user_text("Caveat: blah"))
        self.assertTrue(picker.is_synthetic_user_text("   "))
        self.assertFalse(picker.is_synthetic_user_text("real question?"))

    def test_clean_label_truncates(self):
        out = picker.clean_label("x" * 200)
        self.assertLessEqual(len(out), picker.LABEL_MAX)
        self.assertTrue(out.endswith("…"))

    def test_rel_time(self):
        now = 1_000_000.0
        self.assertEqual(picker.rel_time(now - 10, now), "방금")
        self.assertEqual(picker.rel_time(now - 120, now), "2분")
        self.assertEqual(picker.rel_time(now - 7200, now), "2시간")
        self.assertEqual(picker.rel_time(now - 100000, now), "어제")
        self.assertEqual(picker.rel_time(now - 300000, now), "3일")


class ResumeCommand(unittest.TestCase):
    def test_claude(self):
        self.assertEqual(picker.resume_command("claude", "id1"), "claude --resume id1")

    def test_codex(self):
        self.assertEqual(picker.resume_command("codex", "id1"), "codex resume id1")

    def test_unknown(self):
        with self.assertRaises(ValueError):
            picker.resume_command("wat", "id1")


class DecideAction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_focus_when_active(self):
        conv = Conversation("claude", "sess1", "/p", 0.0, cwd=self.tmp)
        action = picker.decide_action(conv, {"sess1": "w1:p3"}, {})
        self.assertEqual(action, {"kind": "focus", "pane_id": "w1:p3"})

    def test_new_tab_when_space_matches(self):
        conv = Conversation("claude", "sess1", "/p", 0.0, cwd=self.tmp + "/")  # trailing slash
        spaces = {os.path.realpath(self.tmp): "w2"}
        action = picker.decide_action(conv, {}, spaces)
        self.assertEqual(action["kind"], "new_tab")
        self.assertEqual(action["workspace_id"], "w2")
        self.assertEqual(action["cwd"], os.path.realpath(self.tmp))

    def test_new_space_when_no_match(self):
        conv = Conversation("codex", "sess1", "/p", 0.0, cwd=self.tmp)
        action = picker.decide_action(conv, {}, {"/somewhere/else": "w9"})
        self.assertEqual(action["kind"], "new_space")
        self.assertEqual(action["cwd"], os.path.realpath(self.tmp))

    def test_active_takes_priority_over_space(self):
        conv = Conversation("claude", "sess1", "/p", 0.0, cwd=self.tmp)
        spaces = {os.path.realpath(self.tmp): "w2"}
        action = picker.decide_action(conv, {"sess1": "w1:p3"}, spaces)
        self.assertEqual(action["kind"], "focus")


class ClaudeParsing(unittest.TestCase):
    def test_enrich_skips_synthetic_label(self):
        path = os.path.join(tempfile.mkdtemp(), "s.jsonl")
        with open(path, "w") as fh:
            fh.write('{"type":"user","message":{"content":"<local-command-caveat>x"},"cwd":"/tmp/proj"}\n')
            fh.write('{"type":"user","message":{"content":"the real question"}}\n')
        conv = Conversation("claude", "s", path, 0.0)
        picker.claude_enrich(conv)
        self.assertEqual(conv.cwd, "/tmp/proj")
        self.assertEqual(conv.label, "the real question")

    def _write(self, lines):
        path = os.path.join(tempfile.mkdtemp(), "s.jsonl")
        with open(path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        return path

    def test_custom_title_wins(self):
        path = self._write([
            '{"type":"user","message":{"content":"first msg"},"cwd":"/p"}',
            '{"type":"ai-title","aiTitle":"AI made this"}',
            '{"type":"custom-title","customTitle":"My Name"}',
        ])
        conv = Conversation("claude", "s", path, 0.0)
        picker.claude_enrich(conv)
        self.assertEqual(conv.label, "My Name")

    def test_ai_title_when_no_custom(self):
        path = self._write([
            '{"type":"user","message":{"content":"first msg"},"cwd":"/p"}',
            '{"type":"ai-title","aiTitle":"AI made this"}',
        ])
        conv = Conversation("claude", "s", path, 0.0)
        picker.claude_enrich(conv)
        self.assertEqual(conv.label, "AI made this")

    def test_last_custom_title_wins(self):
        path = self._write([
            '{"type":"custom-title","customTitle":"old"}',
            '{"type":"custom-title","customTitle":"new"}',
        ])
        conv = Conversation("claude", "s", path, 0.0)
        picker.claude_enrich(conv)
        self.assertEqual(conv.label, "new")


class SourceAvailability(unittest.TestCase):
    def setUp(self):
        self._cp, self._cs = picker.CLAUDE_PROJECTS, picker.CODEX_SESSIONS

    def tearDown(self):
        picker.CLAUDE_PROJECTS, picker.CODEX_SESSIONS = self._cp, self._cs

    def test_none_present(self):
        picker.CLAUDE_PROJECTS = "/no/claude/xyz"
        picker.CODEX_SESSIONS = "/no/codex/xyz"
        self.assertEqual(picker.available_sources(), [])

    def test_only_one_present(self):
        picker.CLAUDE_PROJECTS = tempfile.mkdtemp()
        picker.CODEX_SESSIONS = "/no/codex/xyz"
        self.assertEqual([n for n, _ in picker.available_sources()], ["claude"])

        picker.CLAUDE_PROJECTS = "/no/claude/xyz"
        picker.CODEX_SESSIONS = tempfile.mkdtemp()
        self.assertEqual([n for n, _ in picker.available_sources()], ["codex"])


class ModeSelection(unittest.TestCase):
    def setUp(self):
        import shutil
        self.saved = (picker.available_sources, picker._run_fzf,
                      picker._run_python_picker, shutil.which)
        picker.available_sources = lambda: [("claude", None)]
        picker._run_fzf = lambda: "FZF"
        picker._run_python_picker = lambda: "NATIVE"
        self._env = os.environ.get("CONV_PICKER_MODE")

    def tearDown(self):
        import shutil
        (picker.available_sources, picker._run_fzf,
         picker._run_python_picker, shutil.which) = self.saved
        if self._env is None:
            os.environ.pop("CONV_PICKER_MODE", None)
        else:
            os.environ["CONV_PICKER_MODE"] = self._env

    def _set(self, mode, fzf):
        import shutil
        if mode is None:
            os.environ.pop("CONV_PICKER_MODE", None)
        else:
            os.environ["CONV_PICKER_MODE"] = mode
        shutil.which = lambda _x: "/bin/fzf" if fzf else None

    def test_native_forces_native_even_with_fzf(self):
        self._set("native", True)
        self.assertEqual(picker.cmd_ui(), "NATIVE")

    def test_fzf_forces_fzf(self):
        self._set("fzf", True)
        self.assertEqual(picker.cmd_ui(), "FZF")

    def test_fzf_missing_errors(self):
        self._set("fzf", False)
        self.assertEqual(picker.cmd_ui(), 1)

    def test_auto_prefers_fzf(self):
        self._set("auto", True)
        self.assertEqual(picker.cmd_ui(), "FZF")

    def test_auto_falls_back_to_native(self):
        self._set("auto", False)
        self.assertEqual(picker.cmd_ui(), "NATIVE")

    def test_unset_defaults_to_auto(self):
        self._set(None, True)
        self.assertEqual(picker.cmd_ui(), "FZF")


class FallbackPicker(unittest.TestCase):
    ROWS = [
        ("claude proj herdr favorites", "row a", "tokA", False),
        ("codex backend login session", "row b", "tokB", True),
        ("claude zim vim plugin", "row c", "tokC", False),
    ]

    def test_filter_empty_returns_all(self):
        self.assertEqual(picker.filter_rows(self.ROWS, ""), self.ROWS)

    def test_filter_substring_case_insensitive(self):
        out = picker.filter_rows(self.ROWS, "HERDR")
        self.assertEqual([r[2] for r in out], ["tokA"])

    def test_filter_matches_agent_and_space(self):
        self.assertEqual([r[2] for r in picker.filter_rows(self.ROWS, "claude")], ["tokA", "tokC"])
        self.assertEqual([r[2] for r in picker.filter_rows(self.ROWS, "backend")], ["tokB"])

    def test_filter_no_match(self):
        self.assertEqual(picker.filter_rows(self.ROWS, "zzz"), [])

    def test_fit_width_ascii(self):
        self.assertEqual(picker._fit_width("hello", 10), "hello")
        self.assertEqual(picker._fit_width("hello world", 5), "hell…")

    def test_fit_width_wide_chars(self):
        # 한글 = 2 cols each; 3 chars = 6 cols, fits in 6
        self.assertEqual(picker._disp_width("한글날"), 6)
        self.assertLessEqual(picker._disp_width(picker._fit_width("한글날씨좋다", 6)), 6)


class OpenGuards(unittest.TestCase):
    def setUp(self):
        self._active, self._space = picker.active_session_map, picker.space_cwd_map
        picker.active_session_map = lambda: {}
        picker.space_cwd_map = lambda: {}

    def tearDown(self):
        picker.active_session_map, picker.space_cwd_map = self._active, self._space

    def test_missing_cli_blocks_restore(self):
        # agent whose CLI is not on PATH -> restore refused, no herdr effects
        conv = Conversation("nonexistent-cli-xyz", "s", "/p", 0.0, cwd=tempfile.mkdtemp())
        self.assertEqual(picker.cmd_open(picker.encode_token(conv)), 1)

    def test_missing_directory_blocks_restore(self):
        conv = Conversation("claude", "s", "/p", 0.0, cwd="/no/such/dir/xyz")
        self.assertEqual(picker.cmd_open(picker.encode_token(conv)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
