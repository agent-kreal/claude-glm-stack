# Links & reference — where the truth lives

Curated pointers for humans and coding agents. If behaviour disagrees with
this repo, the official docs below win; if the docs disagree with the app, the
app wins (see `findings.md` — several things are undocumented).

## Anthropic — Claude Desktop on third-party platforms (3P)

Complete index for agents: **https://claude.com/docs/llms.txt**

| Page | What it answers |
|---|---|
| https://claude.com/docs/third-party/claude-desktop/overview | what 3P mode is, architecture, data handling per provider |
| https://claude.com/docs/third-party/claude-desktop/installation | install + **single-machine setup without MDM** (Developer Mode path) |
| https://claude.com/docs/third-party/claude-desktop/in-app-configuration | the in-app Configure Third-Party Inference flow, click by click |
| https://claude.com/docs/third-party/claude-desktop/configuration | **every managed-config key** (`inference*`, telemetry, egress, extensions) — check here when the schema changes |
| https://claude.com/docs/third-party/claude-desktop/gateway | gateway requirements: `POST /v1/messages` with streaming + tool use, optional `GET /v1/models`, `cache_control` passthrough |
| https://claude.com/docs/third-party/claude-desktop/models | `inferenceModels`, `anthropicFamilyTier`, discovery rules, model catalog |
| https://claude.com/docs/third-party/claude-desktop/extensions | MCP (`managedMcpServers`), plugin marketplaces, `org-plugins` provisioning |
| https://claude.com/docs/third-party/claude-desktop/web-tools | WebSearch (server-side, provider-executed) vs WebFetch (client-side, egress-gated) |
| https://claude.com/docs/third-party/claude-desktop/telemetry | what the app sends to Anthropic, how to switch it off, firewall allowlist |
| https://claude.com/docs/third-party/claude-desktop/data-storage | where chats/memory live on device; 3P uses a separate profile dir |
| https://claude.com/docs/third-party/claude-desktop/feature-matrix | what works on 3P vs first-party |
| https://claude.com/docs/cowork/guide/plugins | user-level plugin/skill install (Chat tab) |

## Z.AI — GLM Coding Plan & API

| Page | What it answers |
|---|---|
| https://docs.z.ai/devpack/tool/claude | official Claude Code + GLM setup (env vars, default slot mapping) |
| https://docs.z.ai/devpack/latest-model | how to switch plan models (`ANTHROPIC_DEFAULT_*_MODEL`) |
| https://docs.z.ai/devpack/tool/others | endpoint table: Anthropic Messages `https://api.z.ai/api/anthropic` vs OpenAI-compat |
| https://docs.z.ai/devpack/overview | what the Coding Plan includes (incl. the web-search quota) |
| https://z.ai/manage-apikey/apikey-list | API key console (create/rotate the key you give the setup) |

## Local cheat-sheet (macOS)

| Path | What it is |
|---|---|
| `/Applications/Claude.app` (Contents/Resources/app.asar) | the app; the model-name validator lives in the asar (`docs/findings.md` §1) |
| `/Library/Managed Preferences/com.anthropic.claudefordesktop.plist` | managed config the app reads at launch (sudo to write) |
| `~/Library/Application Support/Claude-3p/` | 3P profile: chats, memory, `configLibrary/` (Developer-UI config), `cowork_plugins/` |
| `~/Library/Application Support/Claude/` | first-party profile (untouched by this setup) |
| `~/Library/Logs/Claude-3p/` | app logs (`main.log`, `custom3p-setup.log`, diagnostics) |
| `~/Library/Logs/claude-glm-stack.log` | gateway log |
| `~/.config/claude-glm-stack/key` | your Z.AI key (mode 600) |
| `~/.claude/settings.json` | Claude Code user config — also read by the Desktop **Code tab** |

Diagnostics when something is off: in the app, Help → Troubleshooting →
Generate Diagnostic Report (look at `provider-status.txt`).

## Community (same problem, other approaches)

* https://github.com/kakaballina/claude-desktop-glm-bridge — Windows/Node translating proxy (same architecture as this repo)
* https://github.com/KaramelliS/claude-desktop-glm — Windows/PowerShell direct config
  (claims native `glm-*` model names via `/v1/models`; does not hold for z.ai — see `findings.md` §3)

## Fetching docs as an agent

The Anthropic docs are plain, fetchable pages; start from the `llms.txt` index
above. Z.AI docs are static HTML. No auth needed for either.
