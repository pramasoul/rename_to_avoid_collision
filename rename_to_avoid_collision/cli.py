import argparse
import json
import sys
import time
import uuid
from pathlib import Path

from .core import (
    APPLE_CAMERA_EXTS,
    b64url_no_pad,
    digest_blake3,
    find_noncolliding_strip_dst,
    iter_files,
    parse_suffix,
    propose_dst_apply,
    same_bytes,
    verify_suffix_matches_digest,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Rename camera-like files by appending/removing short base64url(BLAKE3) suffix "
            "(idempotent; collision-safe)."
        )
    )
    ap.add_argument("root", type=Path, help="Root directory to scan.")
    ap.add_argument("--chars", type=int, default=6, help="Base suffix length in base64url chars (default: 6).")

    # Modes
    ap.add_argument("--apply", action="store_true", help="Actually rename files. Default is dry-run.")
    ap.add_argument("--strip", action="store_true", help="Strip suffix instead of appending it.")

    # Extension selection
    ap.add_argument("--preset", choices=["apple-camera"], default=None, help="Use a predefined extension set.")
    ap.add_argument("--ext", action="append", default=None, help="Extensions to include (repeatable), e.g. --ext .heic --ext .jpg")

    # Strip options
    ap.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        help="When stripping, do not verify suffix against file digest (faster, less safe).",
    )
    ap.set_defaults(verify=True)
    ap.add_argument(
        "--conflict",
        choices=["refuse", "keep-suffixed", "add-counter"],
        default="refuse",
        help="When stripping, what to do if the stripped target exists with different content (default: refuse).",
    )

    # Output / progress
    ap.add_argument("-v", "--verbose", action="store_true", help="Print each rename as it is found.")
    ap.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output (overrides --verbose/progress).")
    ap.add_argument(
        "--progress",
        type=int,
        default=0,
        metavar="N",
        help="If set, print progress every N files scanned (to stderr).",
    )

    # Logging (apply mode only)
    ap.add_argument("--log", type=Path, default=None, help="JSONL log path (default: <root>/rename-log.jsonl when --apply).")

    args = ap.parse_args(argv)

    root = args.root.resolve()

    run_id = str(uuid.uuid4())

    # Extension set
    if args.ext is not None:
        ext_filter = set()
        for e in args.ext:
            e = e.strip()
            if not e:
                continue
            if not e.startswith("."):
                e = "." + e
            ext_filter.add(e.lower())
    elif args.preset == "apple-camera":
        ext_filter = set(APPLE_CAMERA_EXTS)
    else:
        ext_filter = {".heic"}  # historical default

    # Logging
    logf = None
    log_path = None
    exts_used = sorted(ext_filter)  # ext_filter already lowercased
    if args.apply:
        log_path = args.log or (root / "rename-log.jsonl")
        logf = log_path.open("a", encoding="utf-8")

    scanned = 0
    considered = 0
    renamed = 0
    skipped_not_target = 0
    skipped_dupe_or_already = 0
    skipped_verify_fail = 0
    conflicts = 0

    t0 = time.time()

    try:
        for p in iter_files(root):
            scanned += 1

            if args.progress and (not args.quiet) and scanned % args.progress == 0:
                dt = max(1e-9, time.time() - t0)
                rate = scanned / dt
                print(
                    f"[progress] scanned={scanned} considered={considered} renamed={renamed} "
                    f"skipped_not_target={skipped_not_target} skipped_dupe_or_already={skipped_dupe_or_already} "
                    f"skipped_verify_fail={skipped_verify_fail} conflicts={conflicts} rate={rate:.1f}/s",
                    file=sys.stderr,
                )

            if not p.is_file():
                continue

            if p.suffix.lower() not in ext_filter:
                skipped_not_target += 1
                continue

            considered += 1

            if not args.strip:
                # APPLY MODE
                digest = digest_blake3(p)
                dst, sfx = propose_dst_apply(p, digest, args.chars)
                if dst is None:
                    skipped_dupe_or_already += 1
                    continue

                if args.verbose and (not args.quiet):
                    print(f"{p}  ->  {dst}")

                if args.apply:
                    p.rename(dst)
                    renamed += 1

                    if logf:
                        st = dst.stat() if args.apply else p.stat()
                        rec = {
                            "ts": int(time.time()),
                            "run_id": run_id,
                            "mode": "apply",
                            "dry_run": (not args.apply),
                            "root": str(root),
                            "chars_min": args.chars,
                            "preset": args.preset,
                            "exts": exts_used,
                            "verify": False,
                            "conflict_policy": None,
                            "old": str(p),
                            "new": str(dst),
                            "suffix_used": sfx,
                            "suffix_removed": None,
                            "blake3_b64url": b64url_no_pad(digest),
                            "size": st.st_size,
                            "mtime": int(st.st_mtime),
                        }
                        logf.write(json.dumps(rec, ensure_ascii=False) + "\n")

                else:
                    renamed += 1

            else:
                # STRIP MODE
                parsed = parse_suffix(p.stem)
                if not parsed:
                    skipped_dupe_or_already += 1
                    continue
                base_stem, suffix = parsed

                if args.verify:
                    digest = digest_blake3(p)
                    if not verify_suffix_matches_digest(suffix, digest, args.chars):
                        skipped_verify_fail += 1
                        continue

                dst = p.with_name(f"{base_stem}{p.suffix}")

                # Collision handling
                if dst.exists():
                    if same_bytes(p, dst):
                        # already stripped / duplicate; treat as skip
                        skipped_dupe_or_already += 1
                        continue

                    if args.conflict == "keep-suffixed":
                        conflicts += 1
                        continue
                    if args.conflict == "refuse":
                        conflicts += 1
                        if not args.quiet:
                            print(f"[conflict] would overwrite: {dst} (from {p})", file=sys.stderr)
                        continue

                    # add-counter
                    alt = find_noncolliding_strip_dst(p.parent, base_stem, p.suffix, args.conflict)
                    if alt is None:
                        conflicts += 1
                        continue
                    dst = alt
                    conflicts += 1

                if args.verbose and (not args.quiet):
                    print(f"{p}  ->  {dst}")

                if args.apply:
                    p.rename(dst)
                    renamed += 1
                    if logf:
                        rec = {
                            "mode": "strip",
                            "old": str(p),
                            "new": str(dst),
                            "verify": bool(args.verify),
                            "suffix_removed": suffix,
                            "size": dst.stat().st_size,
                            "mtime": int(dst.stat().st_mtime),
                        }
                        logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                else:
                    renamed += 1

    finally:
        if logf:
            logf.close()

    if not args.quiet:
        mode = "STRIP" if args.strip else "APPLY"
        applied = "APPLIED" if args.apply else "DRY-RUN"
        print(
            f"{mode} {applied}: scanned={scanned} considered={considered} "
            f"{'renamed' if args.apply else 'would_rename'}={renamed} "
            f"skipped_not_target={skipped_not_target} skipped_dupe_or_already={skipped_dupe_or_already} "
            f"skipped_verify_fail={skipped_verify_fail} conflicts={conflicts}"
        )
        if args.apply and log_path is not None:
            print(f"Log: {log_path}")

    # In strip mode with default refuse, conflicts indicates how many need manual handling.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
