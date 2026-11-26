#!/bin/sh
# LifeAgent network access approved by the owner on 2026-11-25.
# Keep the sandbox_mode supplied by Agent Autoloop and only enable shell networking.
exec '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex' \
  -c 'sandbox_workspace_write.network_access=true' "$@"
