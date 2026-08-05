#!/usr/bin/env python3
"""Unit tests for the pure half of agents.py (no herdr CLI, no curses)."""
import unittest

import agents


def claude(pane="w1:p1", sid="e45410df-3f1c-442a-ab59-d8eccb27e831", **over):
    a = {"pane_id": pane, "agent": "claude", "workspace_id": pane.split(":")[0],
         "cwd": "/repo", "foreground_cwd": "/repo",
         "agent_session": {"agent": "claude", "kind": "id", "value": sid}}
    a.update(over)
    return a


class TestContextPane(unittest.TestCase):
    def test_reads_focused_pane_id(self):
        self.assertEqual(agents.context_pane('{"focused_pane_id":"w1:p9"}'), "w1:p9")

    def test_tolerates_junk(self):
        for bad in ("", "not json", "[]", '{"focused_pane_id":3}', '{"other":1}'):
            self.assertEqual(agents.context_pane(bad), "")


class TestResolveTarget(unittest.TestCase):
    def setUp(self):
        self.agents = [claude("w1:p1"), claude("w2:p5", focused=True)]

    def test_caller_pane_wins(self):
        self.assertEqual(agents.resolve_target_pane(self.agents, "w1:p1"), "w1:p1")

    def test_caller_without_agent_yields_nothing(self):
        # never silently retarget somebody else's conversation
        self.assertEqual(agents.resolve_target_pane(self.agents, "w9:p9"), "")

    def test_falls_back_to_focused_agent(self):
        self.assertEqual(agents.resolve_target_pane(self.agents, ""), "w2:p5")

    def test_no_agents(self):
        self.assertEqual(agents.resolve_target_pane([], ""), "")


class TestFindAgent(unittest.TestCase):
    def test_found_and_missing(self):
        pool = [claude("w1:p1"), claude("w1:p2")]
        self.assertEqual(agents.find_agent(pool, "w1:p2")["pane_id"], "w1:p2")
        self.assertIsNone(agents.find_agent(pool, "w1:p3"))
        self.assertIsNone(agents.find_agent(pool, ""))


class TestSessionId(unittest.TestCase):
    def test_id_session(self):
        self.assertEqual(agents.session_id(claude(sid="abc")), "abc")

    def test_non_id_session_is_not_usable(self):
        # a transcript path is not something either fork CLI accepts
        a = claude()
        a["agent_session"] = {"kind": "path", "value": "/tmp/x.jsonl"}
        self.assertEqual(agents.session_id(a), "")

    def test_missing_session(self):
        a = claude()
        del a["agent_session"]
        self.assertEqual(agents.session_id(a), "")


class TestForkError(unittest.TestCase):
    def test_forkable(self):
        self.assertEqual(agents.fork_error(claude()), "")

    def test_codex_forkable(self):
        a = claude(agent="codex")
        a["agent_session"]["agent"] = "codex"
        self.assertEqual(agents.fork_error(a), "")

    def test_no_agent(self):
        self.assertIn("no agent", agents.fork_error(None))

    def test_unsupported_kind(self):
        self.assertIn("gemini", agents.fork_error(claude(agent="gemini")))

    def test_no_session_yet(self):
        a = claude()
        a["agent_session"] = {"kind": "id", "value": ""}
        self.assertIn("session id", agents.fork_error(a))

    def test_no_workspace(self):
        self.assertIn("workspace", agents.fork_error(claude(workspace_id="")))


class TestItemError(unittest.TestCase):
    def test_dispatches_to_the_item_checker(self):
        self.assertEqual(agents.item_error("fork", claude()), "")
        self.assertIn("gemini", agents.item_error("fork", claude(agent="gemini")))

    def test_no_agent_fails_every_item(self):
        for item in agents.MENU:
            self.assertIn("no agent", agents.item_error(item.id, None))

    def test_item_without_a_checker_just_needs_an_agent(self):
        self.assertEqual(agents.item_error("not-a-feature", claude()), "")


class TestForkCommand(unittest.TestCase):
    def test_claude(self):
        self.assertEqual(agents.fork_command("claude", "abc-123"),
                         "claude --resume abc-123 --fork-session")

    def test_codex(self):
        self.assertEqual(agents.fork_command("codex", "abc-123"), "codex fork abc-123")

    def test_session_id_is_quoted(self):
        self.assertEqual(agents.fork_command("claude", "a b;rm"),
                         "claude --resume 'a b;rm' --fork-session")


class TestForkCwd(unittest.TestCase):
    def test_prefers_foreground_cwd(self):
        self.assertEqual(agents.fork_cwd(claude(cwd="/a", foreground_cwd="/b")), "/b")

    def test_falls_back_to_pane_cwd(self):
        self.assertEqual(agents.fork_cwd(claude(cwd="/a", foreground_cwd="")), "/a")

    def test_neither(self):
        self.assertEqual(agents.fork_cwd({}), "")


class TestSourceLabel(unittest.TestCase):
    def test_includes_pane_kind_and_title(self):
        label = agents.source_label(claude(terminal_title_stripped="fix the parser"), "w1:p1")
        self.assertIn("w1:p1", label)
        self.assertIn("claude", label)
        self.assertIn("fix the parser", label)

    def test_without_agent(self):
        self.assertEqual(agents.source_label(None, "w1:p1"), "w1:p1")
        self.assertEqual(agents.source_label(None, ""), "(none)")


class TestMenuModel(unittest.TestCase):
    def test_accelerators_are_unique(self):
        keys = [i.key for i in agents.MENU]
        self.assertEqual(len(keys), len(set(keys)))

    def test_accelerators_avoid_reserved_keys(self):
        # the popup eats these itself (quit / vim-style nav), so an item keyed to
        # one of them would simply never fire
        self.assertFalse({i.key for i in agents.MENU} & {"q", "j", "k"})

    def test_accel_index(self):
        self.assertEqual(agents.accel_index(agents.MENU, "f"), 0)
        self.assertEqual(agents.accel_index(agents.MENU, "F"), 0)
        self.assertEqual(agents.accel_index(agents.MENU, "z"), -1)
        self.assertEqual(agents.accel_index(agents.MENU, 27), -1)   # curses key codes

    def test_item_line_mentions_key_and_title(self):
        line = agents.item_line(agents.MENU[0])
        self.assertTrue(line.startswith("f "))
        self.assertIn("fork", line)

    def test_menu_lines_align_descriptions(self):
        items = [agents.Item("a", "a", "short", "desc one"),
                 agents.Item("b", "b", "muchlonger", "desc two")]
        lines = agents.menu_lines(items)
        self.assertEqual(*[line.index("desc") for line in lines])

    def test_every_item_is_runnable(self):
        # the popup spawns `agents.py <item id>`, so an item without a command
        # would be a menu entry that silently does nothing
        for item in agents.MENU:
            self.assertIn(item.id, agents.FEATURE_COMMANDS)


class TestErrorMessage(unittest.TestCase):
    def test_json_error(self):
        self.assertEqual(
            agents.error_message('{"error":{"code":"x","message":"pane is busy"}}'),
            "pane is busy")

    def test_plain_line(self):
        self.assertEqual(agents.error_message("", "boom\nmore"), "boom")

    def test_nothing(self):
        self.assertEqual(agents.error_message("", ""), "failed")


if __name__ == "__main__":
    unittest.main()
