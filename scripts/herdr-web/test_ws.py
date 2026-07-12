import struct, unittest
import ws

class TestHandshake(unittest.TestCase):
    def test_rfc_example_accept_key(self):
        # RFC 6455 section 1.3 canonical example
        self.assertEqual(
            ws.accept_key("dGhlIHNhbXBsZSBub25jZQ=="),
            "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=",
        )

class TestEncode(unittest.TestCase):
    def test_small_binary_frame(self):
        f = ws.encode_frame(b"hi", ws.OP_BINARY)
        self.assertEqual(f, b"\x82\x02hi")  # FIN|binary, len 2

    def test_medium_length_uses_126(self):
        payload = b"x" * 200
        f = ws.encode_frame(payload, ws.OP_BINARY)
        self.assertEqual(f[0], 0x82)
        self.assertEqual(f[1], 126)
        self.assertEqual(struct.unpack("!H", f[2:4])[0], 200)

class TestRead(unittest.TestCase):
    def _reader(self, data):
        buf = {"b": data}
        def recv_exactly(n):
            if len(buf["b"]) < n:
                raise ConnectionError("eof")
            out, buf["b"] = buf["b"][:n], buf["b"][n:]
            return out
        return recv_exactly

    def test_masked_client_text(self):
        mask = b"\x01\x02\x03\x04"
        payload = b"ping"
        masked = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
        frame = bytes([0x81, 0x80 | len(payload)]) + mask + masked
        op, data = ws.read_frame(self._reader(frame))
        self.assertEqual(op, ws.OP_TEXT)
        self.assertEqual(data, b"ping")

if __name__ == "__main__":
    unittest.main()
