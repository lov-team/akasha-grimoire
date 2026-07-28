#!/usr/bin/env python3
"""Focused unit and fake-HTTP E2E tests for shared/akasha_recharge (no real network)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import warnings
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import mock

sys.dont_write_bytecode = True

SHARED = Path(__file__).with_name("akasha_recharge.py")
SPEC = importlib.util.spec_from_file_location("akasha_recharge_under_test", SHARED)
assert SPEC and SPEC.loader
assert SHARED.is_file(), "akasha_recharge.py must exist for tests"
recharge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recharge
SPEC.loader.exec_module(recharge)

PNG = b"\x89PNG\r\n\x1a\n" + b"qr-fixture-bytes"


def _require_module() -> Any:
    return recharge


class ResolveAmountTests(unittest.TestCase):
    def test_default_is_10_usd_cents(self) -> None:
        mod = _require_module()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(mod.resolve_face_value_usd_cent(None), 1000)

    def test_env_and_cli_priority(self) -> None:
        mod = _require_module()
        with mock.patch.dict(os.environ, {"AKASHA_RECHARGE_USD": "20"}, clear=True):
            self.assertEqual(mod.resolve_face_value_usd_cent(None), 2000)
            self.assertEqual(mod.resolve_face_value_usd_cent("15"), 1500)
            self.assertEqual(mod.resolve_face_value_usd_cent("15.50"), 1550)

    def test_rejects_illegal_precision_and_bounds(self) -> None:
        mod = _require_module()
        with mock.patch.dict(os.environ, {}, clear=True):
            for bad in ("abc", "10.001", "NaN", "Infinity", "0.5", "0", "10001", "-1"):
                with self.assertRaises(mod.AkashaRechargeError):
                    mod.resolve_face_value_usd_cent(bad)
            self.assertEqual(mod.resolve_face_value_usd_cent("1"), 100)
            self.assertEqual(mod.resolve_face_value_usd_cent("10000"), 1_000_000)

    def test_env_not_read_when_use_env_false(self) -> None:
        mod = _require_module()
        with mock.patch.dict(os.environ, {"AKASHA_RECHARGE_USD": "not-a-number"}, clear=True):
            self.assertEqual(mod.resolve_face_value_usd_cent(None, use_env=False), 1000)
            mod.validate_cli_recharge_usd(None)
            with self.assertRaises(mod.AkashaRechargeError):
                mod.validate_cli_recharge_usd("bad")


class OfficialOriginTests(unittest.TestCase):
    def test_official_origin_allowed_variants(self) -> None:
        mod = _require_module()
        for value in (
            "https://newapi.1234bot.com/v1",
            "https://newapi.1234bot.com",
            "https://newapi.1234bot.com/v1/",
            "https://newapi.1234bot.com/gateway/v1",
            "HTTPS://NEWAPI.1234BOT.COM/v1",
        ):
            self.assertTrue(mod.is_official_newapi_base_url(value), value)

    def test_spoofed_origins_rejected(self) -> None:
        mod = _require_module()
        for value in (
            "http://newapi.1234bot.com/v1",
            "https://newapi.1234bot.com:8443/v1",
            "https://user:pass@newapi.1234bot.com/v1",
            "https://evil-newapi.1234bot.com/v1",
            "https://newapi.1234bot.com.evil.example/v1",
            "https://newapi.1234bot.com.evil.com/v1",
            "https://private.example/v1",
            "https://1234bot.com/v1",
            "https://newapi.1234bot.com.attacker/v1",
        ):
            self.assertFalse(mod.is_official_newapi_base_url(value), value)


class TriggerDetectionTests(unittest.TestCase):
    def _quota_body(self, **overrides: Any) -> bytes:
        payload: dict[str, Any] = {
            "error": {
                "message": "insufficient user quota",
                "type": "new_api_error",
                "code": "insufficient_user_quota",
                "metadata": {
                    "recharge": {
                        "supported": True,
                        "ticket_endpoint": "/v1/tooling/recharge-ticket",
                        "default_face_value_usd_cent": 1000,
                    }
                },
            }
        }
        error = payload["error"]
        for key, value in overrides.items():
            if key == "metadata":
                error["metadata"] = value
            elif key == "code":
                error["code"] = value
            else:
                error[key] = value
        return json.dumps(payload).encode()

    def test_exact_three_conditions_trigger(self) -> None:
        mod = _require_module()
        hint = mod.detect_insufficient_user_quota(
            403,
            self._quota_body(),
            base_url="https://newapi.1234bot.com/v1",
        )
        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertEqual(hint.ticket_endpoint, "/v1/tooling/recharge-ticket")

    def test_non_matching_errors_do_not_trigger(self) -> None:
        mod = _require_module()
        base = "https://newapi.1234bot.com/v1"
        cases = [
            (401, self._quota_body()),
            (403, json.dumps({"error": {"code": "subscription_token_exhausted", "metadata": {"recharge": {"supported": True}}}}).encode()),
            (403, json.dumps({"error": {"code": "insufficient_user_quota", "metadata": {"recharge": {"supported": False}}}}).encode()),
            (403, json.dumps({"error": {"code": "insufficient_user_quota"}}).encode()),
            (403, json.dumps({"error": {"code": "insufficient_user_quota", "metadata": {}}}).encode()),
            (403, b"not-json"),
        ]
        for status, body in cases:
            self.assertIsNone(mod.detect_insufficient_user_quota(status, body, base_url=base))
        self.assertIsNone(
            mod.detect_insufficient_user_quota(
                403, self._quota_body(), base_url="https://private.example/v1"
            )
        )


class SensitiveEventTests(unittest.TestCase):
    def test_event_omits_secrets_ticket_and_pay_url(self) -> None:
        mod = _require_module()
        event = mod.build_recharge_event(
            public_id="pub_abc",
            status="PENDING_PAYMENT",
            face_value_usd_cent=1000,
            currency="USD",
            expire_time=1_700_000_000,
            qr_png_path="/tmp/akasha-recharge-x/pub_abc.png",
            public_page_url="https://lovbrowser.example/pay/pub_abc",
            status_url="https://lovbrowser.example/api/v1/tooling/api-recharge-sessions/pub_abc",
        )
        encoded = json.dumps(event, ensure_ascii=False)
        for forbidden in ("ticket", "authorization", "api_key", "apiKey", "payUrl", "pay_url", "Bearer"):
            self.assertNotIn(forbidden, event)
            if forbidden not in {"ticket"}:  # statusUrl path may contain tooling words only
                pass
        self.assertNotIn("payUrl", encoded)
        self.assertEqual(event["publicId"], "pub_abc")
        self.assertEqual(event["qrPngPath"], "/tmp/akasha-recharge-x/pub_abc.png")
        self.assertEqual(event["publicPageUrl"], "https://lovbrowser.example/pay/pub_abc")
        self.assertEqual(event["statusUrl"], "https://lovbrowser.example/api/v1/tooling/api-recharge-sessions/pub_abc")
        # Fields required for Codex to render QR + offer public page
        for key in ("qrPngPath", "publicPageUrl", "statusUrl", "publicId", "status", "faceValueUsdCent"):
            self.assertIn(key, event)

    def test_safe_error_message_never_echoes_server_secrets(self) -> None:
        mod = _require_module()
        detail = mod._safe_status_detail(
            403,
            {
                "error": {
                    "code": "bad",
                    "message": "ticket=COMPACT_SECRET Authorization=Bearer KEY payUrl=https://pay/secret",
                }
            },
        )
        self.assertIn("HTTP 403", detail)
        self.assertIn("code=bad", detail)
        self.assertNotIn("COMPACT_SECRET", detail)
        self.assertNotIn("Bearer KEY", detail)
        self.assertNotIn("payUrl", detail)
        self.assertNotIn("ticket=", detail)


class DecimalCentMathTests(unittest.TestCase):
    def test_decimal_exact_cents(self) -> None:
        mod = _require_module()
        self.assertEqual(mod.usd_to_cents(Decimal("10")), 1000)
        self.assertEqual(mod.usd_to_cents(Decimal("10.00")), 1000)
        self.assertEqual(mod.usd_to_cents(Decimal("1.23")), 123)
        with self.assertRaises(mod.AkashaRechargeError):
            mod.usd_to_cents(Decimal("1.234"))


class _RechargeHTTPState:
    gen_calls = 0
    poll_calls = 0
    ticket_calls = 0
    session_posts = 0
    status_calls = 0
    qr_calls = 0
    ticket_auths: list[str | None] = []
    session_auths: list[str | None] = []
    session_bodies: list[bytes] = []
    ticket_face_values: list[Any] = []
    status_sequence: list[str] = ["PENDING_PAYMENT", "CREDITING", "SUCCEEDED"]
    mode = "happy"
    enterprise = False
    redirect_ticket = False
    async_submit_ok_then_poll_quota = False
    second_poll_quota_after_recharge = False
    content_after_poll = False
    _recharged_once = False


class _RechargeHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _read(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length else b""

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _quota(self) -> None:
        self._json(
            403,
            {
                "error": {
                    "code": "insufficient_user_quota",
                    "message": "ticket=SHOULD_NOT_LEAK Authorization=Bearer LEAK_KEY",
                    "metadata": {
                        "recharge": {
                            "supported": True,
                            "ticket_endpoint": "/v1/tooling/recharge-ticket",
                            "default_face_value_usd_cent": 1000,
                        }
                    },
                }
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        body = self._read()
        auth = self.headers.get("Authorization")
        if self.path in {"/v1/images/generations", "/v1/images/edits", "/v1/video/generations", "/v1/videos/generations", "/suno/submit/MUSIC"}:
            _RechargeHTTPState.gen_calls += 1
            if _RechargeHTTPState.mode == "always_quota":
                self._quota()
                return
            if _RechargeHTTPState.async_submit_ok_then_poll_quota:
                # submit always succeeds
                if self.path == "/suno/submit/MUSIC":
                    self._json(200, {"code": "success", "data": "task_public"})
                else:
                    self._json(200, {"id": "task-async-1", "request_id": "task-async-1", "status": "queued"})
                return
            if _RechargeHTTPState.mode == "happy" and _RechargeHTTPState.gen_calls == 1:
                self._quota()
                return
            if self.path == "/suno/submit/MUSIC":
                self._json(200, {"code": "success", "data": "task_public"})
            else:
                self._json(200, {"created": 1, "data": [{"b64_json": "aGk="}], "id": "task-async-1", "request_id": "task-async-1"})
            return
        if self.path == "/v1/tooling/recharge-ticket":
            if _RechargeHTTPState.redirect_ticket:
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:9/steal")
                self.end_headers()
                return
            _RechargeHTTPState.ticket_calls += 1
            _RechargeHTTPState.ticket_auths.append(auth)
            try:
                parsed = json.loads(body.decode() or "{}")
            except json.JSONDecodeError:
                parsed = {}
            _RechargeHTTPState.ticket_face_values.append(parsed.get("face_value_usd_cent"))
            host = f"http://127.0.0.1:{self.server.server_port}"
            self._json(
                200,
                {
                    "ticket": "COMPACT_TICKET_SECRET_DO_NOT_LEAK",
                    "issued_at": 0,
                    "expires_at": 0,
                    "expires_in_seconds": 300,
                    "lovbrowser_session_endpoint": f"{host}/api/v1/tooling/api-recharge-sessions",
                    "face_value_usd_cent": parsed.get("face_value_usd_cent", 1000),
                },
            )
            return
        if self.path == "/api/v1/tooling/api-recharge-sessions":
            _RechargeHTTPState.session_posts += 1
            _RechargeHTTPState.session_auths.append(auth)
            _RechargeHTTPState.session_bodies.append(body)
            if _RechargeHTTPState.enterprise:
                self._json(
                    403,
                    {
                        "error": {
                            "code": "enterprise_member_key_forbidden",
                            "message": "enterprise wallet only; token=SENSITIVE_TOKEN",
                        }
                    },
                )
                return
            host = f"http://127.0.0.1:{self.server.server_port}"
            self._json(
                200,
                {
                    "publicId": "pub_test_1",
                    "status": "PENDING_PAYMENT",
                    "faceValueUsdCent": 1000,
                    "currency": "USD",
                    "expireTime": 1_700_000_000,
                    "publicPageUrl": f"{host}/pay/pub_test_1",
                    "payUrl": f"{host}/pay/pub_test_1/checkout?sig=SECRET_PAY",
                    "qrPngUrl": f"{host}/qr/pub_test_1.png",
                    "message": "scan to pay ticket=COMPACT_TICKET_SECRET",
                },
            )
            return
        self.send_error(404)

    def do_GET(self) -> None:  # noqa: N802
        # async poll / content paths
        if self.path in {
            "/v1/videos/task-async-1",
            "/v1/video/generations/task-async-1",
            "/suno/fetch/task_public",
        }:
            _RechargeHTTPState.poll_calls += 1
            if _RechargeHTTPState.async_submit_ok_then_poll_quota:
                # First poll after submit -> quota once; after recharge, second poll may quota again for budget test
                if _RechargeHTTPState.poll_calls == 1 and not _RechargeHTTPState._recharged_once:
                    # Before recharge: quota
                    if _RechargeHTTPState.ticket_calls == 0:
                        self._quota()
                        return
                if _RechargeHTTPState.second_poll_quota_after_recharge and _RechargeHTTPState.ticket_calls >= 1:
                    # After recharge happened, next poll still quota -> controller must stop without 2nd ticket
                    self._quota()
                    return
                # success terminal for poll
                if self.path.startswith("/suno/"):
                    host = f"http://127.0.0.1:{self.server.server_port}"
                    self._json(
                        200,
                        {
                            "code": "success",
                            "data": {
                                "status": "SUCCESS",
                                "data": [{"audio_url": f"{host}/files/song.mp3"}],
                            },
                        },
                    )
                else:
                    self._json(200, {"id": "task-async-1", "status": "completed", "data": {"status": "SUCCESS"}})
                return
            self._json(200, {"id": "task-async-1", "status": "completed", "data": {"status": "SUCCESS"}})
            return
        if self.path in {"/v1/videos/task-async-1/content", "/v1/videos/task-async-1/content"}:
            body = b"\x00\x00\x00\x18ftypisomfixture"
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/v1/tooling/api-recharge-sessions/pub_test_1":
            _RechargeHTTPState.status_calls += 1
            if _RechargeHTTPState.ticket_calls > 0:
                _RechargeHTTPState._recharged_once = True
            if _RechargeHTTPState.mode == "expired":
                status = "EXPIRED"
            elif _RechargeHTTPState.mode == "failed":
                status = "FAILED"
            elif _RechargeHTTPState.mode == "timeout_credit":
                status = "CREDITING"
            else:
                idx = min(_RechargeHTTPState.status_calls - 1, len(_RechargeHTTPState.status_sequence) - 1)
                status = _RechargeHTTPState.status_sequence[idx]
            host = f"http://127.0.0.1:{self.server.server_port}"
            self._json(
                200,
                {
                    "publicId": "pub_test_1",
                    "status": status,
                    "faceValueUsdCent": 1000,
                    "currency": "USD",
                    "expireTime": 1_700_000_000,
                    "publicPageUrl": f"{host}/pay/pub_test_1",
                    "payUrl": f"{host}/pay/pub_test_1/checkout?sig=SECRET_PAY",
                    "qrPngUrl": f"{host}/qr/pub_test_1.png",
                    "message": f"{status} ticket=COMPACT_TICKET_SECRET",
                },
            )
            return
        if self.path == "/qr/pub_test_1.png":
            _RechargeHTTPState.qr_calls += 1
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG)))
            self.end_headers()
            self.wfile.write(PNG)
            return
        if self.path.startswith("/files/song.mp3"):
            body = b"fake-mp3"
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)


class FakeHttpE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _RechargeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port
        cls.base = f"http://127.0.0.1:{cls.port}/v1"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        _RechargeHTTPState.gen_calls = 0
        _RechargeHTTPState.poll_calls = 0
        _RechargeHTTPState.ticket_calls = 0
        _RechargeHTTPState.session_posts = 0
        _RechargeHTTPState.status_calls = 0
        _RechargeHTTPState.qr_calls = 0
        _RechargeHTTPState.ticket_auths = []
        _RechargeHTTPState.session_auths = []
        _RechargeHTTPState.session_bodies = []
        _RechargeHTTPState.ticket_face_values = []
        _RechargeHTTPState.status_sequence = ["PENDING_PAYMENT", "CREDITING", "SUCCEEDED"]
        _RechargeHTTPState.mode = "happy"
        _RechargeHTTPState.enterprise = False
        _RechargeHTTPState.redirect_ticket = False
        _RechargeHTTPState.async_submit_ok_then_poll_quota = False
        _RechargeHTTPState.second_poll_quota_after_recharge = False
        _RechargeHTTPState.content_after_poll = False
        _RechargeHTTPState._recharged_once = False

    def _controller(self, tmp: str, sink: io.StringIO, cli: str | None = "10") -> Any:
        mod = _require_module()
        return mod.RechargeController(
            api_key="test-key-secret",
            base_url="https://newapi.1234bot.com/v1",
            cli_recharge_usd=cli,
            poll_interval=0.01,
            poll_timeout=2.0,
            qr_parent_dir=tmp,
            event_file=sink,
            sleep=lambda _s: None,
            ticket_base_url=self.base,
            allow_http_endpoints=True,
        )

    def _quota_operation(self, path: str = "/v1/images/generations") -> Any:
        mod = _require_module()

        def operation() -> str:
            import urllib.error
            import urllib.request

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}{path}",
                data=b"{}",
                headers={
                    "Authorization": "Bearer test-key-secret",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.read().decode()
            except urllib.error.HTTPError as exc:
                body = exc.read()
                try:
                    exc.close()
                except Exception:
                    pass
                hint = mod.detect_insufficient_user_quota(
                    exc.code, body, base_url="https://newapi.1234bot.com/v1"
                )
                if hint is not None:
                    raise mod.InsufficientUserQuotaError(exc.code, body, hint) from exc
                raise

        return operation

    def test_happy_path_recharge_then_retry_once(self) -> None:
        mod = _require_module()
        sink = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ctrl = self._controller(tmp, sink)
            result = ctrl.run(self._quota_operation())
            self.assertIn("created", result)
            self.assertEqual(_RechargeHTTPState.gen_calls, 2)
            self.assertEqual(_RechargeHTTPState.ticket_calls, 1)
            self.assertEqual(_RechargeHTTPState.session_posts, 1)
            self.assertEqual(_RechargeHTTPState.qr_calls, 1)
            self.assertEqual(_RechargeHTTPState.ticket_auths, ["Bearer test-key-secret"])
            self.assertEqual(_RechargeHTTPState.session_auths, [None])
            self.assertEqual(_RechargeHTTPState.ticket_face_values, [1000])
            session_body = json.loads(_RechargeHTTPState.session_bodies[0])
            self.assertEqual(set(session_body.keys()), {"ticket"})
            emitted = sink.getvalue()
            self.assertNotIn("COMPACT_TICKET_SECRET_DO_NOT_LEAK", emitted)
            self.assertNotIn("test-key-secret", emitted)
            self.assertNotIn("Bearer ", emitted)
            self.assertNotIn("SECRET_PAY", emitted)
            self.assertNotIn("payUrl", emitted)
            self.assertIn("akasha.recharge", emitted)
            self.assertIn("pub_test_1", emitted)
            self.assertIn("qrPngPath", emitted)
            self.assertIn("publicPageUrl", emitted)
            # No ResourceWarning about HTTPError cleanup
            for w in caught:
                self.assertNotIn("HTTPError", str(w.message))

    def test_command_budget_blocks_second_quota_on_later_phase(self) -> None:
        """Submit ok, first poll recharges once, later poll quota stops without 2nd ticket."""
        mod = _require_module()
        _RechargeHTTPState.async_submit_ok_then_poll_quota = True
        _RechargeHTTPState.second_poll_quota_after_recharge = True
        sink = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = self._controller(tmp, sink)

            def submit() -> str:
                import urllib.request

                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/v1/videos/generations",
                    data=b"{}",
                    headers={"Authorization": "Bearer test-key-secret", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.read().decode()

            def poll() -> str:
                import urllib.error
                import urllib.request

                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/v1/videos/task-async-1",
                    headers={"Authorization": "Bearer test-key-secret"},
                    method="GET",
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        return resp.read().decode()
                except urllib.error.HTTPError as exc:
                    body = exc.read()
                    try:
                        exc.close()
                    except Exception:
                        pass
                    hint = mod.detect_insufficient_user_quota(
                        exc.code, body, base_url="https://newapi.1234bot.com/v1"
                    )
                    if hint is not None:
                        raise mod.InsufficientUserQuotaError(exc.code, body, hint) from exc
                    raise

            # submit never recharges
            submit_body = ctrl.run(submit)
            self.assertIn("task-async-1", submit_body)
            self.assertEqual(_RechargeHTTPState.gen_calls, 1)
            self.assertEqual(_RechargeHTTPState.ticket_calls, 0)

            # first poll triggers recharge + retry; retry still quota due to second_poll flag
            with self.assertRaises(mod.AkashaRechargeError) as caught:
                ctrl.run(poll)
            message = str(caught.exception)
            self.assertIn("publicPageUrl=", message)
            self.assertIn("statusUrl=", message)
            self.assertNotIn("COMPACT_TICKET", message)
            self.assertNotIn("test-key-secret", message)
            self.assertEqual(_RechargeHTTPState.ticket_calls, 1)
            self.assertEqual(_RechargeHTTPState.session_posts, 1)
            self.assertEqual(_RechargeHTTPState.gen_calls, 1)  # submit not repeated

            # another phase still must not create second ticket
            with self.assertRaises(mod.AkashaRechargeError):
                ctrl.run(poll)
            self.assertEqual(_RechargeHTTPState.ticket_calls, 1)

    def test_second_insufficient_stops_without_second_recharge(self) -> None:
        mod = _require_module()
        _RechargeHTTPState.mode = "always_quota"
        sink = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = self._controller(tmp, sink)
            with self.assertRaises(mod.AkashaRechargeError) as caught:
                ctrl.run(self._quota_operation())
            message = str(caught.exception)
            self.assertNotIn("COMPACT_TICKET_SECRET", message)
            self.assertNotIn("test-key-secret", message)
            self.assertEqual(_RechargeHTTPState.ticket_calls, 1)
            self.assertEqual(_RechargeHTTPState.gen_calls, 2)

    def test_failed_expired_timeout_safe_links(self) -> None:
        mod = _require_module()
        for mode, needle in (("failed", "FAILED"), ("expired", "EXPIRED"), ("timeout_credit", "timed out")):
            with self.subTest(mode=mode):
                _RechargeHTTPState.mode = mode
                _RechargeHTTPState.ticket_calls = 0
                _RechargeHTTPState.session_posts = 0
                _RechargeHTTPState.status_calls = 0
                _RechargeHTTPState.qr_calls = 0
                _RechargeHTTPState.ticket_auths = []
                _RechargeHTTPState.session_auths = []
                _RechargeHTTPState.session_bodies = []
                sink = io.StringIO()
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaises(mod.AkashaRechargeError) as caught:
                        mod.perform_recharge(
                            api_key="test-key-secret",
                            base_url="https://newapi.1234bot.com/v1",
                            face_value_usd_cent=1000,
                            ticket_endpoint="/v1/tooling/recharge-ticket",
                            poll_interval=0.01,
                            poll_timeout=0.05 if mode == "timeout_credit" else 1.0,
                            qr_parent_dir=tmp,
                            event_file=sink,
                            sleep=lambda _s: None,
                            ticket_base_url=self.base,
                            allow_http_endpoints=True,
                        )
                    text = str(caught.exception)
                    self.assertIn(needle if mode != "timeout_credit" else "timed out", text)
                    self.assertIn("publicPageUrl=", text)
                    self.assertIn("statusUrl=", text)
                    self.assertNotIn("COMPACT_TICKET", text)
                    self.assertNotIn("SECRET_PAY", text)
                    self.assertEqual(_RechargeHTTPState.ticket_calls, 1)
                    self.assertEqual(_RechargeHTTPState.session_posts, 1)

    def test_enterprise_rejection_safe_message(self) -> None:
        mod = _require_module()
        _RechargeHTTPState.enterprise = True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(mod.AkashaRechargeError) as caught:
                mod.perform_recharge(
                    api_key="test-key-secret",
                    base_url="https://newapi.1234bot.com/v1",
                    face_value_usd_cent=1000,
                    ticket_endpoint="/v1/tooling/recharge-ticket",
                    poll_interval=0.01,
                    poll_timeout=1.0,
                    qr_parent_dir=tmp,
                    event_file=io.StringIO(),
                    sleep=lambda _s: None,
                    ticket_base_url=self.base,
                    allow_http_endpoints=True,
                )
            text = str(caught.exception)
            self.assertTrue("企业" in text or "enterprise" in text.lower() or "admin" in text.lower())
            self.assertNotIn("SENSITIVE_TOKEN", text)
            self.assertNotIn("test-key-secret", text)

    def test_redirect_on_ticket_is_refused_without_following(self) -> None:
        mod = _require_module()
        _RechargeHTTPState.redirect_ticket = True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(mod.AkashaRechargeError) as caught:
                mod.perform_recharge(
                    api_key="test-key-secret",
                    base_url="https://newapi.1234bot.com/v1",
                    face_value_usd_cent=1000,
                    ticket_endpoint="/v1/tooling/recharge-ticket",
                    poll_interval=0.01,
                    poll_timeout=1.0,
                    qr_parent_dir=tmp,
                    event_file=io.StringIO(),
                    sleep=lambda _s: None,
                    ticket_base_url=self.base,
                    allow_http_endpoints=True,
                )
            self.assertIn("redirect", str(caught.exception).lower())
            self.assertEqual(_RechargeHTTPState.session_posts, 0)

    def test_production_rejects_http_session_endpoint(self) -> None:
        mod = _require_module()
        with self.assertRaises(mod.AkashaRechargeError):
            mod._require_https_url("http://evil.example/session", "lovbrowser_session_endpoint")

    def test_cli_amount_reaches_ticket(self) -> None:
        sink = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = self._controller(tmp, sink, cli="12.5")
            ctrl.run(self._quota_operation())
            self.assertEqual(_RechargeHTTPState.ticket_face_values, [1250])


class LazyEnvAmountTests(unittest.TestCase):
    def test_invalid_env_does_not_break_non_trigger_path(self) -> None:
        mod = _require_module()
        with mock.patch.dict(os.environ, {"AKASHA_RECHARGE_USD": "not-a-number"}, clear=True):
            # No recharge triggered: resolving with use_env=False (private/success path) is fine
            self.assertEqual(mod.resolve_face_value_usd_cent(None, use_env=False), 1000)
            # CLI validation does not read env
            mod.validate_cli_recharge_usd(None)
            # Trigger-time resolution fails only when recharge actually needs env
            with self.assertRaises(mod.AkashaRechargeError):
                mod.resolve_face_value_usd_cent(None, use_env=True)


class LoaderSingletonTests(unittest.TestCase):
    def test_load_akasha_recharge_module_is_identity_stable(self) -> None:
        mod = _require_module()
        caller = Path(__file__).resolve()
        a = mod.load_akasha_recharge_module(caller)
        b = mod.load_akasha_recharge_module(caller)
        self.assertIs(a, b)
        self.assertIs(a.InsufficientUserQuotaError, b.InsufficientUserQuotaError)
        self.assertTrue(str(Path(a.__file__).resolve()).endswith("shared/akasha_recharge.py"))


if __name__ == "__main__":
    unittest.main()
