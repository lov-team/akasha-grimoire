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

SCRIPT = Path(__file__).with_name("video_generation.py")
MP4 = b"\x00\x00\x00\x18ftypisomfixture"

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("video_generation_under_test", SCRIPT)
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
        self.send_json({"id": "task-video-123", "status": "queued"})

    def do_GET(self) -> None:
        self.requests.append((self.command, self.path, b""))
        if self.path == "/v1/models":
            self.send_json({"object": "list", "data": []})
        elif self.path == "/v1/video/generations/task-video-123":
            self.send_json({"data": {"task_id": "task-video-123", "status": "SUCCESS"}})
        elif self.path == "/v1/videos/task-video-123/content":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(MP4)))
            self.end_headers()
            self.wfile.write(MP4)
        else:
            self.send_response(404)
            self.end_headers()


class VideoGenerationTest(unittest.TestCase):
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
        env["H3_KLING_VIDEO_API_KEY"] = "test-key"
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
                "H3_KLING_VIDEO_BASE_URL": "https://video.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(VIDEO.resolve_base_url(None), "https://video.example/v1")
            self.assertEqual(VIDEO.resolve_base_url("https://cli.example"), "https://cli.example/v1")

    def test_minimax_h3_payload_and_download(self) -> None:
        output = self.output("h3.mp4")
        result = self.invoke(
            "generate", "--model", "minimax-h3", "--prompt", "a cat on a beach",
            "--duration", "15", "--aspect-ratio", "21:9", "--resolution", "768P",
            "--poll-interval", "0.01", "--output", output,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(output).read_bytes(), MP4)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "minimax-h3/text-to-video")
        self.assertEqual(payload["duration"], 15)
        self.assertEqual(payload["metadata"], {
            "aspect_ratio": "21:9", "duration": 15, "resolution": "768P"
        })

    def test_minimax_h3_image_to_video_first_and_last_frame_payload(self) -> None:
        first = "https://media.example/first.png"
        last = "https://media.example/last.png"
        result = self.invoke(
            "generate", "--model", "h3-i2v", "--prompt", "grass sways in a light breeze",
            "--duration", "10", "--resolution", "2K",
            "--image", first, "--image", last,
            "--poll-interval", "0.01", "--output", self.output("h3-i2v.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "minimax-h3/image-to-video")
        self.assertEqual(payload["duration"], 10)
        self.assertEqual(payload["images"], [first, last])
        self.assertEqual(payload["metadata"], {
            "duration": 10,
            "resolution": "2K",
            "image_url": first,
            "end_image_url": last,
        })

    def test_minimax_h3_image_to_video_requires_reference_frame(self) -> None:
        result = self.invoke(
            "generate", "--model", "minimax-h3/image-to-video", "--prompt", "subtle motion",
            "--duration", "10", "--output", self.output("missing-frame.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires at least one", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])

    def test_kling_25_uses_string_duration_and_native_options(self) -> None:
        result = self.invoke(
            "generate", "--model", "kling-2.5-t2v", "--prompt", "camera dolly",
            "--duration", "10", "--negative-prompt", "blur", "--cfg-scale", "0.7",
            "--poll-interval", "0.01", "--output", self.output("k25.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "kling/v2-5-turbo-text-to-video-pro")
        self.assertEqual(payload["metadata"]["duration"], "10")
        self.assertEqual(payload["metadata"]["negative_prompt"], "blur")
        self.assertEqual(payload["metadata"]["cfg_scale"], 0.7)

    def test_kling_25_uses_five_second_model_default(self) -> None:
        result = self.invoke(
            "generate", "--model", "kling-2.5-t2v", "--prompt", "camera dolly",
            "--poll-interval", "0.01", "--output", self.output("k25-default.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["duration"], 5)
        self.assertEqual(payload["metadata"]["duration"], "5")

    def test_kling_3_images_sound_mode_and_advanced_metadata(self) -> None:
        image = "https://media.example/first.png"
        result = self.invoke(
            "generate", "--model", "kling-3", "--prompt", "the subject turns",
            "--duration", "7", "--image", image, "--mode", "4K", "--no-sound",
            "--metadata-json", '{"kling_elements":[{"name":"subject"}]}' ,
            "--poll-interval", "0.01", "--output", self.output("k3.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        metadata = payload["metadata"]
        self.assertEqual(metadata["image_urls"], [image])
        self.assertEqual(metadata["duration"], "7")
        self.assertEqual(metadata["mode"], "4K")
        self.assertFalse(metadata["sound"])
        self.assertEqual(metadata["kling_elements"], [{"name": "subject"}])

    def test_rejects_model_specific_invalid_values_before_request(self) -> None:
        result = self.invoke(
            "generate", "--model", "minimax-h3", "--prompt", "x",
            "--duration", "3", "--output", self.output("bad.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("4-15", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])

        result = self.invoke(
            "generate", "--model", "kling-2.5-t2v", "--prompt", "x",
            "--duration", "5", "--cfg-scale", "0.65", "--output", self.output("bad-scale.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("increments of 0.1", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])


if __name__ == "__main__":
    unittest.main()
