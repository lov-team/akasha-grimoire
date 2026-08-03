from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("source_media.py")
SPEC = importlib.util.spec_from_file_location("source_media", SCRIPT)
assert SPEC and SPEC.loader
source_media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source_media)


class SourceMediaTests(unittest.TestCase):
    def test_safe_url_removes_query_and_fragment(self) -> None:
        self.assertEqual(
            source_media.safe_url("https://media.example/a.mp4?token=secret#part"),
            "https://media.example/a.mp4",
        )

    def test_sanitize_filename(self) -> None:
        self.assertEqual(source_media.sanitize_filename("片段 one?.mp4"), "one-.mp4")

    def test_register_asset_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / "clip.mp4"
            media.write_bytes(b"fixture-media")
            manifest = root / "sources.json"
            probe = {"duration": 2.0, "video_codec": "h264", "audio_codec": "aac"}
            with mock.patch.object(source_media, "probe_media", return_value=probe):
                first = source_media.register_asset(
                    file_path=media,
                    manifest_path=manifest,
                    shot_id="S001",
                    source_url="https://example.test/clip",
                    source_page="",
                    creator="",
                    license_name="",
                    notes="first",
                    status="candidate",
                )
                second = source_media.register_asset(
                    file_path=media,
                    manifest_path=manifest,
                    shot_id="S001",
                    source_url="https://example.test/clip",
                    source_page="",
                    creator="",
                    license_name="",
                    notes="selected",
                    status="selected",
                )
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(len(data["assets"]), 1)
            self.assertEqual(first["asset_id"], second["asset_id"])
            self.assertEqual(first["retrieved_at"], second["retrieved_at"])
            self.assertEqual(data["assets"][0]["status"], "selected")


if __name__ == "__main__":
    unittest.main()
