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

SCRIPT = Path(__file__).with_name("seedance_video.py")
MP4 = b"\x00\x00\x00\x18ftypisomfixture"

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("seedance_video_under_test", SCRIPT)
assert SPEC and SPEC.loader
SEEDANCE_VIDEO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEEDANCE_VIDEO)


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
        self.send_json({"id": "task-seedance-123", "status": "queued"})

    def do_GET(self) -> None:
        self.requests.append((self.command, self.path, b""))
        if self.path == "/v1/models":
            self.send_json({"object": "list", "data": []})
        elif self.path == "/v1/video/generations/task-seedance-123":
            self.send_json({"code": "success", "data": {"task_id": "task-seedance-123", "status": "SUCCESS"}})
        elif self.path == "/v1/videos/task-seedance-123/content":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(MP4)))
            self.end_headers()
            self.wfile.write(MP4)
        else:
            self.send_response(404)
            self.end_headers()


class SeedanceVideoScriptTest(unittest.TestCase):
    def test_base_url_default_and_override_precedence(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                SEEDANCE_VIDEO.resolve_base_url(None),
                "https://newapi.1234bot.com/v1",
            )
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/v1",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(
                SEEDANCE_VIDEO.resolve_base_url(None),
                "https://new-api.example/v1",
            )
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/v1",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
                "SEEDANCE_VIDEO_BASE_URL": "https://seedance.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(
                SEEDANCE_VIDEO.resolve_base_url(None),
                "https://seedance.example/v1",
            )
            self.assertEqual(
                SEEDANCE_VIDEO.resolve_base_url("https://cli.example/custom"),
                "https://cli.example/custom/v1",
            )

    def test_missing_key_message_links_lovbrowser_and_payment_flow(self) -> None:
        with patch.dict(os.environ, {"AKASHA_DISABLE_AUTO_BOOTSTRAP": "1"}, clear=True), self.assertRaises(
            SEEDANCE_VIDEO.SeedanceVideoError
        ) as caught:
            SEEDANCE_VIDEO.read_api_key()
        message = str(caught.exception)
        self.assertIn("https://lovbrowser.com", message)
        self.assertIn("akasha_credentials.py start", message)

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

    def test_generate_preserves_references_and_downloads_completed_video(self) -> None:
        output = Path(self.temp_dir.name) / "result.mp4"
        result = self.invoke(
            "generate",
            "--prompt", "wave to camera",
            "--duration", "10",
            "--first-frame", "https://media.example/first.png",
            "--reference-video", "https://media.example/reference.mp4",
            "--no-generate-audio",
            "--poll-interval", "0.01",
            "--output", str(output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_bytes(), MP4)
        method, path, body = [request for request in Handler.requests if request[1] != "/v1/models"][0]
        self.assertEqual((method, path), ("POST", "/v1/video/generations"))
        payload = json.loads(body)
        self.assertEqual(payload["prompt"], "wave to camera")
        self.assertEqual(payload["duration"], 10)
        self.assertEqual(payload["metadata"]["duration"], 10)
        self.assertFalse(payload["metadata"]["generate_audio"])
        self.assertEqual(payload["metadata"]["content"][0]["role"], "first_frame")
        self.assertEqual(payload["metadata"]["content"][1]["type"], "video_url")
        self.assertEqual(payload["metadata"]["content"][1]["role"], "reference_video")

    def test_generate_reads_multiline_prompt_from_utf8_file(self) -> None:
        prompt_file = Path(self.temp_dir.name) / "director-prompt.txt"
        prompt_file.write_text(
            "【全局】写实电影风格。\n"
            "【时间轴】\n"
            "0.00–2.00秒：低机位远景，镜头小幅慢推。\n"
            "2.00–5.00秒：中景侧跟，人物向画面左侧奔跑。\n",
            encoding="utf-8",
        )
        output = Path(self.temp_dir.name) / "prompt-file.mp4"

        result = self.invoke(
            "generate",
            "--prompt-file", str(prompt_file),
            "--duration", "5",
            "--poll-interval", "0.01",
            "--output", str(output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads([request for request in Handler.requests if request[1] != "/v1/models"][0][2])
        self.assertEqual(payload["prompt"], prompt_file.read_text(encoding="utf-8").strip())

    def test_generate_rejects_empty_prompt_file_before_request(self) -> None:
        prompt_file = Path(self.temp_dir.name) / "empty.txt"
        prompt_file.write_text(" \n\t", encoding="utf-8")
        output = Path(self.temp_dir.name) / "empty.mp4"

        result = self.invoke(
            "generate",
            "--prompt-file", str(prompt_file),
            "--output", str(output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prompt file is empty", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])
        self.assertFalse(output.exists())

    def test_generate_requires_exactly_one_prompt_source(self) -> None:
        prompt_file = Path(self.temp_dir.name) / "prompt.txt"
        prompt_file.write_text("camera pushes in", encoding="utf-8")
        output = Path(self.temp_dir.name) / "conflict.mp4"

        result = self.invoke(
            "generate",
            "--prompt", "camera pans right",
            "--prompt-file", str(prompt_file),
            "--output", str(output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not allowed with argument", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])

    def test_seedance_1_pro_uses_ark_model_and_twelve_second_limit(self) -> None:
        output = Path(self.temp_dir.name) / "pro.mp4"
        result = self.invoke(
            "generate",
            "--model", "seedance-1.0-pro",
            "--prompt", "camera pans across a garden",
            "--duration", "12",
            "--poll-interval", "0.01",
            "--output", str(output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads([request for request in Handler.requests if request[1] != "/v1/models"][0][2])
        self.assertEqual(payload["model"], "doubao-seedance-1-0-pro-250528")
        self.assertFalse(payload["metadata"]["generate_audio"])

    def test_seedance_1_lite_alias_selects_t2v_or_i2v(self) -> None:
        text_output = Path(self.temp_dir.name) / "lite-text.mp4"
        text_result = self.invoke(
            "generate",
            "--model", "seedance-1.0-lite",
            "--prompt", "clouds move over a lake",
            "--poll-interval", "0.01",
            "--output", str(text_output),
        )
        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        text_payload = json.loads([request for request in Handler.requests if request[1] != "/v1/models"][0][2])
        self.assertEqual(text_payload["model"], "doubao-seedance-1-0-lite-t2v-250428")

        Handler.requests.clear()
        image_output = Path(self.temp_dir.name) / "lite-image.mp4"
        image_result = self.invoke(
            "generate",
            "--model", "seedance-1.0-lite",
            "--prompt", "the character waves",
            "--first-frame", "https://media.example/character.png",
            "--poll-interval", "0.01",
            "--output", str(image_output),
        )
        self.assertEqual(image_result.returncode, 0, image_result.stderr)
        image_payload = json.loads([request for request in Handler.requests if request[1] != "/v1/models"][0][2])
        self.assertEqual(image_payload["model"], "doubao-seedance-1-0-lite-i2v-250428")

    def test_rejects_unsupported_seedance_1_inputs_before_request(self) -> None:
        output = Path(self.temp_dir.name) / "invalid.mp4"
        result = self.invoke(
            "generate",
            "--model", "seedance-1.5-pro",
            "--prompt", "wave",
            "--reference-video", "https://media.example/reference.mp4",
            "--output", str(output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not accept video or audio references", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])
        self.assertFalse(output.exists())

    def test_loader_identity_and_controller_catches_quota_from_real_loader(self) -> None:
        a = SEEDANCE_VIDEO._load_akasha_recharge()
        b = SEEDANCE_VIDEO._load_akasha_recharge()
        self.assertIs(a, b)
        self.assertIs(a.InsufficientUserQuotaError, b.InsufficientUserQuotaError)
        body = (
            b'{"error":{"code":"insufficient_user_quota","metadata":'
            b'{"recharge":{"supported":true,"ticket_endpoint":"/v1/tooling/recharge-ticket"}}}}'
        )
        performed: list[int] = []

        def fake_perform(**kwargs: object) -> object:
            performed.append(1)
            return a.RechargeSessionView(
                public_id="s1",
                status="SUCCEEDED",
                face_value_usd_cent=1000,
                currency="USD",
                expire_time=0,
                public_page_url="https://lovbrowser.example/pay/s1",
                status_url="https://lovbrowser.example/status/s1",
            )

        controller = a.RechargeController(
            api_key="k",
            base_url="https://newapi.1234bot.com/v1",
            allow_http_endpoints=True,
        )
        n = {"v": 0}

        def op() -> str:
            n["v"] += 1
            if n["v"] == 1:
                SEEDANCE_VIDEO._load_akasha_recharge().raise_quota_if_applicable(
                    403, body, base_url="https://newapi.1234bot.com/v1"
                )
            return "done"

        with patch.object(a, "perform_recharge", side_effect=fake_perform):
            self.assertEqual(controller.run(op), "done")
        self.assertEqual(performed, [1])
        self.assertTrue(controller._recharge_attempted)

    def test_recharge_usd_accepted_before_and_after_subcommand(self) -> None:
        parser = SEEDANCE_VIDEO.build_parser()
        a = parser.parse_args(
            ["--recharge-usd", "25", "generate", "--prompt", "x", "--output", "/tmp/out.mp4"]
        )
        self.assertEqual(a.recharge_usd, "25")
        b = parser.parse_args(
            ["generate", "--recharge-usd", "30", "--prompt", "x", "--output", "/tmp/out.mp4"]
        )
        self.assertEqual(b.recharge_usd, "30")

    def test_poll_quota_does_not_resubmit_with_shared_controller(self) -> None:
        recharge = SEEDANCE_VIDEO._load_akasha_recharge()
        counts = {"submit": 0, "poll": 0, "ticket": 0}
        PNG = b"\x89PNG\r\n\x1a\nqr"

        class Local(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002
                return

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(n)
                if self.path.endswith("/video/generations"):
                    counts["submit"] += 1
                    body = json.dumps({"id": "task-s1"}).encode()
                elif self.path.endswith("/recharge-ticket"):
                    counts["ticket"] += 1
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
                            "publicId": "ps1",
                            "status": "SUCCEEDED",
                            "faceValueUsdCent": 1000,
                            "currency": "USD",
                            "publicPageUrl": f"{host}/pay/ps1",
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
                if "/video/generations/task-s1" in self.path:
                    counts["poll"] += 1
                    if counts["ticket"] == 0:
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
                        body = json.dumps({"data": {"status": "SUCCESS"}}).encode()
                        self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.endswith("/qr.png"):
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(PNG)))
                    self.end_headers()
                    self.wfile.write(PNG)
                    return
                if self.path.endswith("/sess/ps1"):
                    body = json.dumps(
                        {
                            "publicId": "ps1",
                            "status": "SUCCEEDED",
                            "faceValueUsdCent": 1000,
                            "currency": "USD",
                            "publicPageUrl": "http://127.0.0.1/pay/ps1",
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
            with tempfile.TemporaryDirectory() as tmp:
                ctrl = recharge.RechargeController(
                    api_key="k",
                    base_url="https://newapi.1234bot.com/v1",
                    cli_recharge_usd="10",
                    poll_interval=0.01,
                    poll_timeout=2.0,
                    sleep=lambda _s: None,
                    ticket_base_url=base,
                    allow_http_endpoints=True,
                    qr_parent_dir=tmp,
                    request_timeout=5,
                )
                raw, _ = SEEDANCE_VIDEO.request(
                    base, "k", "/video/generations", 5, {"model": "m", "prompt": "p"}, controller=ctrl
                )
                self.assertIn(b"task-s1", raw)

                def poll() -> bytes:
                    import urllib.error
                    import urllib.request

                    req = urllib.request.Request(
                        f"{base}/video/generations/task-s1",
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
                        recharge.raise_quota_if_applicable(
                            exc.code, body, base_url="https://newapi.1234bot.com/v1"
                        )
                        raise

                out = ctrl.run(poll)
                self.assertIn(b"SUCCESS", out)
            self.assertEqual(counts["submit"], 1)
            self.assertEqual(counts["ticket"], 1)
            self.assertGreaterEqual(counts["poll"], 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_seedance_1_5_enables_native_audio_generation(self) -> None:
        output = Path(self.temp_dir.name) / "seedance-15.mp4"
        result = self.invoke(
            "generate",
            "--model", "doubao-seedance-1-5-pro-251215",
            "--prompt", "a singer performs on stage",
            "--poll-interval", "0.01",
            "--output", str(output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads([request for request in Handler.requests if request[1] != "/v1/models"][0][2])
        self.assertTrue(payload["metadata"]["generate_audio"])

    def test_explicit_lite_modes_validate_image_input(self) -> None:
        output = Path(self.temp_dir.name) / "invalid-lite.mp4"
        i2v_result = self.invoke(
            "generate",
            "--model", "doubao-seedance-1-0-lite-i2v-250428",
            "--prompt", "wave",
            "--output", str(output),
        )
        self.assertNotEqual(i2v_result.returncode, 0)
        self.assertIn("requires an image reference", i2v_result.stderr)

        t2v_result = self.invoke(
            "generate",
            "--model", "doubao-seedance-1-0-lite-t2v-250428",
            "--prompt", "wave",
            "--first-frame", "https://media.example/character.png",
            "--output", str(output),
        )
        self.assertNotEqual(t2v_result.returncode, 0)
        self.assertIn("does not accept image references", t2v_result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])
        self.assertFalse(output.exists())

    def test_rejects_duration_above_model_limit_before_request(self) -> None:
        output = Path(self.temp_dir.name) / "too-long.mp4"
        result = self.invoke(
            "generate",
            "--model", "seedance-1.0-pro",
            "--prompt", "wave",
            "--duration", "13",
            "--output", str(output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("between 4 and 12 seconds", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])
        self.assertFalse(output.exists())

    def test_rejects_non_https_reference_before_request(self) -> None:
        output = Path(self.temp_dir.name) / "result.mp4"
        result = self.invoke(
            "generate",
            "--prompt", "wave",
            "--first-frame", "http://media.example/first.png",
            "--output", str(output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])
        self.assertFalse(output.exists())


    def test_real_request_wrapper_catches_quota_via_same_controller(self) -> None:
        from email.message import Message
        from io import BytesIO
        from urllib.error import HTTPError

        recharge = SEEDANCE_VIDEO._load_akasha_recharge()
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
        ok = json.dumps({"id": "task-wrap"}).encode()
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
                raw, _ = SEEDANCE_VIDEO.request(
                    "https://newapi.1234bot.com/v1",
                    "k",
                    "/video/generations",
                    5,
                    {"prompt": "x"},
                    controller=controller,
                )
        self.assertIn(b"task-wrap", raw)
        self.assertEqual(performed, [1])
        self.assertTrue(controller._recharge_attempted)


if __name__ == "__main__":
    unittest.main()
