import getpass, socket, unittest
import config, serve

def _s(**kw):
    base = dict(port=8022, bind="127.0.0.1", username="herdr",
               tunnel_enabled=False, require_os_auth=True)
    base.update(kw)
    return config.Settings(**base)

class TestPtyArgv(unittest.TestCase):
    def test_local_uses_herdr(self):
        self.assertEqual(serve.pty_argv(_s(), exposed=False), ["herdr"])

    def test_exposed_with_os_auth_uses_ssh(self):
        argv = serve.pty_argv(_s(tunnel_enabled=True, require_os_auth=True), exposed=True)
        self.assertEqual(argv, ["ssh", "%s@localhost" % getpass.getuser()])

    def test_exposed_without_os_auth_uses_herdr(self):
        argv = serve.pty_argv(_s(tunnel_enabled=True, require_os_auth=False), exposed=True)
        self.assertEqual(argv, ["herdr"])

class TestBind(unittest.TestCase):
    def test_uses_preferred_when_free(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
        s.close()
        httpd, port = serve._bind("127.0.0.1", free, serve.BaseHTTPRequestHandler)
        try:
            self.assertEqual(port, free)
        finally:
            httpd.server_close()

    def test_falls_back_when_preferred_busy(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        busy_port = busy.getsockname()[1]
        try:
            httpd, port = serve._bind("127.0.0.1", busy_port, serve.BaseHTTPRequestHandler)
            self.assertIsNotNone(httpd)
            self.assertNotEqual(port, busy_port)  # fell back to a free port
            httpd.server_close()
        finally:
            busy.close()

if __name__ == "__main__":
    unittest.main()
