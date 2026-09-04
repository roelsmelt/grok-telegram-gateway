---
name: Telegram Gateway
description: >-
  Use this when wiring a Grok Bot to Telegram via BotFather (DM + groups):
  long-poll listener, instant webhook wake, typing indicator, and send — without
  a native Telegram channel.
---
# Telegram Gateway for Grok Bot

Grok Bot has **no native Telegram channel**. This skill rebuilds the working pattern: BotFather bot + box long-poll + wake the agent via a Grok Bot **webhook routine** (Bearer auth) + `sendChatAction` typing + send.

Do **not** print bot tokens, webhook keys, or Authorization headers in chat.

## Architecture

1. **BotFather** bot (one door for many groups — not one Grok agent per group).
2. **Connector secret** on the agent: at least `bot_token`. For instant wake also `grok_webhook_url` + `grok_webhook_key` (from the agent's webhook routine pills).
3. **Portable helpers** (after `scripts/install.sh`):
   - Installed to `/home/box/bin/` or `~/.local/bin/`, with a copy under `~/.local/grok-telegram-gateway/scripts/`
   - `telegram_lib.py` — API, inbox, `wake_grok`, typing
   - `telegram-listen` — long-poll `getUpdates` (keep running)
   - `telegram-send` / `telegram-typing` / `telegram-drain`
4. **Agent discovery**
   - `GROK_AGENT_ID` env, or cwd under `agent-data/agents/<uuid>/` / `sand-data/agents/<uuid>/`
   - Secrets: `connector-secrets/<agent_id>/telegram.json`
   - State: `<data-root>/agents/<id>/channels/telegram/state/` (fallback: `~/.local/grok-telegram-gateway/state`)
5. **Routines**
   - `telegram-inbound` — **webhook** trigger: wakes on each forwarded update; reply with `telegram-send` after `telegram-typing`.
   - `telegram-drain` — cron backup, **minimum every 5 minutes** (platform limit). Not for chat latency.
6. Telegram **cannot** call the Grok webhook directly (no Bearer header). The listener POSTs the update to the webhook with `Authorization: Bearer <key>`.

## Setup (order)

1. User creates a bot with BotFather; store token via **secret-request** (`connector: telegram`, `field: bot_token`) — never paste in chat.
2. Run `scripts/install.sh` from this plugin (or Marketplace install + install.sh).
3. Verify: `getMe` via the helpers (username, `can_join_groups`, `can_read_all_group_messages`) — e.g. `telegram-drain`.
4. User: BotFather `/setprivacy` → **Disable** so the bot sees group messages without @mention.
5. Create webhook routine `telegram-inbound` (prompt: typing → send; DMs reply; groups surface or reply only on @mention / explicit ask). Empty/`chat_id` 0 = quiet health ping.
6. User copies [Webhook URL] and [Webhook key] from that routine into secrets (`grok_webhook_url`, `grok_webhook_key`) via secret-request.
7. Ensure `wake_grok` in the lib POSTs JSON updates to that URL with Bearer auth; on each real message call `sendChatAction(typing)` then `wake_grok`.
8. Start `telegram-listen` (supervisor/nohup); confirm pid/log under the agent's `channels/telegram/state/` (or fallback state dir).
9. Optional cron `telegram-drain` every 5+ minutes as backup only.
10. User opens `t.me/<bot>`, sends `/start`, then adds the bot to groups.

## Reply rules (default)

- **DM**: typing, then short reply via `telegram-send <chat_id> …`. Require CLI line `sent message_id=…` before claiming success.
- **Groups**: note in Grok chat; reply in-group only if @mentioned or the user asked.
- Refresh typing every ~4s if work takes longer than ~5s (`sendChatAction` expires).
- Never claim a send without CLI proof.

## Pitfalls

- Cron cannot run faster than every 5 minutes — do not rely on it for “live” chat.
- Do not `setWebhook` on Telegram pointing at the Grok URL without a proxy that adds Bearer.
- After `setWebhook`, `getUpdates` conflicts (409). This gateway uses **getUpdates long-poll on the box**, not Telegram's webhook mode.
- One BotFather bot for many groups; one Grok “door” agent owns the pipe.
- Never hardcode agent UUIDs or tokens in scripts; use env / discovery / connector-secrets.
