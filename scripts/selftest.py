#!/usr/bin/env python3
"""Self-test for claude-glm-stack: verifies the gateway maps model tiers correctly.

Checks (each costs a handful of tokens on your Z.AI plan):
  1. gateway is up and answers on the local port
  2. opus-tier name -> upstream glm-5.3   (text-only: must FAIL to describe an image)
  3. sonnet-tier name -> glm-5.3-flash    (vision: must read the code word off the image)
  4. SSE streaming works end-to-end

Exit code 0 = all good. Stdlib only (builds the test PNG by hand).

Usage: python3 scripts/selftest.py [gateway_port]
"""
import base64
import json
import socket
import struct
import sys
import time
import urllib.request
import zlib

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
CODE_WORD = "ZEBRA-47"


def make_png(code_word):
    """Minimal dependency-free PNG: white box, black frame, red code word (5x7 font dots)."""
    S = 5  # pixel size of one font dot
    W, H = 30 + len(code_word) * 6 * S, 90
    # 5x7 bitmap font for A-Z and 0-9 (columns per char)
    FONT = {
        'Z': ("111", "001", "010", "100", "111"), 'E': ("111", "100", "111", "100", "111"),
        'B': ("111", "101", "110", "101", "111"), 'R': ("111", "101", "110", "101", "101"),
        'A': ("010", "101", "111", "101", "101"), '-': ("000", "000", "111", "000", "000"),
        '4': ("101", "101", "111", "001", "001"), '7': ("111", "001", "010", "010", "010"),
    }
    px = [[(255, 255, 255)] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if x in (0, W - 1) or y in (0, H - 1):
                px[y][x] = (0, 0, 0)
    cx, cy = 15, 25
    for ch in code_word:
        cols = FONT.get(ch, ("000",) * 5)
        for row in range(7):
            bits = cols[row] if row < len(cols) else "000"
            for col in range(5):
                if col < len(bits) and bits[col] == "1":
                    for dy in range(S):
                        for dx in range(S):
                            X, Y = cx + col * S + dx, cy + row * S + dy
                            if 0 <= X < W and 0 <= Y < H:
                                px[Y][X] = (204, 0, 0)
        cx += 6 * S
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in px)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def post(body, timeout=120):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/messages", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer selftest",
                                          "anthropic-version": "2023-06-01"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=timeout)
    return r, json.loads(r.read()), time.time() - t0


def text_of(d):
    return "".join(c.get("text", "") for c in d.get("content", []) if c.get("type") == "text").strip()


def main():
    ok = True
    # 1. gateway up?
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=3).close()
        print(f"[1] gateway on :{PORT} ................ UP")
    except OSError:
        print(f"[1] gateway on :{PORT} ................ DOWN  <- run the launchd agent / gateway.py")
        return 1

    code_word = CODE_WORD
    b64 = base64.b64encode(make_png(code_word)).decode()
    img_msg = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
               {"type": "text", "text": "What exactly is written on the image? One short sentence."}]

    # 2. opus-tier must be BLIND (routed to text-only glm-5.3)
    try:
        _, d, _ = post({"model": "claude-opus-5", "max_tokens": 120,
                        "thinking": {"type": "disabled"}, "messages": [{"role": "user", "content": img_msg}]})
        t = text_of(d).lower()
        blind = code_word.lower() not in t  # text-only model cannot read the code word
        print(f"[2] opus-tier -> glm-5.3 (text-only) .. {'OK (blind, as expected): ' + text_of(d)[:70] if blind else 'FAIL: ' + text_of(d)[:90]}")
        ok &= blind
    except Exception as e:
        print(f"[2] opus-tier -> glm-5.3 (text-only) .. ERROR {e}")
        ok = False

    # 3. sonnet-tier must SEE the code word (routed to glm-5.3-flash)
    try:
        _, d, _ = post({"model": "claude-sonnet-4-5", "max_tokens": 120,
                        "thinking": {"type": "disabled"}, "messages": [{"role": "user", "content": img_msg}]})
        saw = code_word.lower() in text_of(d).lower()
        print(f"[3] sonnet-tier -> glm-5.3-flash ...... {'OK (reads ' + code_word + ')' if saw else 'FAIL: ' + text_of(d)[:90]}")
        ok &= saw
    except Exception as e:
        print(f"[3] sonnet-tier -> glm-5.3-flash ...... ERROR {e}")
        ok = False

    # 4. SSE streaming (raw request -- the response is an event stream, not JSON)
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/messages", method="POST",
                                     data=json.dumps({"model": "claude-sonnet-4-5", "max_tokens": 40, "stream": True,
                                                      "messages": [{"role": "user", "content": "Say three words about the sea."}]}).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer selftest",
                                              "anthropic-version": "2023-06-01"})
        t0 = time.time()
        r = urllib.request.urlopen(req, timeout=60)
        dt = time.time() - t0
        buf = b""
        while True:
            chunk = r.read(256)
            if not chunk:
                break
            buf += chunk
        streamed = b"content_block_delta" in buf and b"message_stop" in buf
        print(f"[4] SSE streaming ..................... {'OK' if streamed else 'FAIL'} ({dt:.1f}s)")
        ok &= streamed
    except Exception as e:
        print(f"[4] SSE streaming ..................... ERROR {e}")
        ok = False

    print("\nRESULT:", "ALL GREEN — Claude Desktop is on real GLM tiers" if ok else "PROBLEMS FOUND — see above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
