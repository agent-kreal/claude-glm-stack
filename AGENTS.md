# AGENTS.md — playbook for coding agents

You are setting up **Claude Desktop on Z.AI GLM** on this user's Mac. The human
should only ever supply their Z.AI API key. Do everything else yourself, verify,
and report. If a step cannot be automated, give the human the exact 3 clicks.

## Safety rules (non-negotiable)

* NEVER print, echo, log or commit the Z.AI API key. Store it only in
  `~/.config/claude-glm-stack/key` (mode 600).
* NEVER delete or reset `~/Library/Application Support/Claude*` profiles — the
  user's local chats live there.
* Ask before anything destructive. Read-only inspection needs no permission.
* The self-test spends < 100 tokens of the user's plan — fine to run any time.

## Prerequisites

1. macOS (this playbook; for Windows point the user at the README "Windows" section).
2. `python3` available (`/usr/bin/python3` is fine — the scripts are stdlib-only).
3. Claude Desktop installed. Check `/Applications/Claude.app`; if missing and
   `brew` exists: `brew install --cask claude`. Version must be ≥ 2.x for 3P mode.

## Setup

Run the installer — it validates the key, installs the gateway as a launchd
agent, writes the Desktop config, restarts the app and self-tests:

```bash
export ZAI_API_KEY="<ask the human, once>"
./scripts/setup-macos.sh
```

If the human cannot grant sudo, use the no-sudo route (seeds the Developer-Mode
config file instead of the managed plist):

```bash
./scripts/setup-macos.sh --config-library
```

## Verify

1. `python3 scripts/selftest.py` must end with `ALL GREEN`
   (it proves: opus tier is text-only `glm-5.3`, sonnet tier is vision `glm-5.3-flash`, SSE streams).
2. Ask the human to open Claude Desktop and confirm the model picker shows
   **GLM-5.3** and **GLM-5.3 Flash**, and that the chat answers.
3. Quick smoke the human can do: attach an image in a chat on "GLM-5.3" — the
   model must say it cannot see images. If it describes the image, the gateway
   is bypassed (see Troubleshooting).

## If the provider is not detected at launch

The sign-in screen must offer "use your inference provider configuration".
If it doesn't:

1. `launchctl print gui/$(id -u)/com.claude-glm-stack.gateway | head` — the
   gateway must be `running`. Logs: `~/Library/Logs/claude-glm-stack.log`.
2. Managed plist present? `sudo defaults read /Library/Managed\ Preferences/com.anthropic.claudefordesktop.plist`
   (or the configLibrary route was used — check
   `~/Library/Application Support/Claude-3p/configLibrary/_meta.json`).
3. Fallback (always works, 4 clicks for the human):
   Help → Troubleshooting → **Enable Developer Mode**, then
   Developer → **Configure Third-Party Inference…**: provider `gateway`,
   endpoint `http://127.0.0.1:8788`, API key `via-local-gateway`, then
   Apply Changes → Save & Restart. Do not sign in to claude.ai.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Desktop chat silent, no requests in gateway log | gateway down | `launchctl kickstart -k gui/$(id -u)/com.claude-glm-stack.gateway` |
| 401/403 in gateway log | bad key | update `~/.config/claude-glm-stack/key`, kickstart the agent |
| "GLM-5.3" describes images | Desktop bypasses the gateway (base URL points straight at z.ai) | set `inferenceGatewayBaseUrl` to `http://127.0.0.1:8788` |
| Model picker empty | `inferenceModels` lost | re-run setup; check config file was not overwritten |
| App updated, config schema changed | upstream rename | compare with `docs/findings.md` §4; keys were decoded from app.asar and are version-sensitive |

## Optional hardening (offer, don't force)

* Deterministic model behaviour in Code sessions (no silent fallback):
  add `"CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK": "1"` to `~/.claude/settings.json` `env`.
* WebFetch in Code sessions preflights each domain against `api.anthropic.com`;
  `"skipWebFetchPreflight": true` in the Desktop managed config removes that.

## Uninstall

```bash
./scripts/setup-macos.sh --uninstall
```
