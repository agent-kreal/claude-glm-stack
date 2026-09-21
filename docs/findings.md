# Findings: how Claude Desktop 3P + Z.AI actually behave

Everything below was verified empirically on 2026-09-21 against
Claude Desktop **2.2553.1** (macOS, `com.anthropic.claudefordesktop`) and the
Z.AI Anthropic-compatible endpoint `https://api.z.ai/api/anthropic`
(GLM Coding Plan key). Most of it is not in any official doc.

## 1. The app rejects non-Claude model names

The bundled web app (`app.asar`) validates every model-route name with a
whitelist/blacklist pair (minified as `Jo`/`Yo` + `Ixe`/`Fxe`):

* **allowed:** the name contains one of `claude, sonnet, opus, haiku, fable, mythos, anthropic`
  (or is a bare tier alias like `sonnet-4.5`)
* **blocked:** the name contains any of `glm, gpt, qwen, deepseek, kimi, minimix, mistral,
  llama, gemini, grok, ...` (a competitor-model blocklist)

So `"glm-5.3"` can never be sent by Claude Desktop, even in gateway mode.
This kills the "just use the real model names" idea -- you need name translation.

## 2. Z.AI routes ALL claude-* aliases to GLM-5.3-Flash

Verified with a vision probe (an image with a code word, sent to the Messages API):

| requested model   | sees the image? | actual model          |
|-------------------|-----------------|-----------------------|
| `glm-5.3-flash`   | yes             | GLM-5.3-Flash (control) |
| `glm-5.3`         | **no** ("cannot process") | GLM-5.3, text-only (control) |
| `claude-opus-5`   | yes             | **GLM-5.3-Flash**     |
| `claude-sonnet-4-5` | yes           | GLM-5.3-Flash         |
| `claude-opus-4/4-1/4-6`, `claude-sonnet-4`, old dated IDs, bare `opus-5`/`sonnet` | yes | Flash |

Every claude-shaped name is accepted (HTTP 200, the name is echoed back) and
served by the flash-tier model. The endpoint never reveals the real model in the
response body or headers. Practical consequence: **without a rewriting proxy the
whole Desktop runs on flash while labelling it whatever you typed.**

Z.AI's own docs corroborate the intent: the current GLM Coding Plan default maps
*all three* Claude Code slots (`ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`) to
`GLM-5.3-Flash`.

## 3. `/v1/models` exists but cannot rescue native discovery

`GET /v1/models` returns 11 models (`glm-4.5` ... `glm-5.3-flashx`) with plain
`{id, created_at, display_name, type}` records. Desktop's auto-discovery only
admits non-Claude IDs when the gateway marks them with `anthropic_family_tier`
metadata -- z.ai does not -- so native discovery shows nothing useful.
Explicit `inferenceModels` entries are subject to the blocklist from §1.
Conclusion: a local translating proxy (this repo) or a self-hosted gateway that
adds the metadata are the only deterministic routes.

## 4. Config channels: who reads what

| Channel | Path | Notes |
|---|---|---|
| Managed config (IT/MDM) | `/Library/Managed Preferences/com.anthropic.claudefordesktop.plist` (device) or `/Library/Managed Preferences/<user>/...` | read at launch, no UI needed; needs sudo; also `CLAUDE_E2E_MANAGED_PLIST` env var can point anywhere (terminal launches only) |
| 3P config library (Developer UI artifact) | `~/Library/Application Support/Claude-3p/configLibrary/*.json` + `_meta.json` | what "Developer → Configure Third-Party Inference" writes; editable while the app is quit |
| App preferences | `~/Library/Application Support/Claude-3p/claude_desktop_config.json` | a *mirror* of the web-app store; hand edits get overwritten on launch -- don't fight it |
| Claude Code user config | `~/.claude/settings.json` | the **Code tab** reads it (env, skills, plugins, memory); the Chat tab does not |

3P mode uses a separate profile dir (`Claude-3p`): chats, memory and logs stay
local and never touch claude.ai.

## 5. Tier mapping

`inferenceModels[]` supports `anthropicFamilyTier` (`haiku|sonnet|opus|fable|mythos`)
and `isFamilyDefault` -- bare tier aliases (e.g. the `sonnet` slot used for
subagents in Code sessions) resolve to the entry marked default for that tier.
`labelOverride` is what the model picker shows.

## 6. Silent model fallback (and how to disable it)

`preferences.coworkModelAutoFallbackByAccount` (web-app store, not file-editable)
makes Code sessions fall back to another model on refusal/error. The app
implements it by exporting `CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1` when the
toggle is off -- so you can pin determinism yourself via
`~/.claude/settings.json`:

```json
{ "env": { "CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK": "1" } }
```

## 7. Web search: server-side, and z.ai implements it

Chat's built-in WebSearch is a *server-side tool executed by the inference
provider*. The docs assume most gateways don't implement Anthropic's
`web_search` -- but z.ai does (tool `web_search_prime`, visible in the tool
result metadata). It works through the rewriting proxy untouched, and shares
one pool: **1000 searches/month on the GLM Coding Plan key**, the same pool
your CLI tooling uses. Monthly reset; on exhaustion you get a 429 with a
`reset at ...` date.

WebFetch, by contrast, is client-side -- but the Cowork sandbox only lets it
egress to the inference endpoint unless you extend `coworkEgressAllowedHosts`.

## 8. Skills / memory: two worlds in one app

* **Code tab** = bundled Claude Code: reads `~/.claude/skills/`, plugins, hooks,
  `~/.claude/CLAUDE.md`, memory, `settings.json`. No migration needed.
* **Chat/Cowork tab**: only bundled skills (`documents-*`, `schedule`, ...),
  plugins installed via the UI (`~/Library/Application Support/Claude-3p/cowork_plugins/`,
  one folder per skill with a top-level `SKILL.md`), and org-level provisioning
  (`/Library/Application Support/Claude/org-plugins/`). Its memory lives in
  `Claude-3p/local-agent-mode-sessions/<account>/<org>/memory/` and never
  syncs with the CLI's.

## 9. Quota economics

GLM Coding Plan: flash-tier usage counts ~3x cheaper than the main glm-5.3.
Without the proxy everything silently runs on flash (cheap but weak for heavy
reasoning); with the tier mapping you pay the heavy rate only for the opus tier,
exactly like CLI slots. Server-side web search draws from the shared 1000/month
pool (§7).
