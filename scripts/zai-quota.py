#!/usr/bin/env python3
"""zai-quota: GLM Coding Plan usage from Z.AI's monitor API -- one line or JSON.

The same undocumented endpoints the z.ai dashboard uses; auth is the plain
API key (no Bearer). Key resolution mirrors gateway.py:
$ZAI_API_KEY -> ~/.claude/settings.json env.ANTHROPIC_AUTH_TOKEN
             -> ~/.config/claude-glm-stack/key
Caches for 5 minutes in ~/.cache/zai-quota.json, falls back to the stale
cache when the API is down, never logs or stores the key.

Usage:
    zai-quota.py --line            # band/statusline one-liner
    zai-quota.py --line --fresh    # bypass the cache
    zai-quota.py --json            # full payload for the mod
"""
import json
import os
import pathlib
import sys
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import quote

API = "https://api.z.ai/api/monitor"
CACHE_FILE = pathlib.Path.home() / ".cache" / "zai-quota.json"
CACHE_TTL = 300  # seconds; the community norm (VS Code ext default)

# Peak window (docs.z.ai/devpack): Mon-Fri 14:00-18:00 UTC+8 == 09:00-13:00 MSK.
# Multipliers per plan generation: quota-based burns x1 off-peak / x3 peak,
# credits-based burns x0.5 off-peak / x1 peak. Defaults below are quota-based;
# a credits-based pro just flips the two strings.
PEAK_START, PEAK_END = 9, 13  # local hours, MSK == mac timezone assumed
MULT_OFFPEAK, MULT_PEAK = "x1", "x3"


def load_key():
    env_key = os.environ.get("ZAI_API_KEY")
    if env_key:
        return env_key.strip()
    try:
        env = json.loads((pathlib.Path.home() / ".claude" / "settings.json").read_text()).get("env", {})
        if env.get("ANTHROPIC_AUTH_TOKEN"):
            return env["ANTHROPIC_AUTH_TOKEN"]
    except (OSError, ValueError):
        pass
    try:
        return (pathlib.Path.home() / ".config" / "claude-glm-stack" / "key").read_text().strip()
    except OSError:
        return None


def http_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def monitor_headers(key):
    # api.z.ai monitor endpoints want the raw key, no Bearer (verified 2026-10-18)
    return {"Authorization": key, "Content-Type": "application/json"}


def fetch_quota_limits(headers):
    """GET /usage/quota/limit -> 5h window (pct + reset) and monthly MCP quota."""
    out = {"level": None, "five_hour": {}, "mcp": {}}
    try:
        data = http_get(f"{API}/usage/quota/limit", headers).get("data", {})
    except Exception:
        return out
    out["level"] = data.get("level")
    for limit in data.get("limits", []):
        if limit.get("type") == "TOKENS_LIMIT":
            out["five_hour"] = {
                "percentage": limit.get("percentage", 0),
                "next_reset_ms": limit.get("nextResetTime"),
            }
        elif limit.get("type") == "TIME_LIMIT":
            out["mcp"] = {
                "limit": limit.get("usage", 0),
                "used": limit.get("currentValue", 0),
                "remaining": limit.get("remaining", 0),
                "tools": {t.get("modelCode"): t.get("usage") for t in limit.get("usageDetails", [])},
                "next_reset_ms": limit.get("nextResetTime"),
            }
    return out


def fetch_window_usage(headers, days):
    """GET /usage/model-usage over the last `days` local days -> calls + tokens.

    Verified 2026-10-18: the server aggregates by whole dates and ignores
    the time-of-day part (same-date windows with different hours return
    identical numbers); multi-day ranges and end dates are honored
    (0 tokens for a pre-subscription day). So a "day" here is the server's
    calendar day of the date string, not an hour-precise window.
    """
    now = datetime.now()
    start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    url = (f"{API}/usage/model-usage"
           f"?startTime={quote(start.strftime('%Y-%m-%d %H:%M:%S'))}"
           f"&endTime={quote(end.strftime('%Y-%m-%d %H:%M:%S'))}")
    try:
        total = http_get(url, headers).get("data", {}).get("totalUsage", {})
    except Exception:
        return {"calls": None, "tokens": None}
    return {"calls": total.get("totalModelCallCount", 0), "tokens": total.get("totalTokensUsage", 0)}


