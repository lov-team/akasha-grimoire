#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("fetch_shotcraft_sfx.py")


class FetchShotcraftSfxTest(unittest.TestCase):
    def run_fetch(self, manifest: Path, name: str, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            sys.executable, str(SCRIPT), "--manifest", str(manifest),
            "--name", name, "--output", str(output),
        ], text=True, capture_output=True, check=False)

    def test_downloads_and_verifies_selected_sfx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp3"
            source.write_bytes(b"sound")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sounds": [{
                "name": "hit", "url": source.as_uri(),
                "sha256": hashlib.sha256(b"sound").hexdigest(),
            }]}), encoding="utf-8")
            output = root / "public/hit.mp3"
            result = self.run_fetch(manifest, "hit", output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output.read_bytes(), b"sound")

    def test_hash_failure_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp3"
            source.write_bytes(b"tampered")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sounds": [{
                "name": "hit", "url": source.as_uri(), "sha256": "0" * 64,
            }]}), encoding="utf-8")
            output = root / "hit.mp3"
            output.write_bytes(b"existing")
            result = self.run_fetch(manifest, "hit", output)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
