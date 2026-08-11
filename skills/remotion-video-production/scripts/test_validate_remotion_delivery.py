#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("validate_remotion_delivery.py")


class ValidateRemotionDeliveryTest(unittest.TestCase):
    def make_project(self, root: Path, source: str = "export const frame = 1;\n") -> tuple[Path, Path, Path]:
        project = root / "project"
        for directory in ("src", "public", "render", "qa", "qa/keyframes"):
            (project / directory).mkdir(parents=True, exist_ok=True)
        for filename in ("brief.md", "design.md", "storyboard.md", "commands.md"):
            (project / filename).write_text("ok\n", encoding="utf-8")
        (project / "package.json").write_text('{"scripts":{"remotion":"remotion"}}\n', encoding="utf-8")
        (project / "src/index.ts").write_text(source, encoding="utf-8")
        (project / "timeline.json").write_text(
            '[{"id":"main","from":0,"durationInFrames":60}]\n', encoding="utf-8"
        )
        video = project / "render/final.mp4"
        sfx = project / "render/final-sfx.mp4"
        video.write_bytes(b"video")
        sfx.write_bytes(b"video")
        (project / "qa/keyframes/main-f0001.png").write_bytes(b"png")
        return project, video, sfx

    def make_tools(
        self, root: Path, width: int = 1080, text_compositions: bool = False,
        frame_mismatch: bool = False, zero_fps: bool = False,
    ) -> Path:
        tools = root / "bin"
        tools.mkdir()
        composition = json.dumps([
            {"id": "Demo", "width": width, "height": 1920, "fps": 30, "durationInFrames": 60}
        ])
        probe = json.dumps({
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": width, "height": 1920,
                 "avg_frame_rate": "0/0" if zero_fps else "30/1", "nb_frames": "60", "duration": "2.000000"},
                {"codec_type": "audio", "codec_name": "aac", "duration": "2.000000"}
            ],
            "format": {"duration": "2.000000"}
        })
        composition_output = (
            f"The following compositions are available:\n\nDemo    30    {width}x1920    60 (2.00 sec)"
            if text_compositions else composition
        )
        scripts = {
            "npx": f"#!/bin/sh\nprintf '%s\\n' '{composition_output}'\n",
            "ffprobe": f"#!/bin/sh\nprintf '%s\\n' '{probe}'\n",
            "ffmpeg": (
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *framemd5*)\n"
                + ("    case \"$*\" in *final-sfx.mp4*) echo DIFFERENT;; *) echo SAME;; esac\n" if frame_mismatch else "    echo SAME\n")
                + "    ;;\n"
                "esac\n"
                "exit 0\n"
            ),
        }
        for name, body in scripts.items():
            path = tools / name
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)
        return tools

    def run_validator(self, project: Path, video: Path, tools: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        report = project / "qa/report.json"
        env = os.environ.copy()
        env["PATH"] = f"{tools}:{env['PATH']}"
        command = [
            sys.executable, str(SCRIPT), str(project),
            "--composition", "Demo", "--video", str(video),
            "--width", "1080", "--height", "1920", "--fps", "30",
            "--duration-frames", "60", "--report", str(report),
            "--keyframes-dir", str(project / "qa/keyframes"), *extra,
        ]
        return subprocess.run(command, text=True, capture_output=True, env=env, check=False)

    def test_accepts_complete_deterministic_delivery_and_matching_sfx_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, sfx = self.make_project(root)
            result = self.run_validator(project, video, self.make_tools(root), "--sfx-only-video", str(sfx))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["composition"]["id"], "Demo")
            self.assertEqual(report["videos"][0]["codec"], "h264")

    def test_rejects_different_frames_between_audio_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, sfx = self.make_project(root)
            result = self.run_validator(
                project, video, self.make_tools(root, frame_mismatch=True),
                "--sfx-only-video", str(sfx),
            )
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertIn("decoded video frames differ", "\n".join(report["errors"]))

    def test_accepts_current_remotion_text_composition_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, _ = self.make_project(root)
            result = self.run_validator(project, video, self.make_tools(root, text_compositions=True))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["composition"]["durationInFrames"], 60)

    def test_rejects_timeline_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, _ = self.make_project(root)
            (project / "timeline.json").write_text(
                '[{"id":"a","from":0,"durationInFrames":20},'
                '{"id":"b","from":21,"durationInFrames":39}]\n', encoding="utf-8"
            )
            result = self.run_validator(project, video, self.make_tools(root))
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertIn("timeline gap or overlap", "\n".join(report["errors"]))

    def test_requires_one_keyframe_per_timeline_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, _ = self.make_project(root)
            (project / "timeline.json").write_text(
                '[{"id":"a","from":0,"durationInFrames":20},'
                '{"id":"b","from":20,"durationInFrames":40}]\n', encoding="utf-8"
            )
            (project / "qa/keyframes/a-f0001.png").write_bytes(b"png")
            result = self.run_validator(project, video, self.make_tools(root))
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertIn("keyframe missing for scene b", "\n".join(report["errors"]))

    def test_rejects_timeline_scene_without_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, _ = self.make_project(root)
            (project / "timeline.json").write_text(
                '[{"from":0,"durationInFrames":60}]\n', encoding="utf-8"
            )
            result = self.run_validator(project, video, self.make_tools(root))
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertIn("scene id", "\n".join(report["errors"]))

    def test_reports_zero_frame_rate_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, _ = self.make_project(root)
            result = self.run_validator(project, video, self.make_tools(root, zero_fps=True))
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertIn("frame rate", "\n".join(report["errors"]))

    def test_rejects_nondeterministic_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, _ = self.make_project(root, "export const value = Math.random();\n")
            result = self.run_validator(project, video, self.make_tools(root))
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertIn("Math.random()", "\n".join(report["errors"]))

    def test_rejects_composition_and_video_spec_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, video, _ = self.make_project(root)
            result = self.run_validator(project, video, self.make_tools(root, width=720))
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((project / "qa/report.json").read_text(encoding="utf-8"))
            self.assertIn("width", "\n".join(report["errors"]))


if __name__ == "__main__":
    unittest.main()
