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

class TestCreds(unittest.TestCase):
    def test_check_creds(self):
        self.assertTrue(authstate.check_creds("herdr", "s3cret", "herdr", "s3cret"))
        self.assertFalse(authstate.check_creds("herdr", "nope", "herdr", "s3cret"))
        self.assertFalse(authstate.check_creds("nope", "s3cret", "herdr", "s3cret"))

class TestSession(unittest.TestCase):
    def test_roundtrip(self):
        t = authstate.make_session("herdr", "s3cret")
        self.assertTrue(authstate.valid_session("herdr", "s3cret", t))

    def test_cred_rotation_invalidates(self):
        t = authstate.make_session("herdr", "s3cret")
        self.assertFalse(authstate.valid_session("herdr", "rotated", t))  # new password
        self.assertFalse(authstate.valid_session("other", "s3cret", t))   # new username

    def test_malformed_token(self):
        self.assertFalse(authstate.valid_session("herdr", "s3cret", None))
        self.assertFalse(authstate.valid_session("herdr", "s3cret", ""))
        self.assertFalse(authstate.valid_session("herdr", "s3cret", "no-dot"))
        self.assertFalse(authstate.valid_session("herdr", "s3cret", ".sigonly"))

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
