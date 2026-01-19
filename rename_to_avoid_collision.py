#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from blake3 import blake3

SUFFIX_RE = re.compile(r"^(?P<stem>.*)__([A-Za-z0-9_-]{6,})$")


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
    # Need enough bytes to yield at least n_chars base64 characters:
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
    # Fast rejection
    sa = a.stat()
    sb = b.stat()
    if sa.st_size != sb.st_size:
        return False
    # Strong compare
    return sha256_digest(a) == sha256_digest(b)


def propose_dst(src: Path, digest: bytes, base_chars: int) -> Tuple[Path, str]:
    stem = src.stem
    n = base_chars
    while True:
        sfx = suffix_from_digest(digest, n)
        dst = src.with_name(f"{stem}__{sfx}{src.suffix}")
        if not dst.exists():
            return dst, sfx
        # Existing target: if identical bytes, treat as already archived / duplicate.
        if same_bytes(src, dst):
            return src, ""  # sentinel meaning "skip"
        n += 1  # extend deterministically until unique


def iter_files(root: Path):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            yield Path(dirpath) / name


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Append short base64url(BLAKE3) suffix to filenames (idempotent; collision-safe by suffix extension)."
    )
    ap.add_argument("root", type=Path, help="Root directory to scan.")
    ap.add_argument("--ext", action="append", default=[".heic"], help="Extensions to include (repeatable). Default: .heic")
    ap.add_argument("--chars", type=int, default=6, help="Base suffix length in base64url chars (default: 6).")
    ap.add_argument("--apply", action="store_true", help="Actually rename files. Default is dry-run.")
    ap.add_argument("--log", type=Path, default=None, help="JSONL log path (default: <root>/rename-log.jsonl when --apply).")
    ap.add_argument("-v", "--verbose", action="store_true", help="Print each rename as it is found.")
    ap.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output (overrides --verbose/progress).")
    ap.add_argument(
        "--progress",
        type=int,
        default=0,
        metavar="N",
        help="If set, print progress every N files scanned (to stderr).",
    )
    args = ap.parse_args()

    root = args.root.resolve()
    ext_filter = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.ext}

    logf = None
    if args.apply:
        log_path = args.log or (root / "rename-log.jsonl")
        logf = log_path.open("a", encoding="utf-8")

    scanned = 0
    considered = 0
    renamed = 0
    skipped_already_suffixed = 0
    skipped_dupe = 0
    t0 = time.time()

    try:
        for p in iter_files(root):
            scanned += 1

            if args.progress and (not args.quiet) and scanned % args.progress == 0:
                dt = max(1e-9, time.time() - t0)
                rate = scanned / dt
                print(
                    f"[progress] scanned={scanned} considered={considered} renamed={renamed} "
                    f"skipped_suffixed={skipped_already_suffixed} skipped_dupe={skipped_dupe} "
                    f"rate={rate:.1f}/s",
                    file=sys.stderr,
                )

            if not p.is_file():
                continue
            if p.suffix.lower() not in ext_filter:
                continue

            stem = p.stem
            if SUFFIX_RE.match(stem):
                skipped_already_suffixed += 1
                continue

            considered += 1
            digest = digest_blake3(p)
            dst, sfx = propose_dst(p, digest, args.chars)

            if dst == p and sfx == "":
                skipped_dupe += 1
                continue

            if args.verbose and (not args.quiet):
                print(f"{p}  ->  {dst}")

            if args.apply:
                p.rename(dst)
                renamed += 1
                if logf:
                    rec = {
                        "old": str(p),
                        "new": str(dst),
                        "suffix_used": sfx,
                        "blake3_b64url": b64url_no_pad(digest),
                        "size": dst.stat().st_size,
                        "mtime": int(dst.stat().st_mtime),
                    }
                    logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            else:
                # dry-run: count as “would rename”
                renamed += 1

    finally:
        if logf:
            logf.close()

    if not args.quiet:
        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(
            f"{mode}: scanned={scanned} considered={considered} "
            f"{'renamed' if args.apply else 'would_rename'}={renamed} "
            f"skipped_suffixed={skipped_already_suffixed} skipped_dupe={skipped_dupe}"
        )
        if args.apply:
            print(f"Log: {log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

