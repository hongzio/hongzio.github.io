import os, tempfile, unittest
import authstate

class TestAuth(unittest.TestCase):
    def test_valid(self):
        h = authstate.basic_auth_header("herdr", "s3cret")
        self.assertTrue(authstate.check_basic_auth(h, "herdr", "s3cret"))

    def test_wrong_password(self):
        h = authstate.basic_auth_header("herdr", "nope")
        self.assertFalse(authstate.check_basic_auth(h, "herdr", "s3cret"))

    def test_missing_or_malformed(self):
        self.assertFalse(authstate.check_basic_auth(None, "u", "p"))
        self.assertFalse(authstate.check_basic_auth("Bearer x", "u", "p"))
        self.assertFalse(authstate.check_basic_auth("Basic !!notb64", "u", "p"))

class TestPid(unittest.TestCase):
    def test_self_is_running(self):
        with tempfile.TemporaryDirectory() as d:
            pf = os.path.join(d, "pid")
            authstate.write_pid(pf, os.getpid())
            self.assertEqual(authstate.is_running(pf), os.getpid())

    def test_dead_pid_not_running(self):
        with tempfile.TemporaryDirectory() as d:
            pf = os.path.join(d, "pid")
            authstate.write_pid(pf, 2_000_000_000)  # implausible pid
            self.assertIsNone(authstate.is_running(pf))

    def test_missing_pidfile(self):
        self.assertIsNone(authstate.is_running("/nonexistent/pid"))

if __name__ == "__main__":
    unittest.main()
