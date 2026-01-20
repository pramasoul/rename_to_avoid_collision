from pathlib import Path

from rename_to_avoid_collision import cli, core


def test_cli_strip_dry_run(tmp_path: Path):
    src = tmp_path / "img.heic"
    src.write_bytes(b"hello")
    digest = core.digest_blake3(src)
    sfx = core.suffix_from_digest(digest, 6)
    suffixed = tmp_path / f"img__{sfx}.heic"
    src.rename(suffixed)

    code = cli.main([str(tmp_path), "--strip", "--quiet"])

    assert code == 0
    assert suffixed.exists()


def test_cli_strip_apply(tmp_path: Path):
    src = tmp_path / "img.heic"
    src.write_bytes(b"hello")
    digest = core.digest_blake3(src)
    sfx = core.suffix_from_digest(digest, 6)
    suffixed = tmp_path / f"img__{sfx}.heic"
    src.rename(suffixed)

    code = cli.main([str(tmp_path), "--strip", "--apply", "--quiet"])

    assert code == 0
    assert not suffixed.exists()
    assert (tmp_path / "img.heic").exists()
