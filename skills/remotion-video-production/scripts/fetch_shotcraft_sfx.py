#!/usr/bin/env python3
"""Fetch one selected video-shotcraft SFX into a production project."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

DEFAULT_MANIFEST = Path(__file__).parent.parent / "assets/video-shotcraft/audio/sfx/SFX_MANIFEST.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    sound = next((item for item in manifest["sounds"] if item["name"] == args.name), None)
    if sound is None:
        parser.error(f"unknown SFX: {args.name}")

    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    request = urllib.request.Request(sound["url"], headers={"User-Agent": "Akasha-Grimoire/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != sound["sha256"]:
            raise ValueError(f"SHA-256 mismatch for {args.name}: expected {sound['sha256']}, got {actual}")
        temporary.write_bytes(data)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(destination)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
