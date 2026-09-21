# claude-glm-stack

Run **Claude Desktop, Claude Code (and friends) on Z.AI GLM** — with honest,
verified model tiers and one API key.

Give this repo to your coding agent (Claude Code, Codex, Cursor, ...) on a Mac,
give it your Z.AI API key, and get a working Claude Desktop whose model picker
says GLM and *means it*. The only manual step that may remain is 4 clicks in
the app (the agent will tell you if and when).

```text
Claude Desktop (3P gateway mode)
   │  model: claude-opus-5          model: claude-sonnet-4-5
   ▼                                        ▼
local rewriting gateway  127.0.0.1:8788  (launchd, auto-start)
   │  model: glm-5.3               model: glm-5.3-flash
   ▼                                        ▼
https://api.z.ai/api/anthropic  (Anthropic Messages API, GLM Coding Plan key)
```

## Why this exists (the two walls)

1. **Claude Desktop refuses non-Claude model names.** In third-party (3P)
   gateway mode its validator rejects any model ID containing `glm`, `gpt`,
   `qwen`, ... So you cannot just write `glm-5.3` into the config.
2. **Z.AI accepts `claude-*` names — and routes every single one to
   GLM-5.3-Flash.** Verified with a vision probe (`docs/findings.md` §2):
   `claude-opus-5` happily describes images, while real `glm-5.3` is text-only
   and cannot. Without a translator your whole "GLM-5.3" Desktop is silently
   running on the flash tier.

The local gateway solves both: the app keeps sending Claude-shaped names, the
gateway rewrites the `model` field to the real GLM model per tier:

| Desktop tier (label) | Sends | Actually runs | Like the CLI slot |
|---|---|---|---|
| opus — "GLM-5.3" | `claude-opus-5` | `glm-5.3` (text-only, heavy) | `ANTHROPIC_DEFAULT_OPUS_MODEL` |
| sonnet — "GLM-5.3 Flash" | `claude-sonnet-4-5` | `glm-5.3-flash` (vision, fast) | sonnet/haiku slots |
| haiku | `claude-haiku-*` | `glm-5.3-flash` | |

SSE streaming and server-side tools (z.ai's `web_search_prime`) pass through
untouched. The gateway never logs or stores your key beyond
`~/.config/claude-glm-stack/key` (mode 600).

## Quick start

**Route A — hand it to your coding agent** (the intended one):

> "Set up Claude Desktop on my GLM plan using this repo. My Z.AI key is …"

The agent follows `AGENTS.md`: runs `scripts/setup-macos.sh`, restarts the app,
verifies with `scripts/selftest.py` (proves the opus tier is blind = real
`glm-5.3`, the sonnet tier reads images = flash, SSE streams), and only asks
you for the 4-click Developer-Mode fallback if the zero-UI config route didn't
take.

**Route B — one command yourself:**

```bash
export ZAI_API_KEY="your-key"
./scripts/setup-macos.sh                 # installs gateway + managed config (sudo once)
# or, without sudo:
./scripts/setup-macos.sh --config-library
```

**Route C — manual (always works):** start the gateway (`python3 gateway.py`),
then in Claude Desktop: Help → Troubleshooting → Enable Developer Mode →
Developer → Configure Third-Party Inference… → provider `gateway`, endpoint
`http://127.0.0.1:8788`, API key `via-local-gateway` → Apply → Save & Restart.
Do **not** sign in to claude.ai. Copy the tier entries from
`configs/configlibrary-example.json`.

## What you get

* Full Claude Desktop (Chat, Cowork, Code) billed to your GLM Coding Plan
* Model picker with honest tiers; subagents (sonnet slot) on cheap flash
* The **Code tab reads your normal Claude Code setup** — `~/.claude/skills/`,
  plugins, hooks, `~/.claude/CLAUDE.md`, memory: no migration
* Chat tab web search works natively (z.ai implements the server-side
  `web_search`; shares the plan's 1000 searches/month pool)
* All data local (3P mode keeps chats on-device; no claude.ai account)

## Verified findings (the part nobody else tested)

Short version — long version in [`docs/findings.md`](docs/findings.md):

* name validator whitelist/blacklist decoded from `app.asar`
* vision-probe proof that all `claude-*` aliases land on flash
* `/v1/models` on z.ai lacks `anthropic_family_tier` → native discovery can't show `glm-*`
* config channel map (managed plist / configLibrary / app-store mirror / `~/.claude`)
* `CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1` pins deterministic model behaviour
* quota economics: flash ≈ 3x cheaper; web search pool 1000/month, shared

## Windows

This repo is macOS-first. For Windows the same architecture exists:
[`kakaballina/claude-desktop-glm-bridge`](https://github.com/kakaballina/claude-desktop-glm-bridge)
(Node proxy + Task Scheduler). Note neither of the existing Windows repos
verifies which model actually serves a tier — the vision-probe self-test here
is the part worth stealing.

## Uninstall

```bash
./scripts/setup-macos.sh --uninstall
```

## License

MIT — see [LICENSE](LICENSE).
