import io
from pathlib import Path

from rename_to_avoid_collision import core

HELLO_B3_HEX = "ea8f163db38682925e4491c5e58d4bb3506ef8c14eb78a86e908c5624a67200f"
HELLO_SFX6 = "6o8WPb"  # derived from b3sum("hello") digest prefix


def test_digest_blake3_known_content(monkeypatch):
    data = b"hello"

    def fake_open(self, mode="rb"):
        assert mode == "rb"
        return io.BytesIO(data)

    monkeypatch.setattr(Path, "open", fake_open)

    digest = core.digest_blake3(Path("ignored"))

    assert digest.hex() == HELLO_B3_HEX


def test_propose_dst_apply_uses_expected_suffix(monkeypatch):
    digest = bytes.fromhex(HELLO_B3_HEX)
    src = Path("IMG_0001.jpg")

    monkeypatch.setattr(Path, "exists", lambda self: False)

    dst, sfx = core.propose_dst_apply(src, digest, 6)

    assert sfx == HELLO_SFX6
    assert dst is not None
    assert dst.name == f"IMG_0001__{HELLO_SFX6}.jpg"


def test_verify_suffix_matches_digest_true_and_false():
    digest = bytes.fromhex(HELLO_B3_HEX)

    assert core.verify_suffix_matches_digest(HELLO_SFX6, digest, 6)
    assert not core.verify_suffix_matches_digest("6o8WPa", digest, 6)
