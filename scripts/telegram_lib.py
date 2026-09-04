#!/usr/bin/env python3
"""Portable Telegram helpers for Grok Bot. Token from connector-secret only; never print it."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_ROOT = "https://api.telegram.org"
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
FALLBACK_STATE = Path.home() / ".local" / "grok-telegram-gateway" / "state"


class TelegramError(RuntimeError):
    pass


def _is_uuid(value: str) -> bool:
    return bool(UUID_RE.match(value.strip()))


def discover_agent_id() -> str | None:
    """Resolve agent id from env or cwd under agent-data/sand-data agents/<uuid>/."""
    env = (os.environ.get("GROK_AGENT_ID") or "").strip()
    if env and _is_uuid(env):
        return env

    cwd = Path.cwd().resolve()
    parts = cwd.parts
    for i, part in enumerate(parts):
        if part in ("agent-data", "sand-data") and i + 2 < len(parts):
            if parts[i + 1] == "agents" and _is_uuid(parts[i + 2]):
                return parts[i + 2]
        # Also match .../agents/<uuid>/... anywhere
        if part == "agents" and i + 1 < len(parts) and _is_uuid(parts[i + 1]):
            # Prefer when parent looks like agent-data or sand-data
            if i > 0 and parts[i - 1] in ("agent-data", "sand-data"):
                return parts[i + 1]

    # Walk parents for agents/<uuid>
    for parent in [cwd, *cwd.parents]:
        if parent.name and _is_uuid(parent.name) and parent.parent.name == "agents":
            grand = parent.parent.parent.name if parent.parent.parent else ""
            if grand in ("agent-data", "sand-data", ""):
                return parent.name
    return None


def _agent_roots(agent_id: str) -> list[Path]:
    """Candidate roots that contain connector-secrets/ and agents/."""
    roots: list[Path] = []
    for base in (Path("/home/box/sand-data"), Path("/home/box/agent-data")):
        if base.is_dir():
            roots.append(base)
    # If cwd is under a data root, prefer that root first
    cwd = Path.cwd().resolve()
    for i, part in enumerate(cwd.parts):
        if part in ("sand-data", "agent-data"):
            candidate = Path(*cwd.parts[: i + 1])
            if candidate.is_dir() and candidate not in roots:
                roots.insert(0, candidate)
            elif candidate in roots:
                roots.remove(candidate)
                roots.insert(0, candidate)
            break
    # Deduplicate while preserving order
    seen: set[Path] = set()
    ordered: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return ordered


def secret_paths(agent_id: str) -> list[Path]:
    return [
        root / "connector-secrets" / agent_id / "telegram.json"
        for root in _agent_roots(agent_id)
    ]


def agent_channel_dir(agent_id: str) -> Path | None:
    for root in _agent_roots(agent_id):
        channel = root / "agents" / agent_id / "channels" / "telegram"
        # Prefer existing agent dir; otherwise use first writable sand/agent root
        agent_dir = root / "agents" / agent_id
        if agent_dir.is_dir() or (root / "connector-secrets" / agent_id).is_dir():
            return channel
    roots = _agent_roots(agent_id)
    if roots:
        return roots[0] / "agents" / agent_id / "channels" / "telegram"
    return None


def resolve_paths() -> dict[str, Path]:
    """Return state paths. Prefer agent channel state; fall back to ~/.local/.../state."""
    agent_id = discover_agent_id()
    if agent_id:
        channel = agent_channel_dir(agent_id)
        if channel is not None:
            state = channel / "state"
            return {
                "agent_id": Path(agent_id),  # marker; use str via agent_id key below
                "channel_dir": channel,
                "state_dir": state,
                "offset_path": state / "offset.json",
                "chats_path": state / "chats.json",
                "inbox_path": state / "inbox.jsonl",
                "listen_pid": state / "listen.pid",
                "wake_log": state / "wake.log",
            }
    state = FALLBACK_STATE
    return {
        "agent_id": Path(""),
        "channel_dir": state.parent,
        "state_dir": state,
        "offset_path": state / "offset.json",
        "chats_path": state / "chats.json",
        "inbox_path": state / "inbox.jsonl",
        "listen_pid": state / "listen.pid",
        "wake_log": state / "wake.log",
    }


def _paths() -> dict[str, Path]:
    return resolve_paths()


def get_agent_id() -> str | None:
    return discover_agent_id()


class _PathProxy:
    """Proxy so imported path names behave like Path but re-resolve each use."""

    def __init__(self, key: str):
        self._key = key

    def _p(self) -> Path:
        return _paths()[self._key]

    def __fspath__(self) -> str:
        return str(self._p())

    def __str__(self) -> str:
        return str(self._p())

    def __repr__(self) -> str:
        return repr(self._p())

    def __getattr__(self, name: str) -> Any:
        return getattr(self._p(), name)


# Re-resolve on each access so cwd / GROK_AGENT_ID changes apply
STATE_DIR = _PathProxy("state_dir")
OFFSET_PATH = _PathProxy("offset_path")
CHATS_PATH = _PathProxy("chats_path")
INBOX_PATH = _PathProxy("inbox_path")
LISTEN_PID = _PathProxy("listen_pid")


def _load_secrets() -> dict[str, Any]:
    agent_id = discover_agent_id()
    candidates: list[Path] = []
    if agent_id:
        candidates.extend(secret_paths(agent_id))
    # Env override for secret file
    env_secret = (os.environ.get("TELEGRAM_SECRET_PATH") or "").strip()
    if env_secret:
        candidates.insert(0, Path(env_secret))
    for p in candidates:
        if p.exists():
            return json.loads(p.read_text())
    raise TelegramError(
        "telegram connector-secret missing "
        "(set GROK_AGENT_ID or run under agent-data/sand-data/agents/<id>/; "
        "expect connector-secrets/<id>/telegram.json)"
    )


def _load_token() -> str:
    data = _load_secrets()
    token = data.get("bot_token") or data.get("token")
    if not token:
        raise TelegramError("bot_token missing in connector-secret")
    return token


def api(method: str, payload: dict[str, Any] | None = None, *, timeout: float = 60) -> dict[str, Any]:
    token = _load_token()
    url = f"{API_ROOT}/bot{token}/{method}"
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except Exception:
            raise TelegramError(f"HTTP {e.code} for {method}") from e
    except Exception as e:
        raise TelegramError(f"{method} failed: {type(e).__name__}") from e
    if not body.get("ok"):
        desc = body.get("description") or "unknown error"
        raise TelegramError(f"{method}: {desc}")
    return body


def ensure_state() -> None:
    paths = _paths()
    paths["state_dir"].mkdir(parents=True, exist_ok=True)
    if not paths["offset_path"].exists():
        paths["offset_path"].write_text(json.dumps({"offset": 0}, indent=2) + "\n")
    if not paths["chats_path"].exists():
        paths["chats_path"].write_text(json.dumps({"chats": {}}, indent=2) + "\n")
    paths["inbox_path"].touch(exist_ok=True)


def load_offset() -> int:
    ensure_state()
    return int(json.loads(OFFSET_PATH.read_text()).get("offset") or 0)


def save_offset(offset: int) -> None:
    ensure_state()
    OFFSET_PATH.write_text(
        json.dumps({"offset": int(offset), "updated_at": int(time.time())}, indent=2) + "\n"
    )


def load_chats() -> dict[str, Any]:
    ensure_state()
    return json.loads(CHATS_PATH.read_text())


def upsert_chat(chat: dict[str, Any], user: dict[str, Any] | None = None) -> None:
    ensure_state()
    store = load_chats()
    chats = store.setdefault("chats", {})
    cid = str(chat.get("id"))
    entry = chats.get(cid, {})
    entry.update(
        {
            "id": chat.get("id"),
            "type": chat.get("type"),
            "title": chat.get("title"),
            "username": chat.get("username"),
            "first_name": chat.get("first_name"),
            "last_name": chat.get("last_name"),
            "updated_at": int(time.time()),
        }
    )
    if user:
        entry["from_user"] = {
            "id": user.get("id"),
            "username": user.get("username"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
        }
    chats[cid] = {k: v for k, v in entry.items() if v is not None}
    store["chats"] = chats
    CHATS_PATH.write_text(json.dumps(store, indent=2) + "\n")


def append_inbox(item: dict[str, Any]) -> None:
    ensure_state()
    with INBOX_PATH.open("a") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def wake_grok(update: dict[str, Any]) -> bool:
    """POST update to Grok Bot webhook routine so the agent wakes immediately."""
    try:
        secrets = _load_secrets()
    except Exception:
        return False
    url = (secrets.get("grok_webhook_url") or "").strip()
    key = (secrets.get("grok_webhook_key") or "").strip()
    if not url or not key:
        return False
    auth = key if key.lower().startswith("bearer ") else f"Bearer {key}"
    body = json.dumps(update, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": auth,
            "User-Agent": "grok-telegram-gateway/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
            return 200 <= resp.status < 300
    except Exception:
        # Never print secrets; soft-fail so listen keeps running.
        return False


def summarize_update(update: dict[str, Any]) -> dict[str, Any]:
    msg = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or {}
    )
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    text = msg.get("text") or msg.get("caption") or ""
    return {
        "update_id": update.get("update_id"),
        "message_id": msg.get("message_id"),
        "date": msg.get("date"),
        "chat_id": chat.get("id"),
        "chat_type": chat.get("type"),
        "chat_title": chat.get("title") or chat.get("username") or chat.get("first_name"),
        "from_id": user.get("id"),
        "from_username": user.get("username"),
        "from_name": " ".join(
            x for x in [user.get("first_name"), user.get("last_name")] if x
        ),
        "text": text,
        "is_command": text.startswith("/"),
        "received_at": int(time.time()),
    }


def process_updates(
    updates: list[dict[str, Any]], *, auto_start_reply: bool = True
) -> dict[str, Any]:
    """Persist chats/inbox; optionally reply to /start. Never prints token."""
    handled = 0
    starts = 0
    max_id = load_offset()
    for upd in updates:
        uid = int(upd.get("update_id") or 0)
        if uid >= max_id:
            max_id = uid + 1
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        user = msg.get("from")
        upsert_chat(chat, user)
        summary = summarize_update(upd)
        append_inbox(summary)
        # Immediate alive signal before Grok Bot finishes waking
        try:
            if summary.get("chat_id") and (summary.get("text") or "").strip():
                send_chat_action(summary["chat_id"], "typing")
        except Exception:
            pass
        woke = wake_grok(upd)
        summary_wake = {"update_id": summary.get("update_id"), "woke_grok": woke}
        try:
            with (_paths()["wake_log"]).open("a") as wf:
                wf.write(json.dumps({"ts": int(time.time()), **summary_wake}) + "\n")
        except Exception:
            pass
        handled += 1
        text = (msg.get("text") or "").strip()
        if auto_start_reply and text.startswith("/start"):
            starts += 1
            try:
                send_message(
                    chat["id"],
                    "Hi — Grok Telegram Gateway is connected. Send a message anytime. "
                    "For groups: add this bot and set BotFather /setprivacy → Disable.",
                )
            except TelegramError:
                pass
    if updates:
        save_offset(max_id)
    return {"handled": handled, "starts": starts, "next_offset": load_offset()}


def get_me() -> dict[str, Any]:
    return api("getMe")["result"]


def get_updates(
    *, offset: int | None = None, timeout: int = 0, limit: int = 100
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "timeout": timeout,
        "limit": limit,
        "allowed_updates": ["message", "edited_message", "my_chat_member", "chat_member"],
    }
    if offset is None:
        offset = load_offset()
    if offset:
        payload["offset"] = offset
    sock_timeout = max(30, timeout + 15)
    return api("getUpdates", payload, timeout=sock_timeout)["result"]


def send_message(
    chat_id: int | str, text: str, *, reply_to: int | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    return api("sendMessage", payload)["result"]


def send_chat_action(chat_id: int | str, action: str = "typing") -> dict[str, Any]:
    """Show typing/upload indicator. Telegram clears it after ~5s — refresh while working."""
    return api("sendChatAction", {"chat_id": chat_id, "action": action})["result"]


def drain_once(*, long_poll: int = 0) -> dict[str, Any]:
    ensure_state()
    updates = get_updates(timeout=long_poll)
    stats = process_updates(updates)
    stats["raw_count"] = len(updates)
    return stats


def find_chat(query: str) -> dict[str, Any] | None:
    q = query.strip().lower().lstrip("@")
    chats = load_chats().get("chats", {})
    for cid, meta in chats.items():
        hay = " ".join(
            str(meta.get(k) or "")
            for k in ("title", "username", "first_name", "last_name", "id")
        ).lower()
        if q == str(meta.get("id")) or q in hay or q == str(meta.get("username") or "").lower():
            return meta
    return None
