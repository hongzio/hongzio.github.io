"""Hand-rolled RFC 6455 WebSocket bits. Pure stdlib."""
import base64
import hashlib
import struct

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

def accept_key(client_key):
    digest = hashlib.sha1((client_key + _GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")

def encode_frame(payload, opcode=OP_BINARY):
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack("!H", n)
    else:
        header.append(127)
        header += struct.pack("!Q", n)
    return bytes(header) + payload

def read_frame(recv_exactly):
    b0 = recv_exactly(1)[0]
    opcode = b0 & 0x0F
    b1 = recv_exactly(1)[0]
    masked = b1 & 0x80
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack("!H", recv_exactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", recv_exactly(8))[0]
    mask = recv_exactly(4) if masked else b""
    data = recv_exactly(length) if length else b""
    if masked:
        data = bytes(data[i] ^ mask[i % 4] for i in range(length))
    return opcode, data
