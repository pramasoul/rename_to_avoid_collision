import base64
import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from blake3 import blake3

# Matches "NAME__suffix" where suffix is base64url-ish (no padding), >= 4 chars
SUFFIX_RE = re.compile(r"^(?P<stem>.*)__([A-Za-z0-9_-]{4,})$")

APPLE_CAMERA_EXTS = {
    ".heic", ".heif",
    ".jpg", ".jpeg", ".png",
    ".mov", ".mp4",
    ".aae",     # iOS edits sidecar
    ".json",    # sometimes produced by tooling
    ".xmp",     # metadata sidecar
}


def b64url_no_pad(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def digest_blake3(file_path: Path, chunk_size: int = 8 * 1024 * 1024) -> bytes:
    h = blake3()
    with file_path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.digest()  # 32 bytes


def suffix_from_digest(digest: bytes, n_chars: int) -> str:
    # Need enough bytes to yield at least n_chars base64url characters:
    # base64 chars = 4*ceil(n_bytes/3)  =>  n_bytes = ceil(3*n_chars/4)
    n_bytes = (3 * n_chars + 3) // 4
    s = b64url_no_pad(digest[:n_bytes])
    return s[:n_chars]


def sha256_digest(file_path: Path, chunk_size: int = 8 * 1024 * 1024) -> bytes:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.digest()


def same_bytes(a: Path, b: Path) -> bool:
    sa = a.stat()
    sb = b.stat()
    if sa.st_size != sb.st_size:
        return False
    return sha256_digest(a) == sha256_digest(b)


def iter_files(root: Path):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            yield Path(dirpath) / name


def propose_dst_apply(src: Path, digest: bytes, base_chars: int) -> Tuple[Optional[Path], str]:
    """
    Return (dst, suffix_used). If dst is None, caller should skip (already suffixed or duplicate).
    If collision with different content, suffix length is extended deterministically.
    """
    stem = src.stem
    if SUFFIX_RE.match(stem):
        return None, ""

    n = base_chars
    while True:
        sfx = suffix_from_digest(digest, n)
        dst = src.with_name(f"{stem}__{sfx}{src.suffix}")
        if not dst.exists():
            return dst, sfx
        if same_bytes(src, dst):
            return None, ""  # treat as duplicate
        n += 1


def parse_suffix(stem: str) -> Optional[Tuple[str, str]]:
    m = SUFFIX_RE.match(stem)
    if not m:
        return None
    return m.group("stem"), stem[len(m.group("stem")) + 2 :]  # after "__"


def verify_suffix_matches_digest(suffix: str, digest: bytes, base_chars: int) -> bool:
    """
    Accept if:
      - suffix length >= base_chars, and
      - suffix == suffix_from_digest(digest, len(suffix))
    This allows "extended suffix" cases while still tying the entire suffix to the digest prefix.
    """
    if len(suffix) < base_chars:
        return False
    expected = suffix_from_digest(digest, len(suffix))
    return suffix == expected


def find_noncolliding_strip_dst(dirpath: Path, stem: str, ext: str, policy: str) -> Optional[Path]:
    """
    For add-counter policy, find stem_1.ext, stem_2.ext, ...
    For refuse/keep-suffixed, returns None.
    """
    if policy != "add-counter":
        return None
    for i in range(1, 10_000_000):
        cand = dirpath / f"{stem}_{i}{ext}"
        if not cand.exists():
            return cand
    raise RuntimeError("Could not find a free counter suffix (unexpected).")
