#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(paths: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for path in paths:
        if not path.is_file():
            continue
        lines.append(f"{sha256_file(path)}  {path.name}")
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SHA256 checksums")
    parser.add_argument("files", nargs="+", help="Files to hash")
    parser.add_argument("-o", "--output", required=True, help="Output checksum file")
    args = parser.parse_args()

    write_checksums([Path(p) for p in args.files], Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
