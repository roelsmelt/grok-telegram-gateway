#!/usr/bin/env bash
# Install Grok Telegram Gateway CLI helpers onto this box.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -d /home/box/bin ]] || [[ "$(id -u)" -eq 0 ]] || [[ -w /home/box 2>/dev/null ]]; then
  if [[ -d /home/box ]] && mkdir -p /home/box/bin 2>/dev/null; then
    DEST="/home/box/bin"
  else
    DEST="${HOME}/.local/bin"
    mkdir -p "${DEST}"
  fi
else
  DEST="${HOME}/.local/bin"
  mkdir -p "${DEST}"
fi

# Also keep a copy under ~/.local/grok-telegram-gateway for skill path docs
SHARE="${HOME}/.local/grok-telegram-gateway"
mkdir -p "${SHARE}/scripts"
mkdir -p "${SHARE}/state"

FILES=(telegram_lib.py telegram-listen telegram-send telegram-typing telegram-drain)

echo "Installing Grok Telegram Gateway scripts"
echo "  from: ${SCRIPT_DIR}"
echo "  to:   ${DEST}"
echo "  share:${SHARE}/scripts"

for f in "${FILES[@]}"; do
  src="${SCRIPT_DIR}/${f}"
  if [[ ! -f "${src}" ]]; then
    echo "missing: ${src}" >&2
    exit 1
  fi
  cp -f "${src}" "${DEST}/${f}"
  cp -f "${src}" "${SHARE}/scripts/${f}"
  chmod +x "${DEST}/${f}" "${SHARE}/scripts/${f}"
done

# Ensure DEST is on PATH hint
case ":${PATH}:" in
  *":${DEST}:"*) ;;
  *)
    echo
    echo "Note: add to PATH if needed:"
    echo "  export PATH=\"${DEST}:\$PATH\""
    ;;
esac

cat << NEXT

Installed. Next steps:

1. BotFather
   - Create a bot (/newbot) and copy the token (never paste in chat).
   - /setprivacy → Disable (so the bot sees group messages without @mention).

2. Connector secrets (secret-request on the Grok agent)
   - connector: telegram
   - fields:
       bot_token          (required)
       grok_webhook_url   (optional, for instant wake)
       grok_webhook_key   (optional, Bearer key from webhook routine)

3. Agent id
   - export GROK_AGENT_ID=<agent-uuid>
   - or run helpers with cwd under agent-data/agents/<uuid>/ or sand-data/agents/<uuid>/
   - secrets path: connector-secrets/<agent_id>/telegram.json

4. Routines
   - Create webhook routine telegram-inbound (typing → send; DMs reply;
     groups surface or reply on @mention / explicit ask).
   - Copy Webhook URL + Webhook key into secrets above.
   - Optional cron telegram-drain every 5+ minutes as backup only.

5. Start listener
   - telegram-listen   # long-poll; keep running (supervisor/nohup)
   - telegram-drain    # one-shot inbox drain / health check
   - telegram-typing <chat_id>
   - telegram-send <chat_id> <message>

6. Skill / plugin
   - Skill lives at: ${PLUGIN_ROOT}/skills/telegram-gateway/SKILL.md
   - Or install the plugin from this repo / Cursor Marketplace.

State defaults to channels/telegram/state under the agent, or:
  ${SHARE}/state

Never print bot tokens, webhook keys, or Authorization headers.
NEXT
