import struct, unittest
import ptybridge

class TestControl(unittest.TestCase):
    def test_resize_message(self):
        self.assertEqual(
            ptybridge.parse_control(b'{"type":"resize","cols":120,"rows":40}'),
            (120, 40),
        )

    def test_non_resize_returns_none(self):
        self.assertIsNone(ptybridge.parse_control(b'{"type":"other"}'))

    def test_garbage_returns_none(self):
        self.assertIsNone(ptybridge.parse_control(b"not json"))

class TestWinsize(unittest.TestCase):
    def test_layout_rows_cols_zero_zero(self):
        self.assertEqual(ptybridge.winsize_bytes(40, 120), struct.pack("HHHH", 40, 120, 0, 0))

if __name__ == "__main__":
    unittest.main()
