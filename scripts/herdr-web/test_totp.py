import base64
import unittest

import totp

# RFC 6238 appendix B reference secret ("12345678901234567890", SHA1).
_RFC_SECRET = base64.b32encode(b"12345678901234567890").decode("ascii")


class TestRFCVectors(unittest.TestCase):
    def test_known_codes(self):
        # RFC 6238 appendix B publishes 8-digit codes; a 6-digit code is their
        # low-order truncation, so validate the algorithm at 8 digits.
        self.assertEqual(totp.totp_at(_RFC_SECRET, 59, digits=8), "94287082")
        self.assertEqual(totp.totp_at(_RFC_SECRET, 1111111109, digits=8), "07081804")
        self.assertEqual(totp.totp_at(_RFC_SECRET, 1234567890, digits=8), "89005924")
        self.assertEqual(totp.totp_at(_RFC_SECRET, 59), "287082")  # 6-digit truncation


class TestVerify(unittest.TestCase):
    def test_accepts_current_code(self):
        code = totp.totp_at(_RFC_SECRET, 59)
        self.assertTrue(totp.verify(_RFC_SECRET, code, when=59))

    def test_accepts_within_skew(self):
        prev = totp.totp_at(_RFC_SECRET, 59 - 30)   # one step back
        nxt = totp.totp_at(_RFC_SECRET, 59 + 30)    # one step forward
        self.assertTrue(totp.verify(_RFC_SECRET, prev, when=59))
        self.assertTrue(totp.verify(_RFC_SECRET, nxt, when=59))

    def test_rejects_outside_skew(self):
        far = totp.totp_at(_RFC_SECRET, 59 + 90)    # three steps forward
        self.assertFalse(totp.verify(_RFC_SECRET, far, when=59))

    def test_rejects_malformed_input(self):
        for bad in ("", "abcdef", "12345", "1234567", None):
            self.assertFalse(totp.verify(_RFC_SECRET, bad, when=59))

    def test_rejects_bad_secret_without_raising(self):
        self.assertFalse(totp.verify("not base32 !!!", "000000", when=59))


class TestSecret(unittest.TestCase):
    def test_generate_is_valid_base32_and_random(self):
        a, b = totp.generate_secret(), totp.generate_secret()
        self.assertNotEqual(a, b)
        totp._b32decode(a)  # must not raise

    def test_provisioning_uri(self):
        uri = totp.provisioning_uri("ABCD", "bob@host", issuer="herdr-web")
        self.assertTrue(uri.startswith("otpauth://totp/herdr-web:bob%40host?"))
        self.assertIn("secret=ABCD", uri)
        self.assertIn("issuer=herdr-web", uri)


class TestSessionCookie(unittest.TestCase):
    def test_roundtrip(self):
        secret = totp.generate_secret()
        token = totp.make_session(secret, iat=1000)
        self.assertTrue(totp.valid_session(secret, token))

    def test_regenerating_secret_invalidates(self):
        s1, s2 = totp.generate_secret(), totp.generate_secret()
        token = totp.make_session(s1, iat=1000)
        self.assertFalse(totp.valid_session(s2, token))

    def test_rejects_tampered_or_empty(self):
        secret = totp.generate_secret()
        token = totp.make_session(secret, iat=1000)
        self.assertFalse(totp.valid_session(secret, token + "x"))
        self.assertFalse(totp.valid_session(secret, "1000.deadbeef"))
        self.assertFalse(totp.valid_session(secret, ""))
        self.assertFalse(totp.valid_session(secret, None))
        self.assertFalse(totp.valid_session("", token))


if __name__ == "__main__":
    unittest.main()
