#!/usr/bin/env python3

from __future__ import annotations

import json
import importlib.machinery
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("video_continuation.py")


def load_module():
    loader = importlib.machinery.SourceFileLoader("video_continuation", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class VideoContinuationLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_fraction(self) -> None:
        self.assertEqual(self.module.fraction("30/1"), 30.0)
        with self.assertRaises(self.module.ContinuationError):
            self.module.fraction("30/0")

    def test_public_url_validation(self) -> None:
        url = "https://media.example/frame.png"
        self.assertEqual(self.module.validate_public_https_url(url), url)
        with self.assertRaises(Exception):
            self.module.validate_public_https_url("http://media.example/frame.png")
        with self.assertRaises(Exception):
            self.module.validate_public_https_url("https://user:pass@media.example/frame.png")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe are required")
class VideoContinuationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def make_video(self, path: Path, color: str, *, audio: bool = True, size: str = "160x288") -> None:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}:r=30:d=0.6",
        ]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.6", "-shortest"]
        command += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio:
            command += ["-c:a", "aac"]
        command += ["-y", str(path)]
        subprocess.run(command, check=True, capture_output=True)

    def test_extract_writes_png_and_refuses_overwrite(self) -> None:
        source = self.root / "source.mp4"
        frame = self.root / "last.png"
        self.make_video(source, "blue")
        result = self.run_command("extract", "--source", str(source), "--output", str(frame))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(frame.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        repeated = self.run_command("extract", "--source", str(source), "--output", str(frame))
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("already exists", repeated.stderr)

    def test_stitch_preserves_audio_and_expected_duration(self) -> None:
        previous = self.root / "previous.mp4"
        next_video = self.root / "next.mp4"
        output = self.root / "combined.mp4"
        self.make_video(previous, "red")
        self.make_video(next_video, "blue")
        result = self.run_command(
            "stitch",
            "--previous",
            str(previous),
            "--next",
            str(next_video),
            "--output",
            str(output),
            "--trim-next-start",
            "0.033",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["has_audio"])
        self.assertEqual((payload["width"], payload["height"]), (160, 288))
        self.assertAlmostEqual(payload["actual_duration"], 1.167, delta=0.25)

    def test_stitch_rejects_resolution_mismatch(self) -> None:
        previous = self.root / "previous.mp4"
        next_video = self.root / "next.mp4"
        self.make_video(previous, "red", size="160x288")
        self.make_video(next_video, "blue", size="180x320")
        result = self.run_command(
            "stitch",
            "--previous",
            str(previous),
            "--next",
            str(next_video),
            "--output",
            str(self.root / "combined.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("same resolution", result.stderr)


if __name__ == "__main__":
    unittest.main()
