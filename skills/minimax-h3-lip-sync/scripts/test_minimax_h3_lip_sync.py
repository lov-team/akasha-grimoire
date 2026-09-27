#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("minimax_h3_lip_sync.py")
MP4 = b"\x00\x00\x00\x18ftypisomfixture"

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("lip_sync_under_test", SCRIPT)
assert SPEC and SPEC.loader
VIDEO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VIDEO)


class Handler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, bytes]] = []

    def log_message(self, *_args: object) -> None:
        pass

    def send_json(self, value: dict) -> None:
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.requests.append((self.command, self.path, body))
        self.send_json({"id": "task-lipsync-123", "status": "queued"})

    def do_GET(self) -> None:
        self.requests.append((self.command, self.path, b""))
        if self.path == "/v1/models":
            self.send_json({"object": "list", "data": []})
        elif self.path == "/v1/video/generations/task-lipsync-123":
            self.send_json({"data": {"task_id": "task-lipsync-123", "status": "SUCCESS"}})
        elif self.path == "/v1/videos/task-lipsync-123/content":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(MP4)))
            self.end_headers()
            self.wfile.write(MP4)
        else:
            self.send_response(404)
            self.end_headers()


class LipSyncGenerationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        Handler.requests.clear()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["LOVBROWSER_API_KEY"] = "test-key"
        env["AKASHA_ALLOW_TEST_HTTP"] = "1"
        return subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--timeout", "5", *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def output(self, name: str) -> str:
        return str(Path(self.temp_dir.name) / name)

    def submit_payload(self) -> dict:
        method, path, body = [request for request in Handler.requests if request[1] != "/v1/models"][0]
        self.assertEqual((method, path), ("POST", "/v1/video/generations"))
        return json.loads(body)

    def test_base_url_precedence(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://compatible.example/v1",
                "MINIMAX_H3_LIP_SYNC_BASE_URL": "https://lipsync.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(VIDEO.resolve_base_url(None), "https://lipsync.example/v1")
            self.assertEqual(VIDEO.resolve_base_url("https://cli.example"), "https://cli.example/v1")

    def test_lip_sync_payload_and_download(self) -> None:
        image = "https://media.example/portrait.png"
        audio = "https://media.example/speech.mp3"
        output = self.output("lip-sync.mp4")
        result = self.invoke(
            "generate", "--image", image, "--audio", audio,
            "--resolution", "1080P", "--seed", "7", "--no-transcription",
            "--poll-interval", "0.01", "--output", output,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(output).read_bytes(), MP4)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "minimax/h3-max/lip-sync/image-to-video")
        self.assertEqual(payload["images"], [image])
        self.assertEqual(payload["audio_url"], audio)
        self.assertNotIn("prompt", payload)
        self.assertNotIn("duration", payload)
        metadata = payload["metadata"]
        self.assertEqual(metadata["image_url"], image)
        self.assertEqual(metadata["audio_url"], audio)
        self.assertEqual(metadata["reference_audio_urls"], [audio])
        self.assertEqual(metadata["resolution"], "1080P")
        self.assertEqual(metadata["seed"], 7)
        self.assertFalse(metadata["enable_transcription"])

    def test_default_model_and_resolution(self) -> None:
        result = self.invoke(
            "generate",
            "--image", "https://media.example/portrait.png",
            "--audio", "https://media.example/speech.mp3",
            "--poll-interval", "0.01",
            "--output", self.output("default.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "minimax/h3-max/lip-sync/image-to-video")
        self.assertEqual(payload["metadata"]["resolution"], "768P")

    def test_fal_ai_alias_is_accepted(self) -> None:
        result = self.invoke(
            "generate", "--model", "fal-ai/minimax/h3-max/lip-sync/image-to-video",
            "--image", "https://media.example/portrait.png",
            "--audio", "https://media.example/speech.mp3",
            "--poll-interval", "0.01",
            "--output", self.output("alias.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.submit_payload()["model"], "fal-ai/minimax/h3-max/lip-sync/image-to-video")

    def test_rejects_missing_image_and_second_image(self) -> None:
        result = self.invoke(
            "generate",
            "--image", "https://media.example/a.png",
            "--image", "https://media.example/b.png",
            "--audio", "https://media.example/speech.mp3",
            "--poll-interval", "0.01",
            "--output", self.output("too-many.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at most 1", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])

        result = self.invoke(
            "generate",
            "--model", "kling-3",
            "--image", "https://media.example/a.png",
            "--audio", "https://media.example/speech.mp3",
            "--output", self.output("bad-model.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported video model", result.stderr)


class LipSyncWorkflowTest(unittest.TestCase):
    """Runs in-process, so no local HTTP server is needed."""

    IMAGE = "https://media.example/portrait.png"
    AUDIO = "https://media.example/speech.mp3"

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name).resolve() / "talk.mp4"
        self.sidecar = self.output.with_name("talk.mp4.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def args(self, *extra: str):
        return VIDEO.build_parser().parse_args(
            ["generate", "--image", self.IMAGE, "--audio", self.AUDIO, "--output", str(self.output), *extra]
        )

    def generate(self, task: dict, *extra: str) -> tuple[list[str], list[tuple[str, dict | None]]]:
        calls: list[tuple[str, dict | None]] = []
        responses = {
            "/video/generations": (b'{"id": "task-1"}', "application/json"),
            "/video/generations/task-1": (json.dumps(task).encode(), "application/json"),
            "/videos/task-1/content": (MP4, "video/mp4"),
        }

        def fake_request(base_url, api_key, path, timeout, payload=None, *, controller=None):
            calls.append((path, payload))
            return responses[path]

        stdout = io.StringIO()
        with (
            patch.object(VIDEO, "resolve_base_url", return_value="https://gateway.example/v1"),
            patch.object(VIDEO, "read_api_key", return_value="test-key"),
            patch.object(VIDEO, "request", side_effect=fake_request),
            patch.object(VIDEO, "probe_media", return_value=None),
            contextlib.redirect_stdout(stdout),
        ):
            VIDEO.run_generate(self.args(*extra))
        return stdout.getvalue().splitlines(), calls

    def test_invalid_requests_fail_before_credentials(self) -> None:
        cases = {
            "at most 1 --image": ("--image", "https://media.example/second.png"),
            "unsupported video model": ("--model", "kling-3"),
            "--metadata-json is invalid JSON": ("--metadata-json", "{"),
        }
        blocked = AssertionError("no credential lookup or request expected")
        with (
            patch.object(VIDEO, "resolve_base_url", side_effect=blocked),
            patch.object(VIDEO, "read_api_key", side_effect=blocked),
            patch.object(VIDEO, "request", side_effect=blocked),
        ):
            for fragment, extra in cases.items():
                with self.subTest(fragment), self.assertRaises(VIDEO.VideoGenerationError) as caught:
                    VIDEO.run_generate(self.args(*extra))
                self.assertIn(fragment, str(caught.exception))

            self.output.write_bytes(b"keep")
            with self.assertRaises(VIDEO.VideoGenerationError) as caught:
                VIDEO.run_generate(self.args())
            self.assertIn("pass --overwrite", str(caught.exception))
            self.assertEqual(self.output.read_bytes(), b"keep")

    def test_generate_reports_media_and_writes_sidecar(self) -> None:
        task = {"data": {"task_id": "task-1", "status": "SUCCESS", "data": {"seed": 99, "duration": 6.2}}}
        lines, calls = self.generate(task, "--resolution", "2K")
        self.assertEqual(
            [path for path, _ in calls],
            ["/video/generations", "/video/generations/task-1", "/videos/task-1/content"],
        )
        self.assertNotIn("seed", calls[0][1]["metadata"])
        self.assertEqual(self.output.read_bytes(), MP4)
        self.assertEqual(
            lines,
            [
                f"OK task_id=task-1 output={self.output} bytes={len(MP4)}",
                "MEDIA unavailable (ffprobe not found or failed)",
                f"SIDECAR {self.sidecar}",
            ],
        )
        text = self.sidecar.read_text(encoding="utf-8")
        record = json.loads(text)
        self.assertEqual(record["task_id"], "task-1")
        self.assertEqual(record["model"], "minimax/h3-max/lip-sync/image-to-video")
        self.assertEqual(record["seed"], 99)
        self.assertIsNone(record["media"])
        self.assertEqual(record["request"]["images"], 1)
        metadata = record["request"]["metadata"]
        self.assertEqual(metadata["resolution"], "2K")
        self.assertEqual(metadata["image_url"], "<url omitted>")
        self.assertEqual(metadata["reference_audio_urls"], ["<url omitted>"])
        self.assertNotIn("media.example", text)

    def test_sidecar_falls_back_to_requested_seed(self) -> None:
        self.generate({"data": {"status": "SUCCESS"}}, "--seed", "7")
        self.assertEqual(json.loads(self.sidecar.read_text(encoding="utf-8"))["seed"], 7)

    def test_report_media_warns_without_audio(self) -> None:
        media = {"codec": "h264", "width": 720, "height": 1280, "fps": 24.0, "duration": 6.208, "audio_streams": 0}
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(VIDEO, "probe_media", return_value=media),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(VIDEO.report_media(self.output), media)
        self.assertEqual(stdout.getvalue(), "MEDIA codec=h264 pixels=720x1280 fps=24 duration=6.21 audio_streams=0\n")
        self.assertIn("no audio stream", stderr.getvalue())

    def test_summarize_probe(self) -> None:
        probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280, "avg_frame_rate": "24/1"},
                {"codec_type": "audio", "codec_name": "aac", "avg_frame_rate": "0/0"},
            ],
            "format": {"duration": "6.208333"},
        }
        self.assertEqual(
            VIDEO.summarize_probe(probe),
            {"codec": "h264", "width": 720, "height": 1280, "fps": 24.0, "duration": 6.208, "audio_streams": 1},
        )
        self.assertIsNone(VIDEO.summarize_probe({"streams": [{"codec_type": "audio"}]}))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe are required")
    def test_probe_media_reads_a_real_file(self) -> None:
        clip = self.output.with_name("probe.mp4")
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=24:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(clip),
            ],
            check=True,
            capture_output=True,
        )
        media = VIDEO.probe_media(clip)
        self.assertEqual(
            {key: media[key] for key in ("codec", "width", "height", "fps", "audio_streams")},
            {"codec": "mpeg4", "width": 160, "height": 120, "fps": 24.0, "audio_streams": 1},
        )
        self.assertAlmostEqual(media["duration"], 1.0, delta=0.1)

    def test_help_states_the_audio_contract(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "generate", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("audio longer than 14.8 s is clipped to its first 14.8 s", " ".join(result.stdout.split()))


if __name__ == "__main__":
    unittest.main()