def peak_state(now=None):
    now = now or datetime.now()
    is_peak = now.weekday() < 5 and PEAK_START <= now.hour < PEAK_END
    if is_peak:
        boundary = now.replace(hour=PEAK_END, minute=0, second=0, microsecond=0)
    else:
        boundary = now.replace(hour=PEAK_START, minute=0, second=0, microsecond=0)
        if now.hour >= PEAK_START:
            boundary += timedelta(days=1)
        while boundary.weekday() >= 5:
            boundary += timedelta(days=1)
    return {"peak": is_peak, "mult": MULT_PEAK if is_peak else MULT_OFFPEAK,
            "changes_in_sec": int((boundary - now).total_seconds())}


def fmt_tokens(n):
    if n is None:
        return "?"
    if n >= 1_000_000_000:
        v = n / 1_000_000_000
        return f"{v:.1f}b" if v < 100 else f"{v:.0f}b"
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}m" if v < 100 else f"{v:.0f}m"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_dur(sec):
    if sec is None or sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    return f"{h}h{rem // 60:02d}m"


def collect(fresh=False):
    """Gather everything, through the cache. Returns payload + meta."""
    now = datetime.now()
    if not fresh and CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text())
            if (now - datetime.fromisoformat(cached["ts"])).total_seconds() < CACHE_TTL:
                cached["stale"] = False
                return cached
        except (OSError, ValueError, KeyError):
            pass

    key = load_key()
    if not key:
        return {"error": "no Z.AI key found (ZAI_API_KEY / settings.json / claude-glm-stack keyfile)"}

    headers = monitor_headers(key)
    payload = {
        "ts": now.isoformat(timespec="seconds"),
        "level": None,
        "five_hour": {},
        "mcp": {},
        "day": fetch_window_usage(headers, 0),   # today
        "week": fetch_window_usage(headers, 6),  # trailing 7 local days
        "month": fetch_window_usage(headers, 29),
        "peak": peak_state(now),
    }
    quota = fetch_quota_limits(headers)
    payload.update(quota)

    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(payload))
    except OSError:
        pass
    payload["stale"] = False
    return payload


def stale_fallback():
    if CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text())
            cached["stale"] = True
            return cached
        except (OSError, ValueError):
            pass
    return {"error": "fetch failed and no cache"}


def render_line(p):
    if p.get("error"):
        return f"GLM ERR: {p['error']}"
    parts = []
    peak = p.get("peak", {})
    parts.append(peak.get("mult", "?"))
    fh = p.get("five_hour", {})
    if fh.get("next_reset_ms"):
        reset = datetime.fromtimestamp(fh["next_reset_ms"] / 1000)
        left = int((reset - datetime.now()).total_seconds())
        if left > 0:
            start = reset - timedelta(hours=5)
            parts.append(f"5h:{fh.get('percentage', 0)}%"
                         f" [{start.strftime('%H:%M')}-{reset.strftime('%H:%M')}]"
                         f"[↻{fmt_dur(left)}]")
        else:
            parts.append(f"5h:{fh.get('percentage', 0)}% [—]")
    else:
        parts.append("5h:0% [—]")
    for tag, win in (("D", "day"), ("W", "week"), ("M", "month")):
        w = p.get(win, {})
        parts.append(f"{tag}:{fmt_tokens(w.get('tokens'))}")
    mcp = p.get("mcp", {})
    if mcp.get("used"):
        parts.append(f"MCP {mcp['used']}/{mcp.get('limit', '?')}")
    if p.get("stale"):
        parts.append("(stale)")
    return " · ".join(parts)


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    fresh = "--fresh" in args
    try:
        payload = collect(fresh=fresh)
    except Exception:
        payload = stale_fallback()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_line(payload))


if __name__ == "__main__":
    main()
