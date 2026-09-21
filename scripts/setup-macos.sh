#!/usr/bin/env bash
# claude-glm-stack -- macOS setup
#
# Does everything scriptable:
#   1. installs the local model-rewrite gateway as a launchd agent (auto-start, KeepAlive)
#   2. writes Claude Desktop's managed config (third-party inference -> gateway)
#   3. restarts Claude Desktop and runs the self-test
#
# The only thing you provide: your Z.AI API key ($ZAI_API_KEY or interactive prompt).
#
# Usage:
#   ./scripts/setup-macos.sh                # managed-config route (needs sudo once)
#   ./scripts/setup-macos.sh --config-library   # seed the Developer-Mode config file instead (no sudo)
#   ./scripts/setup-macos.sh --uninstall    # remove agent + managed config
#
set -euo pipefail

PORT="${CLAUDE_GLM_GATEWAY_PORT:-8788}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_LABEL="com.claude-glm-stack.gateway"
AGENT_PLIST="$HOME/Library/LaunchAgents/$AGENT_LABEL.plist"
KEY_FILE="$HOME/.config/claude-glm-stack/key"
DESKTOP_APP="/Applications/Claude.app"
MANAGED_PLIST="/Library/Managed Preferences/com.anthropic.claudefordesktop.plist"
DESKTOP_DOMAIN="com.anthropic.claudefordesktop"
MODE="managed"

say() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --config-library) MODE="config-library" ;;
    --uninstall) MODE="uninstall" ;;
    *) die "unknown flag: $arg" ;;
  esac
done

[[ "$(uname)" == "Darwin" ]] || die "macOS only (this script); see README for Windows pointers"
command -v python3 >/dev/null || die "python3 not found"

# ---------------------------------------------------------------- uninstall
if [[ "$MODE" == "uninstall" ]]; then
  say "Removing launchd agent"
  launchctl bootout "gui/$(id -u)/$AGENT_LABEL" 2>/dev/null || true
  rm -f "$AGENT_PLIST"
  if [[ -f "$MANAGED_PLIST" ]] && sudo rm -f "$MANAGED_PLIST"; then
    say "Removed managed config (Desktop falls back to normal sign-in)"
  fi
  say "Done. (kept: $KEY_FILE -- delete manually if you want)"
  exit 0
fi

# ---------------------------------------------------------------- API key
if [[ -z "${ZAI_API_KEY:-}" && -f "$KEY_FILE" ]]; then
  ZAI_API_KEY="$(cat "$KEY_FILE")"
fi
if [[ -z "${ZAI_API_KEY:-}" ]]; then
  printf 'Z.AI API key (input hidden): '
  read -rs ZAI_API_KEY; echo
  [[ -n "$ZAI_API_KEY" ]] || die "empty key"
