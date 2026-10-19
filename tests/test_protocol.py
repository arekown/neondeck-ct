from neondeck.device.protocol import (
    ButtonEvent,
    FrameReader,
    RotateEvent,
    TouchEvent,
    WheelTouchEvent,
    build_message,
    encode_frame,
    parse_event,
)


def test_encode_frame_short():
    assert encode_frame(b"\x05\x09\x01\x0a\x00") == b"\x82\x85\x00\x00\x00\x00\x05\x09\x01\x0a\x00"


def test_encode_frame_16bit_length():
    p = bytes(300)
    f = encode_frame(p)
    assert f[:4] == b"\x82\xfe\x01\x2c" and f[4:8] == b"\0\0\0\0" and len(f) == 8 + 300


def test_frame_reader_split_and_garbage():
    r = FrameReader()
    assert r.feed(b"HTTP\x82\x05\x05\x00") == []
    assert r.feed(b"\x00\x07\x00") == [b"\x05\x00\x00\x07\x00"]


def test_frame_reader_16bit_and_multiple():
    r = FrameReader()
    p = bytes(range(200))
    data = b"\x82\x7e\x00\xc8" + p + b"\x82\x02ab"
    assert r.feed(data) == [p, b"ab"]


def test_build_message_len_capped():
    assert build_message(0x10, 3, bytes(400))[:3] == b"\xff\x10\x03"
    assert build_message(0x09, 1, b"\x0a") == b"\x04\x09\x01\x0a"


def test_parse_events_from_measurement():
    assert parse_event(bytes.fromhex("0500000700")) == ButtonEvent(7, True)
    assert parse_event(bytes.fromhex("0500000701")) == ButtonEvent(7, False)
    assert parse_event(bytes.fromhex("0501000401")) == RotateEvent(4, +1)
    assert parse_event(bytes.fromhex("05010004ff")) == RotateEvent(4, -1)
    assert parse_event(bytes.fromhex("094d0000006700252f")) == TouchEvent(0, 103, 37, True)
    assert parse_event(bytes.fromhex("096d0000006700252f")) == TouchEvent(0, 103, 37, False)
    assert parse_event(bytes.fromhex("09520000007a006000")) == WheelTouchEvent(0, 122, 96, True)
    assert parse_event(bytes.fromhex("1f0301" + "41" * 28)) is None


def test_frame_reader_drops_absurd_length_and_resyncs():
    r = FrameReader()
    garbage = b"\x82\x7f" + (2 * 1_048_576).to_bytes(8, "big")
    assert r.feed(garbage + b"\x82\x02ab") == [b"ab"]
