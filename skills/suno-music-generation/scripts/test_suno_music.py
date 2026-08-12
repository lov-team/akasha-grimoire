#!/usr/bin/env python3
"""No-network behavior tests for suno_music.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("suno_music.py")
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("suno_music", SCRIPT)
assert SPEC and SPEC.loader
suno_music = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suno_music)


class _SunoHandler(BaseHTTPRequestHandler):
    polls = 0
    payload: dict[str, object] | None = None

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, data: dict[str, object]) -> None:
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/gateway/suno/submit/MUSIC":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != "Bearer local-test-key":
            self.send_error(401)
            return
        length = int(self.headers.get("Content-Length", "0"))
        type(self).payload = json.loads(self.rfile.read(length))
        self._json({"code": "success", "data": "task_public"})

    def do_GET(self) -> None:
        if self.path == "/gateway/v1/models":
            self._json({"object": "list", "data": []})
            return
        if self.path == "/gateway/suno/fetch/task_public":
            type(self).polls += 1
            if type(self).polls == 1:
                self._json({"code": "success", "data": {"status": "IN_PROGRESS"}})
                return
            host = f"http://127.0.0.1:{self.server.server_port}"
            self._json(
                {
                    "code": "success",
                    "data": {
                        "status": "SUCCESS",
                        "data": [
                            {
                                "audio_url": f"{host}/files/song.mp3?signature=secret",
                                "image_url": f"{host}/files/cover.jpg?signature=secret",
                            }
                        ],
                    },
                }
            )
            return
        if self.path.startswith("/files/song.mp3"):
            body = b"fake-mp3"
            content_type = "audio/mpeg"
        elif self.path.startswith("/files/cover.jpg"):
            body = b"fake-jpeg"
            content_type = "image/jpeg"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SunoMusicTests(unittest.TestCase):
    def test_base_url_normalization_and_sensitive_rejection(self) -> None:
        self.assertEqual(
            suno_music._api_url("https://example.com", "/suno/submit/MUSIC"),
            "https://example.com/suno/submit/MUSIC",
        )
        self.assertEqual(
            suno_music._api_url("https://example.com/gateway/v1/", "/suno/submit/MUSIC"),
            "https://example.com/gateway/suno/submit/MUSIC",
        )
        for value, secret in [
            ("https://user:password@example.com/v1", "password"),
            ("https://example.com/v1?token=secret", "secret"),
        ]:
            with self.assertRaises(SystemExit) as caught:
                suno_music._api_url(value, "/suno/submit/MUSIC")
            self.assertNotIn(secret, str(caught.exception))

    def test_base_url_default_and_override_precedence(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(suno_music._base_url(None), "https://newapi.1234bot.com/v1")
        with mock.patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/v1",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(suno_music._base_url(None), "https://new-api.example/v1")
            self.assertEqual(
                suno_music._base_url("https://cli.example/v1"),
                "https://cli.example/v1",
            )

    def test_missing_key_message_links_lovbrowser_and_payment_flow(self) -> None:
        message = suno_music._missing_key_message()
        self.assertIn("https://lovbrowser.com", message)
        self.assertIn("QR code", message)
        self.assertIn("akasha_credentials.py finish", message)

    def test_submit_wait_and_download_stay_quiet_until_success(self) -> None:
        _SunoHandler.polls = 0
        _SunoHandler.payload = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), _SunoHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
                os.environ,
                {"LOVBROWSER_API_KEY": "local-test-key", "NEW_API_BASE_URL": ""},
                clear=False,
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc = suno_music.main(
                        [
                            "--description",
                            "warm acoustic city folk",
                            "--base-url",
                            f"http://127.0.0.1:{server.server_port}/gateway/v1",
                            "--output-dir",
                            temp_dir,
                            "--poll-seconds",
                            "0.01",
                            "--timeout-seconds",
                            "2",
                        ]
                    )
                self.assertEqual(rc, 0)
                output = stdout.getvalue()
                self.assertTrue(output.startswith("OK task_id=task_public songs=1 files=2\n"))
                self.assertNotIn("signature=secret", output)
                self.assertNotIn("IN_PROGRESS", output)
                self.assertEqual(Path(temp_dir, "suno-song-1.mp3").read_bytes(), b"fake-mp3")
                self.assertEqual(Path(temp_dir, "suno-song-1-cover.jpg").read_bytes(), b"fake-jpeg")
                self.assertEqual(
                    _SunoHandler.payload,
                    {
                        "make_instrumental": False,
                        "gpt_description_prompt": "warm acoustic city folk",
                        "mv": "V5_5",
                    },
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_malformed_success_has_no_ok_output(self) -> None:
        responses = [
            {"code": "success", "data": {"status": "SUCCESS", "data": []}}
        ]
        stdout = io.StringIO()
        with mock.patch.object(suno_music, "_request_json", side_effect=responses):
            with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit):
                suno_music._wait_for_result("task", "key", "https://example.com", 1, 0.01)
        self.assertNotIn("OK", stdout.getvalue())

    def test_server_default_omits_mv(self) -> None:
        args = mock.Mock(
            instrumental=True,
            description="minimal piano underscore",
            lyrics_file=None,
            model=None,
        )
        with mock.patch.object(
            suno_music,
            "_request_json",
            return_value={"code": "success", "data": "task"},
        ) as request:
            task_id = suno_music._submit(args, "key", "https://example.com")
        self.assertEqual(task_id, "task")
        payload = request.call_args.args[3]
        self.assertNotIn("mv", payload)

    def test_non_http_result_url_is_rejected_without_reading_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir, "secret.txt")
            source.write_text("sensitive", encoding="utf-8")
            destination = Path(temp_dir, "out.mp3")
            with self.assertRaises(SystemExit):
                suno_music._download(source.as_uri(), destination, False)
            self.assertFalse(destination.exists())

    def test_loader_identity_and_controller_catches_quota_from_real_loader(self) -> None:
        a = suno_music._load_akasha_recharge()
        b = suno_music._load_akasha_recharge()
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
                public_id="u1",
                status="SUCCEEDED",
                face_value_usd_cent=1000,
                currency="USD",
                expire_time=0,
                public_page_url="https://lovbrowser.example/pay/u1",
                status_url="https://lovbrowser.example/status/u1",
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
                suno_music._load_akasha_recharge().raise_quota_if_applicable(
                    403, body, base_url="https://newapi.1234bot.com/v1"
                )
            return "ok"

        with mock.patch.object(a, "perform_recharge", side_effect=fake_perform):
            self.assertEqual(controller.run(op), "ok")
        self.assertEqual(performed, [1])
        self.assertTrue(controller._recharge_attempted)

    def test_recharge_usd_cli_flag(self) -> None:
        parser = suno_music._parser()
        args = parser.parse_args(
            ["--description", "x", "--output-dir", "/tmp/suno", "--recharge-usd", "30"]
        )
        self.assertEqual(args.recharge_usd, "30")

    def test_fetch_quota_does_not_resubmit_with_shared_controller(self) -> None:
        recharge = suno_music._load_akasha_recharge()
        counts = {"submit": 0, "fetch": 0, "ticket": 0}
        PNG = b"\x89PNG\r\n\x1a\nqr"

        class Local(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002
                return

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(n)
                if self.path.endswith("/suno/submit/MUSIC"):
                    counts["submit"] += 1
                    body = json.dumps({"code": "success", "data": "task_suno"}).encode()
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
                            "publicId": "su1",
                            "status": "SUCCEEDED",
                            "faceValueUsdCent": 1000,
                            "currency": "USD",
                            "publicPageUrl": f"{host}/pay/su1",
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
                if "/suno/fetch/task_suno" in self.path:
                    counts["fetch"] += 1
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
                        body = json.dumps(
                            {
                                "code": "success",
                                "data": {"status": "SUCCESS", "data": [{"audio_url": "http://x/a.mp3"}]},
                            }
                        ).encode()
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
                if self.path.endswith("/sess/su1"):
                    body = json.dumps(
                        {
                            "publicId": "su1",
                            "status": "SUCCEEDED",
                            "faceValueUsdCent": 1000,
                            "currency": "USD",
                            "publicPageUrl": "http://127.0.0.1/pay/su1",
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
            base = f"http://127.0.0.1:{server.server_port}/gateway/v1"
            with tempfile.TemporaryDirectory() as tmp:
                ctrl = recharge.RechargeController(
                    api_key="k",
                    base_url="https://newapi.1234bot.com/v1",
                    cli_recharge_usd="10",
                    poll_interval=0.01,
                    poll_timeout=2.0,
                    sleep=lambda _s: None,
                    ticket_base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    allow_http_endpoints=True,
                    qr_parent_dir=tmp,
                    request_timeout=5,
                )
                submitted = suno_music._request_json(
                    "POST",
                    suno_music._api_url(base, "/suno/submit/MUSIC"),
                    "k",
                    {"gpt_description_prompt": "x"},
                    base_url=base,
                    controller=ctrl,
                )
                self.assertEqual(submitted.get("data"), "task_suno")

                def fetch() -> dict:
                    import urllib.error
                    import urllib.request

                    req = urllib.request.Request(
                        suno_music._api_url(base, "/suno/fetch/task_suno"),
                        headers={"Authorization": "Bearer k"},
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            return json.loads(resp.read().decode())
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

                data = ctrl.run(fetch)
                self.assertEqual(data["data"]["status"], "SUCCESS")
            self.assertEqual(counts["submit"], 1)
            self.assertEqual(counts["ticket"], 1)
            self.assertGreaterEqual(counts["fetch"], 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


    def test_real_request_json_catches_quota_via_same_controller(self) -> None:
        from email.message import Message
        from io import BytesIO
        from urllib.error import HTTPError
        import urllib.request

        recharge = suno_music._load_akasha_recharge()
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
        ok = json.dumps({"code": "success", "data": "task-wrap"}).encode()
        state = {"n": 0}

        class FakeOpener:
            def open(self, req: object, timeout: float = 0) -> object:
                state["n"] += 1
                if state["n"] == 1:
                    raise HTTPError("https://newapi.1234bot.com/v1/x", 403, "Forbidden", Message(), BytesIO(quota))
                class Resp:
                    def __enter__(self):
                        return self
                    def __exit__(self, *args: object) -> bool:
                        return False
                    def read(self) -> bytes:
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

        with mock.patch.object(recharge, "perform_recharge", side_effect=fake_perform):
            with mock.patch.object(urllib.request, "build_opener", return_value=FakeOpener()):
                data = suno_music._request_json(
                    "POST",
                    "https://newapi.1234bot.com/v1/suno/submit/MUSIC",
                    "k",
                    {"gpt_description_prompt": "x"},
                    base_url="https://newapi.1234bot.com/v1",
                    controller=controller,
                )
        self.assertEqual(data.get("data"), "task-wrap")
        self.assertEqual(performed, [1])
        self.assertTrue(controller._recharge_attempted)


if __name__ == "__main__":
    unittest.main()
