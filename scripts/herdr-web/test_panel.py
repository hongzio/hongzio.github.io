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


if __name__ == "__main__":
    unittest.main()
