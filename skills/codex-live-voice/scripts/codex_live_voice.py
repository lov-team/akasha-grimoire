#!/usr/bin/env python3
"""Codex gpt-live duplex voice through new-api.

Transport: WebRTC (POST /v1/realtime/calls, SDP offer/answer) + WebSocket
(wss <gateway>/v1/live/{call_id}) for events. Requires aiortc + websockets,
resolved at runtime via `uv run --with aiortc --with websockets`.

Modes:
  speak  -- append speakable context, record the assistant's spoken reply
  probe  -- create a call, join the WS, stream silence, report event flow
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://llmapi-direct.lovbrowser.com/v1"
LIVE_MODEL = "gpt-live-1-boulder-alpha"
PCMU_PAYLOAD_TYPE = 0
SAMPLE_RATE = 8000
FRAME_MS = 20
SILENCE_BYTE = 0xFF


def _resolve_key() -> str:
    for name in ("OPENAI_API_KEY", "LOVBROWSER_API_KEY", "NEW_API_API_KEY"):
        key = os.environ.get(name, "").strip()
        if key:
            return key
    creds = Path.home() / ".config" / "akasha" / "credentials.env"
    if creds.is_file():
        for line in creds.read_text().splitlines():
            if line.startswith("LOVBROWSER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(
        "no API key: set LOVBROWSER_API_KEY (or OPENAI_API_KEY). "
        "Run shared/akasha_credentials.py status for setup guidance."
    )


def _http_json(method: str, url: str, key: str, body=None, headers=None, timeout=30):
    data = None
    hdrs = {"Authorization": f"Bearer {key}"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return resp.status, dict(resp.headers), raw


def _post_call(base: str, key: str, sdp: str, session: dict) -> tuple[int, dict, bytes]:
    boundary = "----akasha-codex-live"
    parts = []
    for name, value, ctype in (
        ("sdp", sdp, "application/sdp"),
        ("session", json.dumps(session), "application/json"),
    ):
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n{value}\r\n".encode()
        )
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"{base}/realtime/calls",
        data=b"".join(parts),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/sdp",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


async def _duplex(base: str, key: str, text: str, out_path: str, voice: str,
                  instructions: str | None, timeout_s: float, verbose: bool):
    from aiortc import RTCPeerConnection, RTCSessionDescription
    import websockets

    from aiortc.mediastreams import AudioStreamTrack

    pc = RTCPeerConnection()
    done = asyncio.Event()
    pcm = bytearray()
    state = {"call_id": None, "turn_done": False, "transcript": ""}

    # Any outbound audio keeps the duplex pipeline alive; upstream echoes
    # session.input_audio.append once media is flowing. AudioStreamTrack's
    # default 440Hz tone is fine—the session's speech content comes from the
    # speakable context append, not from RTP payload.
    pc.addTrack(AudioStreamTrack())

    @pc.on("track")
    def on_track(track):
        if verbose:
            print(f"[media] inbound track: {track.kind}", file=sys.stderr)

    dc = pc.createDataChannel("oai-events")
    dc.on("message", lambda msg: _handle_event(msg, pcm, state, verbose, "dc"))

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    # wait for ICE gathering
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.05)

    session = {
        "model": LIVE_MODEL,
        "instructions": instructions or (
            "Speak the user's text exactly as written. "
            "Do not add, remove, explain, or answer anything."
        ),
        "audio": {"output": {"voice": voice}},
    }
    status, headers, answer = _post_call(base, key, pc.localDescription.sdp, session)
    if not (200 <= status < 300):
        raise SystemExit(f"call create HTTP {status}: {answer[:500]!r}")
    location = headers.get("Location", "")
    call_id = location.rsplit("/", 1)[-1]
    state["call_id"] = call_id
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer.decode(), type="answer"))
    if verbose:
        print(f"[call] {call_id}; ice={pc.iceConnectionState}", file=sys.stderr)

    ws_url = f"{base.replace('http', 'ws', 1)}/live/{urllib.parse.quote(call_id)}"
    async with websockets.connect(
        ws_url,
        additional_headers={"Authorization": f"Bearer {key}"},
        max_size=8 * 1024 * 1024,
    ) as ws:
        if verbose:
            print(f"[ws] joined {ws_url}", file=sys.stderr)

        async def reader():
            async for msg in ws:
                _handle_event(msg, pcm, state, verbose, "ws")
                if state["turn_done"]:
                    done.set()

        reader_task = asyncio.create_task(reader())
        # wait for session.started before appending speakable text
        t0 = time.monotonic()
        while not state.get("session_started") and time.monotonic() - t0 < 30:
            await asyncio.sleep(0.05)
        append = json.dumps({
            "type": "session.context.append",
            "channel": "speakable",
            "content": [{"type": "input_text", "text": text}],
        })
        await ws.send(append)
        if verbose:
            print("[ws] sent speakable append", file=sys.stderr)

        try:
            await asyncio.wait_for(done.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            if verbose:
                print("[ws] timed out waiting for turn.done", file=sys.stderr)
        reader_task.cancel()

    await pc.close()
    return pcm, state


def _handle_event(msg, pcm: bytearray, state: dict, verbose: bool, src: str):
    if isinstance(msg, (bytes, bytearray)):
        try:
            msg = msg.decode()
        except Exception:
            return
    try:
        event = json.loads(msg)
    except Exception:
        return
    etype = event.get("type", "")
    if etype == "session.started":
        state["session_started"] = True
    elif etype == "session.output_audio.delta":
        chunk = event.get("delta") or event.get("audio") or event.get("data") or ""
        try:
            pcm.extend(base64.b64decode(chunk))
        except Exception:
            pass
    elif etype in ("output_transcript.added", "turn.delta", "output_transcript"):
        item = event.get("item") or {}
        state["transcript"] += item.get("text") or event.get("delta") or ""
    elif etype == "turn.done":
        state["turn_done"] = True
    elif etype == "session.usage.updated":
        state["usage"] = event.get("usage")
    elif etype == "error":
        state["error"] = event.get("error", {}).get("message", "unknown")
    if verbose and etype != "session.output_audio.delta":
        preview = {k: v for k, v in event.items() if k != "delta" and k != "audio"}
        print(f"[{src}] {preview}", file=sys.stderr)


def _write_wav(pcm: bytes, path: str, rate=24000):
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def cmd_speak(args):
    base = args.base_url.rstrip("/")
    key = _resolve_key()
    text = args.text or open(args.text_file).read()
    pcm, state = asyncio.run(
        _duplex(base, key, text, args.output, args.voice,
                args.instructions, args.timeout, args.verbose)
    )
    if not pcm:
        raise SystemExit(f"no audio received; state={state}")
    _write_wav(bytes(pcm), args.output)
    print(json.dumps({
        "output": args.output,
        "pcm_bytes": len(pcm),
        "seconds": round(len(pcm) / 48000, 2),
        "call_id": state.get("call_id"),
        "transcript": state.get("transcript", ""),
        "usage": state.get("usage"),
        "error": state.get("error"),
    }, ensure_ascii=False, indent=2))


def cmd_probe(args):
    base = args.base_url.rstrip("/")
    key = _resolve_key()
    pcm, state = asyncio.run(
        _duplex(base, key, args.text, "/dev/null", args.voice,
                args.instructions, args.timeout, True)
    )
    print(json.dumps({
        "call_id": state.get("call_id"),
        "session_started": bool(state.get("session_started")),
        "turn_done": state.get("turn_done"),
        "pcm_bytes": len(pcm),
        "transcript": state.get("transcript", ""),
        "usage": state.get("usage"),
        "error": state.get("error"),
    }, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Codex gpt-live duplex voice via new-api")
    ap.add_argument("--base-url", default=os.environ.get("NEW_API_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--voice", default="cove")
    ap.add_argument("--instructions")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("speak")
    s.add_argument("--text")
    s.add_argument("--text-file")
    s.add_argument("--output", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--text", default="Akasha duplex voice probe. The relay is working.")
    args = ap.parse_args()
    {"speak": cmd_speak, "probe": cmd_probe}[args.cmd](args)


if __name__ == "__main__":
    main()
