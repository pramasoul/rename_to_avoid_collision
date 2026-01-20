from pathlib import Path

from rename_to_avoid_collision import cli

HELLO_B3_HEX = "ea8f163db38682925e4491c5e58d4bb3506ef8c14eb78a86e908c5624a67200f"


class FakePath:
    def __init__(self, name: str):
        self._name = name
        p = Path(name)
        self._suffix = p.suffix
        self._stem = p.stem
        self._parent = Path("/fake")

    def is_file(self) -> bool:
        return True

    @property
    def suffix(self) -> str:
        return self._suffix

    @property
    def stem(self) -> str:
        return self._stem

    @property
    def parent(self) -> Path:
        return self._parent

    def with_name(self, new_name: str):
        return FakePath(new_name)

    def exists(self) -> bool:
        return False

    def __str__(self) -> str:
        return self._name


def test_cli_strip_verify_fail_emits_count(monkeypatch, capsys):
    fake = FakePath("img__6o8WPa.heic")

    monkeypatch.setattr(cli, "iter_files", lambda root: [fake])
    monkeypatch.setattr(cli, "digest_blake3", lambda path: bytes.fromhex(HELLO_B3_HEX))

    code = cli.main(["/root", "--strip"])

    out = capsys.readouterr().out

    assert code == 0
    assert "skipped_verify_fail=1" in out
