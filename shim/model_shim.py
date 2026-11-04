#!/usr/bin/env python3
"""OpenAI-compatible model shim for the Flip the Switch agent.

OpenCode (the Switch agent provider) points at this shim as a custom
OpenAI provider on http://127.0.0.1:8399/v1. The shim forwards chat
completion requests to OpenRouter, attaching the stored
`custom.openrouter` credential ONLY through the sanctioned surrogate
helper (dynamic_credentials.add_surrogate_to_request) — the raw key is
never read, logged, or persisted here.

$0 rule: the shim always substitutes its own model and only ever calls
`:free`-suffixed OpenRouter models, whatever the client asks for.

Stdlib only; run with the system python3.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
import dynamic_credentials as dc  # noqa: E402

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
ALLOWED_HOSTS = ("openrouter.ai",)
CREDENTIAL = "custom.openrouter"

# Free-tier roster rotates, so it is discovered from the live catalog at
# startup: only models priced 0 that support tool calls qualify. The
# preference order below ranks the discovered set; anything discovered
# but unranked is appended. Static fallback if the catalog is unreachable.
PREFERRED = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "openrouter/free",
    "thinkingmachines/inkling:free",
    "google/gemma-4-26b-a4b-it:free",
]
STATIC_FALLBACK = list(PREFERRED)


def discover_free_models() -> list[str]:
    try:
        req = urllib.request.Request(MODELS_URL)
        dc.add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)
        req.timeout = 60
        with urllib.request.urlopen(req) as resp:
            data = dc.read_json_response(resp)
        live = []
        for m in data.get("data", []):
            p = m.get("pricing", {})
            if str(p.get("prompt")) == "0" and str(p.get("completion")) == "0":
                if "tools" in (m.get("supported_parameters") or []):
                    live.append(m["id"])
        if not live:
            return list(STATIC_FALLBACK)
        ranked = [m for m in PREFERRED if m in live]
        rest = [m for m in live if m not in ranked]
        return ranked + rest
    except Exception as e:  # noqa: BLE001 - fall back to the static roster
        print(f"model discovery failed ({e}); using static roster", flush=True)
        return list(STATIC_FALLBACK)


FREE_MODELS = discover_free_models()
SHIM_MODEL_ID = "switch-free-agent"
PORT = int(os.environ.get("SHIM_PORT", "8399"))


def call_openrouter(payload: dict) -> dict:
    """Try each free model in turn; return the first successful response."""
    last_err = None
    for model in FREE_MODELS:
        body = dict(payload)
        body["model"] = model
        body["stream"] = False
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            OPENROUTER_URL, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        dc.add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)
        req.timeout = 240
        try:
            with urllib.request.urlopen(req) as resp:
                out = dc.read_json_response(resp)
                out["_shim_model"] = model
                return out
        except urllib.error.HTTPError as e:
            last_err = f"{model}: HTTP {e.code}"
            if e.code in (429, 404, 400):
                continue
            raise RuntimeError(last_err) from e
        except Exception as e:  # noqa: BLE001 - report and try next model
            last_err = f"{model}: {type(e).__name__}: {e}"
            continue
    raise RuntimeError(f"all free models failed; last: {last_err}")


def sse_from_completion(comp: dict) -> bytes:
    """Render a complete (non-streamed) completion as one SSE chunk."""
    chunk = {
        "id": comp.get("id", "chatcmpl-shim"),
        "object": "chat.completion.chunk",
        "created": comp.get("created", 0),
        "model": comp.get("model", SHIM_MODEL_ID),
        "choices": [],
    }
    for ch in comp.get("choices", []):
        msg = ch.get("message", {})
        delta = {}
        if msg.get("content"):
            delta["content"] = msg["content"]
        if msg.get("tool_calls"):
            delta["tool_calls"] = msg["tool_calls"]
        chunk["choices"].append({
            "index": ch.get("index", 0),
            "delta": delta,
            "finish_reason": ch.get("finish_reason") or "stop",
        })
    return (f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n").encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep stdout clean
        sys.stderr.write("shim: %s\n" % (fmt % args))

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            body = json.dumps({
                "object": "list",
                "data": [{"id": SHIM_MODEL_ID, "object": "model",
                          "created": 0, "owned_by": "switch-shim"}],
            }).encode()
            self._send(200, body, "application/json")
        else:
            self._send(404, b'{"error":"not found"}', "application/json")

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, b'{"error":"bad json"}', "application/json")
            return
        want_stream = bool(payload.get("stream"))
        # Pass through the OpenAI-shaped fields OpenRouter understands.
        fwd = {k: payload[k] for k in (
            "messages", "tools", "tool_choice", "temperature",
            "max_tokens", "top_p", "stop", "response_format",
        ) if k in payload}
        try:
            comp = call_openrouter(fwd)
        except Exception as e:  # noqa: BLE001
            body = json.dumps({"error": {"message": str(e),
                                         "type": "shim_error"}}).encode()
            self._send(502, body, "application/json")
            return
        if want_stream:
            self._send(200, sse_from_completion(comp),
                       "text/event-stream")
        else:
            comp["model"] = comp.pop("_shim_model", FREE_MODELS[0])
            self._send(200, json.dumps(comp).encode(), "application/json")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"model shim listening on 127.0.0.1:{PORT} "
          f"(models: {', '.join(FREE_MODELS)})", flush=True)
    server.serve_forever()
