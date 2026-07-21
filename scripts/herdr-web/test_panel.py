import unittest
from unittest import mock

import panel


class TestCopy(unittest.TestCase):
    def test_pipes_text_to_pbcopy_and_reports_success(self):
        with mock.patch.object(panel.subprocess, "run",
                               return_value=mock.Mock(returncode=0)) as run:
            self.assertTrue(panel._copy("hunter2"))
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["pbcopy"])
        self.assertEqual(run.call_args.kwargs["input"], b"hunter2")

    def test_nonzero_exit_is_failure(self):
        with mock.patch.object(panel.subprocess, "run",
                               return_value=mock.Mock(returncode=1)):
            self.assertFalse(panel._copy("x"))

    def test_pbcopy_missing_is_failure_not_raise(self):
        with mock.patch.object(panel.subprocess, "run", side_effect=FileNotFoundError):
            self.assertFalse(panel._copy("x"))


class TestTunnelState(unittest.TestCase):
    def test_off_when_local_down(self):
        self.assertEqual(panel._tunnel_state(False, True, None, None), ("OFF", "(tunnel off)"))

    def test_off_when_disabled(self):
        self.assertEqual(panel._tunnel_state(True, False, None, None), ("OFF", "(tunnel off)"))

    def test_coming_up_shows_starting(self):
        txt, disp = panel._tunnel_state(True, True, None, 555)
        self.assertIn("starting...", txt)
        self.assertIn("555", txt)
        self.assertEqual(disp, "(coming up...)")

    def test_coming_up_without_pid(self):
        txt, disp = panel._tunnel_state(True, True, None, None)
        self.assertEqual(txt, "starting...")
        self.assertEqual(disp, "(coming up...)")

    def test_fully_up_drops_starting_and_shows_url(self):
        url = "https://x.trycloudflare.com"
        txt, disp = panel._tunnel_state(True, True, url, 555)
        self.assertNotIn("starting", txt)
        self.assertEqual(txt, "ON  (pid 555)")
        self.assertEqual(disp, url)

    def test_failure_status_replaces_stuck_starting(self):
        txt, disp = panel._tunnel_state(
            True, True, None, None, "cloudflared not found — brew install cloudflared")
        self.assertEqual(txt, "unavailable")
        self.assertIn("cloudflared not found", disp)

    def test_status_ignored_while_process_alive(self):
        # A stale status shouldn't override a genuinely coming-up tunnel (pid alive).
        txt, disp = panel._tunnel_state(True, True, None, 555, "stale error")
        self.assertIn("starting...", txt)

    def test_status_ignored_once_url_is_up(self):
        url = "https://x.trycloudflare.com"
        txt, disp = panel._tunnel_state(True, True, url, 555, "stale error")
        self.assertEqual(disp, url)


class _SyncThread:
    """Stand-in for threading.Thread that runs the target inline on start(), so the
    worker body is exercised deterministically (no join races) in tests."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


class TestSpawnWorkers(unittest.TestCase):
    def test_test_send_success(self):
        state = {"busy": True, "msg": ""}
        with mock.patch.object(panel.threading, "Thread", _SyncThread), \
             mock.patch.object(panel.notify, "send", return_value=(True, "sent")):
            panel._spawn_test(state, "telegram", {"bot_token": "T"}, "hi")
        self.assertFalse(state["busy"])
        self.assertIn("sent", state["msg"])

    def test_test_send_exception_is_isolated(self):
        state = {"busy": True, "msg": ""}
        with mock.patch.object(panel.threading, "Thread", _SyncThread), \
             mock.patch.object(panel.notify, "send", side_effect=RuntimeError("boom")):
            panel._spawn_test(state, "telegram", {}, "hi")  # must not raise
        self.assertFalse(state["busy"])          # thread still cleared busy
        self.assertIn("boom", state["msg"])

    def test_fetch_success_stashes_fields(self):
        state = {"busy": True, "msg": "", "fetched": None}
        with mock.patch.object(panel.threading, "Thread", _SyncThread), \
             mock.patch.object(panel.notify, "fetch",
                               return_value=(True, {"chat_id": "5", "topic_id": "9"}, "G")):
            panel._spawn_fetch(state, "telegram", {"bot_token": "T"})
        self.assertEqual(state["fetched"], {"chat_id": "5", "topic_id": "9"})
        self.assertFalse(state["busy"])
        self.assertIn("chat_id 5", state["msg"])

    def test_fetch_exception_is_isolated(self):
        state = {"busy": True, "msg": "", "fetched": None}
        with mock.patch.object(panel.threading, "Thread", _SyncThread), \
             mock.patch.object(panel.notify, "fetch", side_effect=RuntimeError("boom")):
            panel._spawn_fetch(state, "telegram", {})  # must not raise
        self.assertFalse(state["busy"])
        self.assertIsNone(state["fetched"])          # nothing to apply on failure
        self.assertIn("boom", state["msg"])


if __name__ == "__main__":
    unittest.main()