fi
[[ ${#ZAI_API_KEY} -ge 20 ]] || die "that does not look like a Z.AI key"

mkdir -p "$(dirname "$KEY_FILE")"
umask 077; printf '%s' "$ZAI_API_KEY" > "$KEY_FILE"; umask 022
say "Key stored at $KEY_FILE (chmod 600); gateway picks it up from there"

# quick key check against the real endpoint (1 token)
python3 - "$ZAI_API_KEY" <<'PYEOF' || die "Z.AI rejected the key"
import json, sys, urllib.request
req = urllib.request.Request("https://api.z.ai/api/anthropic/v1/messages",
    data=json.dumps({"model": "glm-5.3-flash", "max_tokens": 1,
                     "messages": [{"role": "user", "content": "hi"}]}).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + sys.argv[1],
             "anthropic-version": "2023-06-01"})
urllib.request.urlopen(req, timeout=30)
print("      key valid: Z.AI answered")
PYEOF

# ---------------------------------------------------------------- gateway
say "Installing gateway launchd agent (port $PORT)"
cat > "$AGENT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>$AGENT_LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>/usr/bin/python3</string>
		<string>$REPO_DIR/gateway.py</string>
		<string>$PORT</string>
	</array>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>ProcessType</key><string>Background</string>
	<key>StandardOutPath</key><string>$HOME/Library/Logs/claude-glm-stack.log</string>
	<key>StandardErrorPath</key><string>$HOME/Library/Logs/claude-glm-stack.log</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/$AGENT_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENT_PLIST"
sleep 1.5
python3 -c "import socket; socket.create_connection(('127.0.0.1', $PORT), timeout=3)" \
  || die "gateway did not come up -- see ~/Library/Logs/claude-glm-stack.log"
say "Gateway up on 127.0.0.1:$PORT"

# ---------------------------------------------------------------- Desktop
if [[ ! -d "$DESKTOP_APP" ]]; then
  say "Claude Desktop not found -- installing via Homebrew"
  command -v brew >/dev/null || die "install Claude Desktop manually from claude.com/download, then re-run"
  brew install --cask claude
fi

if [[ "$MODE" == "managed" ]]; then
  say "Writing managed config (sudo; the documented zero-UI deployment route)"
  say "Note: Desktop gets a placeholder key -- the real key lives only in the gateway"
  sudo python3 - "$PORT" <<'PYEOF' || die "failed to write managed plist"
import plistlib, sys, pathlib
port = sys.argv[1]
cfg = {
    "inferenceProvider": "gateway",
    "inferenceGatewayBaseUrl": f"http://127.0.0.1:{port}",
    "inferenceGatewayApiKey": "via-local-gateway",
    "inferenceGatewayAuthScheme": "bearer",
    "inferenceCredentialKind": "static",
    "inferenceModels": [
        {"name": "claude-opus-5", "labelOverride": "GLM-5.3", "supports1m": True,
         "anthropicFamilyTier": "opus", "isFamilyDefault": True, "maxEffort": "max"},
        {"name": "claude-sonnet-4-5", "labelOverride": "GLM-5.3 Flash",
         "anthropicFamilyTier": "sonnet", "isFamilyDefault": True},
    ],
}
p = pathlib.Path("/Library/Managed Preferences")
p.mkdir(parents=True, exist_ok=True)
(p / "com.anthropic.claudefordesktop.plist").write_bytes(plistlib.dumps(cfg))
print("      wrote", p / "com.anthropic.claudefordesktop.plist")
PYEOF
else
  say "Seeding Developer-Mode configLibrary (no sudo; unverified on a fresh install)"
  CL_DIR="$HOME/Library/Application Support/Claude-3p/configLibrary"
  mkdir -p "$CL_DIR"
  python3 - "$CL_DIR" "$PORT" <<'PYEOF'
import json, pathlib, sys, uuid
cl, port = sys.argv[1], sys.argv[2]
entry_id = str(uuid.uuid4())
cfg = {
    "inferenceProvider": "gateway",
    "inferenceGatewayBaseUrl": f"http://127.0.0.1:{port}",
    "inferenceGatewayApiKey": "via-local-gateway",
    "inferenceGatewayAuthScheme": "bearer",
    "inferenceCredentialKind": "static",
    "modelDiscoveryEnabled": False,
    "inferenceModels": [
        {"name": "claude-opus-5", "labelOverride": "GLM-5.3", "supports1m": True, "prefer1m": True,
         "anthropicFamilyTier": "opus", "isFamilyDefault": True, "maxEffort": "max"},
        {"name": "claude-sonnet-4-5", "labelOverride": "GLM-5.3 Flash",
         "anthropicFamilyTier": "sonnet", "isFamilyDefault": True},
    ],
    "defaultModelEffort": "max",
    "alwaysStartWithDefaultModel": True,
}
(pathlib.Path(cl) / f"{entry_id}.json").write_text(json.dumps(cfg, indent=2))
(pathlib.Path(cl) / "_meta.json").write_text(json.dumps(
    {"appliedId": entry_id, "entries": [{"id": entry_id, "name": "claude-glm-stack"}]}, indent=2))
print("      wrote", cl)
PYEOF
fi

# ---------------------------------------------------------------- restart + test
say "Restarting Claude Desktop"
osascript -e 'tell application "Claude" to quit' 2>/dev/null || true
sleep 2; pkill -f 'Claude.app/Contents/MacOS/Claude' 2>/dev/null || true; sleep 2
open -a Claude

say "Running self-test (burns ~50 tokens)"
python3 "$REPO_DIR/scripts/selftest.py" "$PORT" || true

cat <<EOF

---------------------------------------------------------------
Done. Open Claude Desktop:
  * sign-in screen should offer starting with your provider config
    (do NOT sign in to claude.ai)
  * model picker: "GLM-5.3" (opus tier) and "GLM-5.3 Flash" (sonnet tier)
If the provider is not detected: Help -> Troubleshooting ->
Enable Developer Mode, then Developer -> Configure Third-Party
Inference, point it at http://127.0.0.1:$PORT (see README, "Manual route").
Logs: ~/Library/Logs/claude-glm-stack.log
---------------------------------------------------------------
EOF
