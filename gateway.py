#!/usr/bin/env python3
"""claude-glm-stack gateway: local model-rewrite proxy for Claude Desktop (3P gateway mode).

Claude Desktop's third-party "gateway" provider only accepts Claude-shaped model
names (the app's validator rejects model IDs containing `glm`, `gpt`, `qwen`, ...).
Z.AI's Anthropic-compatible endpoint accepts `claude-*` names -- but routes ALL of
them to GLM-5.3-Flash (verified 2026-09-21 via a vision probe: `claude-opus-5`
describes images, real `glm-5.3` is text-only and cannot).

This proxy gives you deterministic tiers, like Claude Code CLI slots:

    claude-opus-*    -> glm-5.3         (heavy reasoning, text-only)
    claude-sonnet-*  -> glm-5.3-flash   (fast, vision)
    claude-haiku-*   -> glm-5.3-flash
    anything else    -> forwarded verbatim

Stdlib only. SSE streaming is passed through unbuffered (chunked encoding).

API key resolution order:
    1. $ZAI_API_KEY
    2. ~/.claude/settings.json -> env.ANTHROPIC_AUTH_TOKEN   (Claude Code users)
    3. ~/.config/claude-glm-stack/key

Usage:  python3 gateway.py [port]        # default 8788, binds 127.0.0.1
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("CLAUDE_GLM_GATEWAY_PORT", "8788"))

# (substring of requested model name, upstream model). First match wins.
MODEL_RULES = [
    ("opus", "glm-5.3"),
    ("fable", "glm-5.3"),
    ("mythos", "glm-5.3"),
    ("sonnet", "glm-5.3-flash"),
    ("haiku", "glm-5.3-flash"),
]

DEFAULT_UPSTREAM = "https://api.z.ai/api/anthropic"
HOP_HEADERS = ("content-type", "anthropic-version", "anthropic-beta", "accept")


def load_api_key():
    env_key = os.environ.get("ZAI_API_KEY")
    if env_key:
        return env_key.strip()
    settings = pathlib.Path.home() / ".claude" / "settings.json"
    try:
        env = json.loads(settings.read_text()).get("env", {})
        if env.get("ANTHROPIC_AUTH_TOKEN"):
            return env["ANTHROPIC_AUTH_TOKEN"]
    except (OSError, ValueError):
        pass
    keyfile = pathlib.Path.home() / ".config" / "claude-glm-stack" / "key"
    try:
        return keyfile.read_text().strip()
    except OSError:
        return None


def rewrite_model(name):
    low = name.lower()
    for needle, target in MODEL_RULES:
        if needle in low:
            return target
    return name


def upstream_url(base, path):
    """Normalize the path for any base+suffix joining convention the app might use."""
    if path.startswith("/api/"):
        return "https://api.z.ai" + path
    if not path.startswith("/v1"):
        path = "/v1" + path
    return base + path


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self, method):
        token = load_api_key()
        if not token:
            self._json_error(502, "no API key found: set $ZAI_API_KEY, or put it in "
                                  "~/.claude/settings.json (env.ANTHROPIC_AUTH_TOKEN) "
                                  "or ~/.config/claude-glm-stack/key")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        if method == "POST" and raw:
            try:
                body = json.loads(raw)
                if isinstance(body.get("model"), str):
                    body["model"] = rewrite_model(body["model"])
                raw = json.dumps(body).encode()
            except (ValueError, TypeError):
                pass  # not JSON -- forward as-is

        req = urllib.request.Request(upstream_url(DEFAULT_UPSTREAM, self.path), data=raw or None, method=method)
        for h in HOP_HEADERS:
            if self.headers.get(h):
                req.add_header(h, self.headers[h])
        req.add_header("Authorization", "Bearer " + token)

        try:
            resp = urllib.request.urlopen(req, timeout=1800)
        except urllib.error.HTTPError as e:
            resp = e
        except Exception as e:
            self._json_error(502, f"upstream error: {e}")
            return

        ctype = resp.headers.get("Content-Type", "application/json")
        self.send_response(resp.code)
        self.send_header("Content-Type", ctype)
        if "text/event-stream" in ctype:
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                while True:
                    chunk = resp.read(1024)
                    if not chunk:
                        break
                    self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            data = resp.read()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def _json_error(self, code, msg):
        payload = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self._proxy("POST")

    def do_GET(self):
        self._proxy("GET")

    def log_message(self, format, *args):
        sys.stderr.write("[gateway] " + (format % args) + "\n")
        sys.stderr.flush()


if __name__ == "__main__":
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"[gateway] listening on http://{LISTEN_HOST}:{LISTEN_PORT}", file=sys.stderr)
    srv.serve_forever()
