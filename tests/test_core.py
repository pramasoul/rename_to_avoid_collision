from pathlib import Path

from rename_to_avoid_collision import core


def test_suffix_from_digest_length_and_determinism():
    digest = b"\x00" * 32
    sfx6 = core.suffix_from_digest(digest, 6)
    sfx10 = core.suffix_from_digest(digest, 10)

    assert len(sfx6) == 6
    assert len(sfx10) == 10
    assert sfx6 == core.suffix_from_digest(digest, 6)


def test_propose_dst_apply_no_collision(tmp_path: Path):
    src = tmp_path / "photo.jpg"
    src.write_bytes(b"abc")

    digest = core.digest_blake3(src)
    dst, sfx = core.propose_dst_apply(src, digest, 6)

    assert dst is not None
    assert sfx
    assert dst.name.startswith("photo__")
    assert dst.suffix == ".jpg"


def test_propose_dst_apply_extends_on_collision(tmp_path: Path):
    src = tmp_path / "photo.jpg"
    src.write_bytes(b"abc")

    digest = core.digest_blake3(src)
    base = core.suffix_from_digest(digest, 6)
    colliding = tmp_path / f"photo__{base}.jpg"
    colliding.write_bytes(b"different")

    dst, sfx = core.propose_dst_apply(src, digest, 6)

    assert dst is not None
    assert len(sfx) > 6
    assert dst.name.startswith("photo__")


def test_verify_suffix_matches_digest():
    digest = b"\x01" * 32
    sfx = core.suffix_from_digest(digest, 6)

    assert core.verify_suffix_matches_digest(sfx, digest, 6)
    assert not core.verify_suffix_matches_digest("abcdef", digest, 6)
