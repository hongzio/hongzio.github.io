import unittest
import panel


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
