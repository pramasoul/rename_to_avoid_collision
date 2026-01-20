# uncollide

Rename camera-like files by appending (or stripping) a short base64url BLAKE3 suffix to avoid name collisions. The suffix is deterministic per file content, so repeated runs are idempotent and collisions are handled safely.

## What it does

- Appends `__<suffix>` to filenames (e.g., `IMG_1234__a1b2c3.jpg`) based on the file's BLAKE3 digest
- Skips files that already have a suffix or are duplicates
- Can strip suffixes back to the original name, optionally verifying the suffix matches the file content
- Handles collisions when stripping with configurable policies
- Logs applied renames to JSONL for auditability

## Requirements

- Python 3.8+
- `blake3` Python package

Install:

```bash
python3 -m pip install blake3
```

## Usage

Dry-run (default) to see what would change:

```bash
python3 rename_to_avoid_collision.py /path/to/photos --preset apple-camera
```

Apply renames:

```bash
python3 rename_to_avoid_collision.py /path/to/photos --preset apple-camera --apply
```

Strip suffixes (dry-run):

```bash
python3 rename_to_avoid_collision.py /path/to/photos --strip --preset apple-camera
```

Strip suffixes with verification and apply:

```bash
python3 rename_to_avoid_collision.py /path/to/photos --strip --verify --apply
```

## Options

- `--chars N`: Base suffix length in base64url characters (default: 6)
- `--apply`: Actually rename files (otherwise dry-run)
- `--strip`: Remove suffixes instead of appending
- `--preset apple-camera`: Use Apple camera-related extensions
- `--ext .heic --ext .jpg`: Custom extension list (repeatable)
- `--verify`: When stripping, verify suffix matches the file's digest
- `--conflict {refuse,keep-suffixed,add-counter}`: Conflict policy when stripping
- `--log PATH`: JSONL log path (default: `<root>/rename-log.jsonl` when `--apply`)
- `--progress N`: Print progress every N files scanned
- `-v/--verbose`: Print each rename as it is found
- `-q/--quiet`: Suppress non-error output

## Notes

- The suffix is derived from the BLAKE3 digest and encoded as base64url without padding.
- If a collision is detected with different content, the suffix is deterministically extended until unique.
- In strip mode, `--verify` is recommended if you want to ensure the suffix truly matches the file content.
- Default extension set is `.heic` unless you use `--preset` or `--ext`.

## Logging

When `--apply` is set, a JSONL log is written with details about each rename, including digest and suffix used. This makes runs auditable and reversible if needed.

## License

See `LICENSE`.

## Credits

- ChatGPT 5.2 for the architecture and coding
- Tom Soulanille for setting requirements
