from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("render_edl.py")
SPEC = importlib.util.spec_from_file_location("render_edl", SCRIPT)
assert SPEC and SPEC.loader
render_edl = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render_edl
SPEC.loader.exec_module(render_edl)


class RenderEdlTests(unittest.TestCase):
    def test_load_and_build_command_with_missing_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            edl = root / "edl.json"
            edl.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "timeline": {"width": 1280, "height": 720, "fps": 30},
                        "clips": [
                            {
                                "clip_id": "C001",
                                "shot_id": "S001",
                                "path": "clip.mp4",
                                "source_in": 1,
                                "source_out": 3.5,
                                "fit": "contain",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            probe = {
                "format": {"duration": "4.0"},
                "streams": [{"codec_type": "video", "width": 640, "height": 480}],
            }
            with mock.patch.object(render_edl, "probe", return_value=probe):
                timeline, clips = render_edl.load_edl(edl)
            with mock.patch.object(render_edl, "require_tool", return_value="ffmpeg"):
                command = render_edl.build_command(
                    timeline, clips, root / "out.mp4", crf=18, preset="medium"
                )
            filters = command[command.index("-filter_complex") + 1]
            self.assertIn("anullsrc", filters)
            self.assertIn("pad=1280:720", filters)
            self.assertIn("concat=n=1:v=1:a=1", filters)

    def test_rejects_duplicate_clip_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            item = {
                "clip_id": "C001",
                "shot_id": "S001",
                "path": str(clip),
                "source_out": 1,
            }
            edl = root / "edl.json"
            edl.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "timeline": {"width": 1280, "height": 720, "fps": 30},
                        "clips": [item, item],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                render_edl,
                "probe",
                return_value={"format": {"duration": "2"}, "streams": [{"codec_type": "video"}]},
            ):
                with self.assertRaises(render_edl.EdlError):
                    render_edl.load_edl(edl)

    def test_rejects_filter_syntax_in_background(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            edl = root / "edl.json"
            edl.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "timeline": {
                            "width": 1280,
                            "height": 720,
                            "fps": 30,
                            "background": "black:eval=frame",
                        },
                        "clips": [
                            {
                                "clip_id": "C001",
                                "shot_id": "S001",
                                "path": str(clip),
                                "source_out": 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(render_edl.EdlError):
                render_edl.load_edl(edl)


if __name__ == "__main__":
    unittest.main()
