from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_video.py")
SPEC = importlib.util.spec_from_file_location("check_video", SCRIPT)
assert SPEC and SPEC.loader
check_video = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_video)


class CheckVideoTests(unittest.TestCase):
    def test_frame_positions_include_boundaries_without_duplicates(self) -> None:
        positions = check_video.frame_positions(10.0)
        self.assertEqual(positions, [0.1, 2.5, 5.0, 7.5, 9.9])
        self.assertEqual(check_video.frame_positions(0.1), [0.0])

    def test_srt_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.srt"
            path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\nWorld\n",
                encoding="utf-8",
            )
            result = check_video.validate_srt(path, 2.0)
            self.assertEqual(result["entries"], 2)
            self.assertEqual(result["errors"], [])

    def test_srt_validation_rejects_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.srt"
            path.write_text(
                "1\n00:00:00,000 --> 00:00:01,500\nOne\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\nTwo\n",
                encoding="utf-8",
            )
            result = check_video.validate_srt(path, 2.0)
            self.assertTrue(any("overlaps" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
