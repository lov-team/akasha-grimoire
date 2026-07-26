#!/usr/bin/env python3

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).with_name("grok_media.py")
PNG = b"\x89PNG\r\n\x1a\nfixture"
MP4 = b"\x00\x00\x00\x18ftypisomfixture"


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
        self.requests.append((self.path, self.headers.get("Content-Type", ""), body))
        if self.path in {"/v1/images/generations", "/v1/images/edits"}:
            self.send_json({"created": 1, "data": [{"b64_json": base64.b64encode(PNG).decode()}]})
        else:
            self.send_json({"request_id": "task-123"})

    def do_GET(self) -> None:
        self.requests.append((self.path, self.headers.get("Content-Type", ""), b""))
        if self.path == "/v1/videos/task-123":
            self.send_json({"id": "task-123", "status": "completed", "metadata": {"url": "https://example.invalid/result.mp4"}})
        elif self.path == "/v1/videos/task-123/content":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(MP4)))
            self.end_headers()
            self.wfile.write(MP4)
        else:
            self.send_response(404)
            self.end_headers()


class GrokMediaScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join()

    def setUp(self) -> None:
        Handler.requests.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--timeout", "5", *args],
            env={"GROK_MEDIA_API_KEY": "test-key"},
            text=True,
            capture_output=True,
            check=False,
        )

    def test_image_generate_and_multipart_edit(self) -> None:
        generated = self.directory / "generated.png"
        result = self.invoke("image-generate", "--prompt", "red panda", "--output", str(generated))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(generated.read_bytes(), PNG)

        source = self.directory / "source.png"
        source.write_bytes(PNG)
        edited = self.directory / "edited.png"
        result = self.invoke("image-edit", "--image", str(source), "--prompt", "green umbrella", "--output", str(edited))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(edited.read_bytes(), PNG)
        path, content_type, body = Handler.requests[-1]
        self.assertEqual(path, "/v1/images/edits")
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        self.assertIn(b"grok-imagine-image", body)
        self.assertIn(PNG, body)

    def test_video_generate_and_edit_download_content(self) -> None:
        generated = self.directory / "generated.mp4"
        result = self.invoke("video-generate", "--prompt", "wave", "--duration", "4", "--poll-interval", "0.01", "--output", str(generated))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(generated.read_bytes(), MP4)

        edited = self.directory / "edited.mp4"
        result = self.invoke("video-edit", "--video-url", "https://media.example/source.mp4", "--prompt", "make it night", "--poll-interval", "0.01", "--output", str(edited))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(edited.read_bytes(), MP4)
        edit_requests = [entry for entry in Handler.requests if entry[0] == "/v1/videos/edits"]
        self.assertEqual(len(edit_requests), 1)
        payload = json.loads(edit_requests[0][2])
        self.assertEqual(payload["video"]["url"], "https://media.example/source.mp4")

        edited_by_id = self.directory / "edited-by-id.mp4"
        result = self.invoke("video-edit", "--video-file-id", "task-source", "--prompt", "make it night", "--poll-interval", "0.01", "--output", str(edited_by_id))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(edited_by_id.read_bytes(), MP4)
        edit_requests = [entry for entry in Handler.requests if entry[0] == "/v1/videos/edits"]
        self.assertEqual(len(edit_requests), 2)
        payload = json.loads(edit_requests[1][2])
        self.assertEqual(payload["video"]["file_id"], "task-source")

    def test_rejects_non_https_or_credentialed_video_url_without_request(self) -> None:
        for url in ("http://media.example/source.mp4", "file:///tmp/source.mp4", "https://user:secret@media.example/source.mp4"):
            with self.subTest(url=url):
                Handler.requests.clear()
                result = self.invoke("video-edit", "--video-url", url, "--prompt", "edit", "--output", str(self.directory / "out.mp4"))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(Handler.requests, [])
                self.assertNotIn("user:secret", result.stderr)


if __name__ == "__main__":
    unittest.main()
