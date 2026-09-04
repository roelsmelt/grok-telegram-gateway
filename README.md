# Grok Telegram Gateway

Cursor Marketplace plugin that wires **Grok Bot** to **Telegram** via BotFather: long-poll listener, instant webhook wake, typing indicator, and send. No native Telegram channel required.

## Install

### From this repo (local / greenfield)

```bash
# Clone or copy this plugin, then:
bash scripts/install.sh
```

Helpers land in `/home/box/bin` (when available) or `~/.local/bin`, with a share copy under `~/.local/grok-telegram-gateway/scripts/`.

### As a Cursor plugin

1. Place this folder where Cursor plugins are loaded (or submit via Marketplace).
2. Ensure `.cursor-plugin/plugin.json` is present (this repo).
3. Restart Cursor / reload window; confirm the **Telegram Gateway** skill under Customize.
4. Run `scripts/install.sh` on the agent box so CLI helpers are on `PATH`.

### Publish to Marketplace

Submit at [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish) with this single-plugin repo (manifest + skill + scripts + LICENSE).

## BotFather setup

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → save the token **only** via secret-request (never paste in chat).
2. `/setprivacy` → **Disable** so the bot receives group messages without an @mention.
3. Optionally set description / about / commands.
4. Open `t.me/<your_bot>`, send `/start`, then add the bot to groups as needed.

## Connector secrets (secret-request)

Use the agent's **secret-request** flow:

| Field | Required | Purpose |
|-------|----------|---------|
| `bot_token` | yes | Telegram Bot API token from BotFather |
| `grok_webhook_url` | for instant wake | Webhook URL pill from the `telegram-inbound` routine |
| `grok_webhook_key` | for instant wake | Webhook key (Bearer) from the same routine |

Stored at:

```text
<sand-data|agent-data>/connector-secrets/<agent_id>/telegram.json
```

Optional override: `TELEGRAM_SECRET_PATH=/path/to/telegram.json`.

**Never print tokens, keys, or Authorization headers.**

## Agent discovery

Helpers resolve the agent id from:

1. `GROK_AGENT_ID` (UUID), or
2. Current working directory under `agent-data/agents/<uuid>/` or `sand-data/agents/<uuid>/`

State directory:

```text
<data-root>/agents/<agent_id>/channels/telegram/state/
```

Fallback if no agent can be resolved:

```text
~/.local/grok-telegram-gateway/state/
```

## Webhook routine + wake

1. Create a Grok Bot **webhook** routine named e.g. `telegram-inbound`.
2. Prompt sketch: on inbound update → `telegram-typing` → think → `telegram-send`; DMs reply; groups surface or reply only on @mention / explicit ask; empty / `chat_id` 0 = quiet health ping.
3. Copy **Webhook URL** and **Webhook key** into connector secrets (`grok_webhook_url`, `grok_webhook_key`).
4. Keep `telegram-listen` running on the box. On each message it:
   - shows typing (`sendChatAction`)
   - POSTs the update JSON to the webhook with `Authorization: Bearer <key>` (`wake_grok`)
5. Optional backup: cron `telegram-drain` **every 5+ minutes** (platform minimum). Not for live latency.

Telegram cannot call the Grok webhook directly (no Bearer header). Do **not** `setWebhook` on Telegram to the Grok URL without a Bearer-adding proxy — this gateway uses **getUpdates long-poll**, not Telegram webhook mode.

## CLI

```bash
export GROK_AGENT_ID=<agent-uuid>   # if not already under the agent cwd

telegram-listen                     # long-poll (keep running)
telegram-drain                      # one-shot drain + bot health JSON
telegram-typing <chat_id>           # typing indicator (~5s)
telegram-send <chat_id> Hello       # must print: sent message_id=…
```

Require a `sent message_id=…` line before claiming a successful send.

## Layout

```text
grok-telegram-gateway/
  .cursor-plugin/plugin.json
  README.md
  LICENSE
  CHANGELOG.md
  skills/telegram-gateway/SKILL.md
  scripts/telegram_lib.py
  scripts/telegram-listen
  scripts/telegram-send
  scripts/telegram-typing
  scripts/telegram-drain
  scripts/install.sh
```

## License

MIT — see [LICENSE](LICENSE).
