# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-04

### Added

- Initial Cursor Marketplace plugin scaffold
- Skill: `telegram-gateway` (architecture, setup, pitfalls)
- Portable Python helpers: `telegram_lib.py`, `telegram-listen`, `telegram-send`, `telegram-typing`, `telegram-drain`
- `install.sh` to install CLI scripts under `/home/box/bin` or `~/.local/bin`
- Agent discovery via `GROK_AGENT_ID` or cwd under `agent-data` / `sand-data`
- Connector-secret loading for `bot_token`, optional `grok_webhook_url` / `grok_webhook_key`
- Webhook wake (`wake_grok`), typing on inbound, long-poll listener, drain
