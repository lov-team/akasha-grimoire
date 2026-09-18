#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import os
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


if __name__ == "__main__":
    unittest.main()
