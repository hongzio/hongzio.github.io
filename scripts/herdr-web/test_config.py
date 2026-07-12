import os, stat, tempfile, unittest
import config

class TestParse(unittest.TestCase):
    def test_sections_keys_comments(self):
        text = (
            "# comment\n"
            "[server]\n"
            "port = 8022   # inline comment\n"
            'bind = "127.0.0.1"\n'
            "\n"
            "[tunnel]\n"
            "enabled = true\n"
        )
        cfg = config.parse_config(text)
        self.assertEqual(cfg["server"]["port"], "8022")
        self.assertEqual(cfg["server"]["bind"], "127.0.0.1")   # quotes stripped
        self.assertEqual(cfg["tunnel"]["enabled"], "true")

    def test_junk_lines_ignored(self):
        cfg = config.parse_config("garbage\nkey_without_section = 1\n[a]\nk=v\n")
        self.assertEqual(cfg, {"a": {"k": "v"}})

class TestSettings(unittest.TestCase):
    def test_defaults_created(self):
        with tempfile.TemporaryDirectory() as d:
            s = config.load_settings(d)
            self.assertEqual(s.port, 8022)
            self.assertEqual(s.bind, "127.0.0.1")
            self.assertEqual(s.username, "herdr")
            self.assertFalse(s.tunnel_enabled)
            self.assertFalse(s.require_os_auth)
            self.assertTrue(os.path.exists(os.path.join(d, "config.toml")))

    def test_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "config.toml"), "w") as fh:
                fh.write("[server]\nport = 9000\n[tunnel]\nenabled = true\nrequire_os_auth = true\n")
            s = config.load_settings(d)
            self.assertEqual(s.port, 9000)
            self.assertTrue(s.tunnel_enabled)
            self.assertTrue(s.require_os_auth)

class TestPassword(unittest.TestCase):
    def test_generate_then_reuse_0600(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = config.load_or_create_password(d)
            self.assertTrue(len(p1) >= 16)
            mode = stat.S_IMODE(os.stat(os.path.join(d, "password")).st_mode)
            self.assertEqual(mode, 0o600)
            self.assertEqual(config.load_or_create_password(d), p1)  # stable

class TestLiveEdits(unittest.TestCase):
    def test_set_username_replaces_and_preserves(self):
        with tempfile.TemporaryDirectory() as d:
            config.load_settings(d)  # write default config.toml
            config.set_username(d, "alice")
            s = config.load_settings(d)
            self.assertEqual(s.username, "alice")
            self.assertEqual(s.port, 8022)          # other settings intact
            self.assertFalse(s.tunnel_enabled)
            self.assertIn("[tunnel]", open(os.path.join(d, "config.toml")).read())

    def test_save_password_atomic_0600(self):
        with tempfile.TemporaryDirectory() as d:
            config.save_password(d, "newsecret")
            self.assertEqual(config.load_or_create_password(d), "newsecret")
            mode = stat.S_IMODE(os.stat(config.password_path(d)).st_mode)
            self.assertEqual(mode, 0o600)

    def test_tunnel_url_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(config.load_tunnel_url(d))
            config.save_tunnel_url(d, "https://x.trycloudflare.com")
            self.assertEqual(config.load_tunnel_url(d), "https://x.trycloudflare.com")
            config.clear_tunnel_url(d)
            self.assertIsNone(config.load_tunnel_url(d))

    def test_current_creds_reads_live(self):
        with tempfile.TemporaryDirectory() as d:
            config.load_settings(d)
            config.set_username(d, "bob")
            config.save_password(d, "pw123")
            self.assertEqual(config.current_creds(d, d), ("bob", "pw123"))

    def test_port_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(config.load_port(d))
            config.save_port(d, 9999)
            self.assertEqual(config.load_port(d), 9999)
            config.clear_port(d)
            self.assertIsNone(config.load_port(d))

class TestInstance(unittest.TestCase):
    def test_keyed_by_socket_path(self):
        old = os.environ.get("HERDR_SOCKET_PATH")
        try:
            os.environ["HERDR_SOCKET_PATH"] = "/tmp/a.sock"
            a = config.instance_state_dir("/base")
            os.environ["HERDR_SOCKET_PATH"] = "/tmp/b.sock"
            b = config.instance_state_dir("/base")
            self.assertNotEqual(a, b)
            self.assertTrue(a.startswith(os.path.join("/base", "instances") + os.sep))
        finally:
            if old is None:
                os.environ.pop("HERDR_SOCKET_PATH", None)
            else:
                os.environ["HERDR_SOCKET_PATH"] = old

    def test_default_without_socket(self):
        old = os.environ.pop("HERDR_SOCKET_PATH", None)
        try:
            self.assertEqual(config.instance_state_dir("/base"),
                             os.path.join("/base", "instances", "default"))
        finally:
            if old is not None:
                os.environ["HERDR_SOCKET_PATH"] = old

    def test_password_isolated_per_instance(self):
        old = os.environ.get("HERDR_SOCKET_PATH")
        with tempfile.TemporaryDirectory() as base:
            try:
                os.environ["HERDR_SOCKET_PATH"] = "/tmp/A.sock"
                pa = config.load_or_create_password(config.instance_state_dir(base))
                os.environ["HERDR_SOCKET_PATH"] = "/tmp/B.sock"
                pb = config.load_or_create_password(config.instance_state_dir(base))
                self.assertNotEqual(pa, pb)                 # isolated
                os.environ["HERDR_SOCKET_PATH"] = "/tmp/A.sock"
                self.assertEqual(config.load_or_create_password(config.instance_state_dir(base)), pa)  # stable
            finally:
                if old is None:
                    os.environ.pop("HERDR_SOCKET_PATH", None)
                else:
                    os.environ["HERDR_SOCKET_PATH"] = old

if __name__ == "__main__":
    unittest.main()
