from imitate.r1_video import EOI, SOI, clip_jpeg


def test_clip_jpeg_keeps_soi_eoi():
    payload = SOI + b"\x00" * 200 + EOI
    assert clip_jpeg(payload) == payload


def test_clip_jpeg_strips_prefix_and_suffix():
    inner = SOI + b"\x01" * 200 + EOI
    blob = b"junk" + inner + b"\xff\x00tail"
    assert clip_jpeg(blob) == inner


def test_clip_jpeg_rejects_truncated():
    assert clip_jpeg(SOI + b"\x00" * 200) is None
    assert clip_jpeg(b"\x00" * 50) is None
    assert clip_jpeg(SOI + b"x" * 10 + EOI) is None
