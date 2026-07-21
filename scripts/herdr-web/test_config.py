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

    def test_set_tunnel_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            config.load_settings(d)  # default config (enabled=false)
            self.assertFalse(config.load_settings(d).tunnel_enabled)
            config.set_tunnel_enabled(d, True)
            self.assertTrue(config.load_settings(d).tunnel_enabled)
            config.set_tunnel_enabled(d, False)
            self.assertFalse(config.load_settings(d).tunnel_enabled)
            self.assertEqual(config.load_settings(d).port, 8022)  # rest preserved

    def test_save_password_atomic_0600(self):
        with tempfile.TemporaryDirectory() as d:
            config.save_password(d, "newsecret")
            self.assertEqual(config.load_or_create_password(d), "newsecret")
            mode = stat.S_IMODE(os.stat(config.password_path(d)).st_mode)
            self.assertEqual(mode, 0o600)

    def test_save_password_pins(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(config.is_password_pinned(d))
            config.save_password(d, "mine")
            self.assertTrue(config.is_password_pinned(d))

    def test_startup_rotates_when_unpinned(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = config.startup_password(d)
            p2 = config.startup_password(d)
            self.assertNotEqual(p1, p2)              # fresh each start
            self.assertFalse(config.is_password_pinned(d))

    def test_startup_keeps_pinned(self):
        with tempfile.TemporaryDirectory() as d:
            config.save_password(d, "pinnedpw")      # pins it
            self.assertEqual(config.startup_password(d), "pinnedpw")
            self.assertEqual(config.startup_password(d), "pinnedpw")  # stable across starts

    def test_tunnel_url_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(config.load_tunnel_url(d))
            config.save_tunnel_url(d, "https://x.trycloudflare.com")
            self.assertEqual(config.load_tunnel_url(d), "https://x.trycloudflare.com")
            config.clear_tunnel_url(d)
            self.assertIsNone(config.load_tunnel_url(d))

    def test_tunnel_status_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(config.load_tunnel_status(d))
            config.save_tunnel_status(d, "cloudflared not found")
            self.assertEqual(config.load_tunnel_status(d), "cloudflared not found")
            config.clear_tunnel_status(d)
            self.assertIsNone(config.load_tunnel_status(d))

    def test_tunnel_pid_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(os.path.exists(config.tunnel_pid_path(d)))
            config.save_tunnel_pid(d, 4321)
            self.assertEqual(open(config.tunnel_pid_path(d)).read().strip(), "4321")
            config.clear_tunnel_pid(d)
            self.assertFalse(os.path.exists(config.tunnel_pid_path(d)))

    def test_local_enabled_default_on_and_sticks(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(config.is_local_enabled(d))    # absent -> ON (fresh install)
            config.set_local_enabled(d, False)
            self.assertFalse(config.is_local_enabled(d))   # explicit off sticks
            config.set_local_enabled(d, True)
            self.assertTrue(config.is_local_enabled(d))

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

class TestNotify(unittest.TestCase):
    def test_missing_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(config.load_notify(d), {})

    def test_roundtrip_and_0600(self):
        with tempfile.TemporaryDirectory() as d:
            config.save_notify(d, {"options": {"include_password": True}})
            self.assertEqual(config.load_notify(d), {"options": {"include_password": True}})
            mode = stat.S_IMODE(os.stat(config.notify_path(d)).st_mode)
            self.assertEqual(mode, 0o600)  # holds bot tokens

    def test_corrupt_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            with open(config.notify_path(d), "w") as fh:
                fh.write("{not json")
            self.assertEqual(config.load_notify(d), {})


class TestPrefix(unittest.TestCase):
    def test_ctrl_letter_to_control_code(self):
        self.assertEqual(config.prefix_spec_to_bytes("ctrl+a"), b"\x01")
        self.assertEqual(config.prefix_spec_to_bytes("ctrl+b"), b"\x02")  # herdr default
        self.assertEqual(config.prefix_spec_to_bytes("CTRL+A"), b"\x01")  # case-insensitive

    def test_ctrl_special_codes(self):
        self.assertEqual(config.prefix_spec_to_bytes("ctrl+space"), b"\x00")
        self.assertEqual(config.prefix_spec_to_bytes("ctrl+["), b"\x1b")

    def test_named_and_bare_keys(self):
        self.assertEqual(config.prefix_spec_to_bytes("esc"), b"\x1b")
        self.assertEqual(config.prefix_spec_to_bytes("-"), b"-")
        self.assertEqual(config.prefix_spec_to_bytes("`"), b"`")

    def test_unrepresentable_is_empty(self):
        self.assertEqual(config.prefix_spec_to_bytes("f12"), b"")       # function key
        self.assertEqual(config.prefix_spec_to_bytes("ctrl+f12"), b"")
        self.assertEqual(config.prefix_spec_to_bytes(""), b"")
        self.assertEqual(config.prefix_spec_to_bytes(None), b"")

    def test_load_spec_from_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.toml")
            with open(path, "w") as fh:
                fh.write("[keys]\nprefix = \"ctrl+g\"\n")
            self.assertEqual(config.load_prefix_spec(path), "ctrl+g")

    def test_load_spec_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            # file absent -> herdr default
            self.assertEqual(config.load_prefix_spec(os.path.join(d, "nope.toml")),
                             config.HERDR_DEFAULT_PREFIX)
            # file present but no [keys] prefix -> herdr default
            path = os.path.join(d, "config.toml")
            with open(path, "w") as fh:
                fh.write("[server]\nport = 8022\n")
            self.assertEqual(config.load_prefix_spec(path), config.HERDR_DEFAULT_PREFIX)


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
