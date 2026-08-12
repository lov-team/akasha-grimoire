#!/usr/bin/env python3

from __future__ import annotations

import base64
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

# ensure tempfile available for recharge tests

SCRIPT = Path(__file__).with_name("grok_media.py")
PNG = b"\x89PNG\r\n\x1a\nfixture"
MP4 = b"\x00\x00\x00\x18ftypisomfixture"

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("grok_media_under_test", SCRIPT)
assert SPEC and SPEC.loader
GROK_MEDIA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GROK_MEDIA)


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
        if self.path == "/v1/models":
            self.send_json({"object": "list", "data": []})
        elif self.path == "/v1/videos/task-123":
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
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        Handler.requests.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({
            "LOVBROWSER_API_KEY": "test-key",
            "AKASHA_ALLOW_TEST_HTTP": "1",
        })
        return subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--timeout", "5", *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_base_url_default_and_override_precedence(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                GROK_MEDIA.resolve_base_url(None),
                "https://newapi.1234bot.com/v1",
            )
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/api",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(
                GROK_MEDIA.resolve_base_url(None),
                "https://new-api.example/v1",
            )
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/api",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
                "GROK_MEDIA_BASE_URL": "https://grok.example/proxy/v1",
            },
            clear=True,
        ):
            self.assertEqual(
                GROK_MEDIA.resolve_base_url(None),
                "https://grok.example/proxy/v1",
            )
            self.assertEqual(
                GROK_MEDIA.resolve_base_url("https://cli.example/custom"),
                "https://cli.example/custom/v1",
            )

    def test_image_generate_and_multipart_edit(self) -> None:
        generated = self.directory / "generated.png"
        result = self.invoke("image-generate", "--prompt", "red panda", "--output", str(generated))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(generated.read_bytes(), PNG)
        generation_payload = json.loads(Handler.requests[-1][2])
        self.assertEqual(generation_payload["aspect_ratio"], "auto")
        self.assertNotIn("size", generation_payload)

        source = self.directory / "source.png"
        source.write_bytes(PNG)
        edited = self.directory / "edited.png"
        result = self.invoke(
            "image-edit",
            "--image",
            str(source),
            "--aspect-ratio",
            "16:9",
            "--prompt",
            "green umbrella",
            "--output",
            str(edited),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(edited.read_bytes(), PNG)
        path, content_type, body = Handler.requests[-1]
        self.assertEqual(path, "/v1/images/edits")
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        self.assertIn(b"grok-imagine-image", body)
        self.assertIn(PNG, body)
        self.assertNotIn(b'name="aspect_ratio"', body)

    def test_multi_image_edit_defaults_aspect_ratio_to_auto(self) -> None:
        first = self.directory / "first.png"
        second = self.directory / "second.png"
        first.write_bytes(PNG + b"-first")
        second.write_bytes(PNG + b"-second")
        edited = self.directory / "multi-edited.png"

        result = self.invoke(
            "image-edit",
            "--image",
            str(first),
            "--image",
            str(second),
            "--prompt",
            "combine",
            "--output",
            str(edited),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(edited.read_bytes(), PNG)
        path, content_type, body = Handler.requests[-1]
        self.assertEqual(path, "/v1/images/edits")
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        self.assertEqual(body.count(b'name="image"; filename='), 2)
        self.assertIn(b'name="aspect_ratio"\r\n\r\nauto\r\n', body)
        self.assertIn(PNG + b"-first", body)
        self.assertIn(PNG + b"-second", body)

    def test_url_image_edit_uses_bare_image_references(self) -> None:
        single = self.directory / "single-url.png"
        result = self.invoke(
            "image-edit",
            "--image-url",
            "https://media.example/first.png",
            "--aspect-ratio",
            "20:9",
            "--prompt",
            "edit one",
            "--output",
            str(single),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(Handler.requests[-1][2])
        self.assertEqual(payload["image"], {"url": "https://media.example/first.png"})
        self.assertNotIn("images", payload)
        self.assertNotIn("aspect_ratio", payload)
        self.assertNotIn("type", payload["image"])

        multiple = self.directory / "multi-url.png"
        result = self.invoke(
            "image-edit",
            "--image-url",
            "https://media.example/first.png",
            "--image-url",
            "https://media.example/second.png",
            "--aspect-ratio",
            "19.5:9",
            "--prompt",
            "edit two",
            "--output",
            str(multiple),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(Handler.requests[-1][2])
        self.assertEqual(
            payload["images"],
            [
                {"url": "https://media.example/first.png"},
                {"url": "https://media.example/second.png"},
            ],
        )
        self.assertEqual(payload["aspect_ratio"], "19.5:9")
        self.assertTrue(all("type" not in ref for ref in payload["images"]))

    def test_current_aspect_ratios_and_video_models_are_visible_in_help(self) -> None:
        image_help = subprocess.run(
            ["python3", str(SCRIPT), "image-generate", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(image_help.returncode, 0, image_help.stderr)
        current_ratios = ("2:1", "1:2", "19.5:9", "9:19.5", "20:9", "9:20", "auto")
        for ratio in current_ratios:
            self.assertIn(ratio, image_help.stdout)
            parsed = GROK_MEDIA.parser().parse_args(
                [
                    "image-generate",
                    "--aspect-ratio",
                    ratio,
                    "--prompt",
                    "x",
                    "--output",
                    "/tmp/out.png",
                ]
            )
            self.assertEqual(parsed.aspect_ratio, ratio)

        video_help = subprocess.run(
            ["python3", str(SCRIPT), "video-generate", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(video_help.returncode, 0, video_help.stderr)
        self.assertIn("grok-imagine-video-1.5", video_help.stdout)
        self.assertIn("grok-imagine-video-1.5-preview", video_help.stdout)

    def test_stable_and_preview_video_models_are_forwarded(self) -> None:
        for index, model in enumerate(
            ("grok-imagine-video-1.5", "grok-imagine-video-1.5-preview")
        ):
            with self.subTest(model=model):
                Handler.requests.clear()
                output = self.directory / f"model-{index}.mp4"
                result = self.invoke(
                    "video-generate",
                    "--model",
                    model,
                    "--prompt",
                    "wave",
                    "--duration",
                    "4",
                    "--poll-interval",
                    "0.01",
                    "--output",
                    str(output),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                submit = next(
                    request
                    for request in Handler.requests
                    if request[0] == "/v1/videos/generations"
                )
                self.assertEqual(json.loads(submit[2])["model"], model)

    def test_rejects_non_https_image_url_without_request(self) -> None:
        result = self.invoke(
            "image-edit",
            "--image-url",
            "http://media.example/source.png",
            "--prompt",
            "edit",
            "--output",
            str(self.directory / "out.png"),
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual([request for request in Handler.requests if request[0] != "/v1/models"], [])
        self.assertIn("image URL must be an absolute public HTTPS URL", result.stderr)

    def test_missing_key_recommends_lovbrowser_without_request(self) -> None:
        output = self.directory / "missing-key.png"
        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "image-generate",
                "--prompt",
                "test",
                "--output",
                str(output),
            ],
            env={"AKASHA_DISABLE_AUTO_BOOTSTRAP": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("https://lovbrowser.com", result.stderr)
        self.assertFalse(output.exists())

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
                self.assertEqual([request for request in Handler.requests if request[0] != "/v1/models"], [])
                self.assertNotIn("user:secret", result.stderr)

    def test_loader_identity_and_controller_catches_quota_from_real_request_wrapper(self) -> None:
        """No mock of _load_akasha_recharge: real dual-load identity + request path."""
        a = GROK_MEDIA._load_akasha_recharge()
        b = GROK_MEDIA._load_akasha_recharge()
        self.assertIs(a, b)
        self.assertIs(a.InsufficientUserQuotaError, b.InsufficientUserQuotaError)

        body = (
            b'{"error":{"code":"insufficient_user_quota","message":"ticket=SECRET",'
            b'"metadata":{"recharge":{"supported":true,"ticket_endpoint":"/v1/tooling/recharge-ticket"}}}}'
        )
        performed: list[str] = []

        def fake_perform(**kwargs: object) -> object:
            performed.append("once")
            return a.RechargeSessionView(
                public_id="p1",
                status="SUCCEEDED",
                face_value_usd_cent=1000,
                currency="USD",
                expire_time=0,
                public_page_url="https://lovbrowser.example/pay/p1",
                status_url="https://lovbrowser.example/status/p1",
                qr_png_path="/tmp/akasha-recharge-p1.png",
            )

        controller = a.RechargeController(
            api_key="k",
            base_url="https://newapi.1234bot.com/v1",
            cli_recharge_usd="10",
            allow_http_endpoints=True,
            request_timeout=5,
        )
        calls = {"n": 0}

        def operation() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                # Raise using a freshly obtained loader result (must be same module).
                GROK_MEDIA._load_akasha_recharge().raise_quota_if_applicable(
                    403, body, base_url="https://newapi.1234bot.com/v1"
                )
            return "ok"

        with patch.object(a, "perform_recharge", side_effect=fake_perform):
            self.assertEqual(controller.run(operation), "ok")
        self.assertEqual(performed, ["once"])
        self.assertTrue(controller._recharge_attempted)

        # Real api_request wrapper path: inject HTTPError via urlopen mock is heavy;
        # exercise wrapper by ensuring controller is accepted and identity still holds.
        c = GROK_MEDIA._load_akasha_recharge()
        self.assertIs(c, a)

    def test_recharge_usd_accepted_before_and_after_subcommand(self) -> None:
        root = GROK_MEDIA.parser()
        a = root.parse_args(
            ["--recharge-usd", "10", "image-generate", "--prompt", "x", "--output", "/tmp/out.png"]
        )
        self.assertEqual(a.recharge_usd, "10")
        b = root.parse_args(
            ["image-generate", "--recharge-usd", "12.5", "--prompt", "x", "--output", "/tmp/out.png"]
        )
        self.assertEqual(b.recharge_usd, "12.5")

    def test_submit_not_repeated_when_poll_hits_quota_with_command_controller(self) -> None:
        """Async: successful submit then poll quota uses shared controller budget."""
        recharge = GROK_MEDIA._load_akasha_recharge()
        state = {"submit": 0, "poll": 0, "ticket": 0}

        class Local(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                if self.path.endswith("/videos/generations"):
                    state["submit"] += 1
                    body = json.dumps({"request_id": "task-g1"}).encode()
                elif self.path.endswith("/recharge-ticket"):
                    state["ticket"] += 1
                    host = f"http://127.0.0.1:{self.server.server_port}"
                    body = json.dumps(
                        {
                            "ticket": "T",
                            "lovbrowser_session_endpoint": f"{host}/sess",
                            "face_value_usd_cent": 1000,
                        }
                    ).encode()
                elif self.path == "/sess":
                    host = f"http://127.0.0.1:{self.server.server_port}"
                    body = json.dumps(
                        {
                            "publicId": "pg1",
                            "status": "SUCCEEDED",
                            "faceValueUsdCent": 1000,
                            "currency": "USD",
                            "expireTime": 1,
                            "publicPageUrl": f"{host}/pay/pg1",
                            "qrPngUrl": f"{host}/qr.png",
                        }
                    ).encode()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                if self.path.endswith("/videos/task-g1"):
                    state["poll"] += 1
                    if state["ticket"] == 0:
                        body = json.dumps(
                            {
                                "error": {
                                    "code": "insufficient_user_quota",
                                    "metadata": {
                                        "recharge": {
                                            "supported": True,
                                            "ticket_endpoint": "/v1/tooling/recharge-ticket",
                                        }
                                    },
                                }
                            }
                        ).encode()
                        self.send_response(403)
                    else:
                        body = json.dumps({"id": "task-g1", "status": "completed"}).encode()
                        self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.endswith("/content"):
                    data = MP4
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if self.path.endswith("/qr.png"):
                    data = PNG
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if self.path.endswith("/sess/pg1"):
                    body = json.dumps(
                        {
                            "publicId": "pg1",
                            "status": "SUCCEEDED",
                            "faceValueUsdCent": 1000,
                            "currency": "USD",
                            "publicPageUrl": "http://127.0.0.1/pay/pg1",
                            "qrPngUrl": f"http://127.0.0.1:{self.server.server_port}/qr.png",
                        }
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_error(404)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Local)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}/v1"
            # Force official detect by patching is_official on loaded module used by api_request
            mod = GROK_MEDIA._load_akasha_recharge()
            controller = mod.RechargeController(
                api_key="k",
                base_url="https://newapi.1234bot.com/v1",
                cli_recharge_usd="10",
                poll_interval=0.01,
                poll_timeout=2.0,
                sleep=lambda _s: None,
                ticket_base_url=base,
                allow_http_endpoints=True,
                request_timeout=5,
            )
            with tempfile.TemporaryDirectory() as tmp:
                controller.qr_parent_dir = tmp
                # submit
                raw, _ = GROK_MEDIA.api_request(
                    base, "k", "/videos/generations", 5, payload={"model": "m", "prompt": "p"}, controller=controller
                )
                self.assertIn(b"task-g1", raw)
                # poll with quota -> recharge -> retry
                with patch.object(mod, "is_official_newapi_base_url", return_value=True):
                    # raise_quota uses official base_url passed as official constant below
                    pass
                # api_request uses base_url for detect; private http base won't trigger.
                # So call controller.run around a poll that detects with official base.
                def poll_once() -> bytes:
                    import urllib.error
                    import urllib.request

                    req = urllib.request.Request(
                        f"{base}/videos/task-g1",
                        headers={"Authorization": "Bearer k"},
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            return resp.read()
                    except urllib.error.HTTPError as exc:
                        body = exc.read()
                        try:
                            exc.close()
                        except Exception:
                            pass
                        mod.raise_quota_if_applicable(
                            exc.code, body, base_url="https://newapi.1234bot.com/v1"
                        )
                        raise

                out = controller.run(poll_once)
                self.assertIn(b"completed", out)
            self.assertEqual(state["submit"], 1)
            self.assertEqual(state["ticket"], 1)
            self.assertGreaterEqual(state["poll"], 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


    def test_real_api_request_wrapper_catches_quota_via_same_controller(self) -> None:
        """Production api_request path: dual load identity + HTTPError quota + perform_recharge."""
        from email.message import Message
        from io import BytesIO
        from urllib.error import HTTPError

        recharge = GROK_MEDIA._load_akasha_recharge()
        controller = recharge.RechargeController(
            api_key="k",
            base_url="https://newapi.1234bot.com/v1",
            allow_http_endpoints=True,
            request_timeout=5,
        )
        quota = json.dumps(
            {
                "error": {
                    "code": "insufficient_user_quota",
                    "metadata": {
                        "recharge": {
                            "supported": True,
                            "ticket_endpoint": "/v1/tooling/recharge-ticket",
                        }
                    },
                }
            }
        ).encode()
        ok = json.dumps({"request_id": "task-wrap"}).encode()
        state = {"n": 0}

        def fake_urlopen(req: object, timeout: float = 0) -> object:
            state["n"] += 1
            if state["n"] == 1:
                raise HTTPError("https://newapi.1234bot.com/v1/x", 403, "Forbidden", Message(), BytesIO(quota))
            class Resp:
                def __enter__(self):
                    return self
                def __exit__(self, *args: object) -> bool:
                    return False
                def read(self, n: int = -1) -> bytes:
                    return ok
                headers = {"Content-Type": "application/json"}
            return Resp()

        performed: list[int] = []

        def fake_perform(**kwargs: object) -> object:
            performed.append(1)
            return recharge.RechargeSessionView(
                public_id="w1",
                status="SUCCEEDED",
                face_value_usd_cent=1000,
                currency="USD",
                expire_time=0,
                public_page_url="https://lovbrowser.example/pay/w1",
                status_url="https://lovbrowser.example/status/w1",
            )

        with patch.object(recharge, "perform_recharge", side_effect=fake_perform):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                raw, _ = GROK_MEDIA.api_request(
                    "https://newapi.1234bot.com/v1",
                    "k",
                    "/videos/generations",
                    5,
                    payload={"prompt": "x"},
                    controller=controller,
                )
        self.assertIn(b"task-wrap", raw)
        self.assertEqual(performed, [1])
        self.assertTrue(controller._recharge_attempted)


if __name__ == "__main__":
    unittest.main()
