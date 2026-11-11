import html
import re
from typing import Literal
import httpx
from pydantic import BaseModel
from src.config import CredentialsConfig

MAX_TG_LEN = 4096
SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")
_http_client = httpx.Client(timeout=15.0)


class BotCommand(BaseModel):
    kind: Literal["help", "defaults", "subreddit", "sum", "invalid"]
    subreddit: str | None = None
    limit: int | None = None
    indices: list[int] = []


def parse_bot_command(text: str) -> BotCommand | None:
    cleaned = text.strip()
    if not cleaned.startswith("/"):
        return None

    tokens = cleaned.split()
    cmd_token = tokens[0].split("@", 1)[0]
    args = tokens[1:]

    if cmd_token.lower() in ("/start", "/help"):
        return BotCommand(kind="help")

    cmd_body = cmd_token.removeprefix("/").removeprefix("r/").strip("/")
    cmd_lower = cmd_body.lower()

    if cmd_lower == "sum":
        if not args:
            return BotCommand(kind="invalid")
        indices: list[int] = []
        for arg in args:
            if not arg.isdigit():
                return BotCommand(kind="invalid")
            val = int(arg)
            if val < 1 or val > 100:
                return BotCommand(kind="invalid")
            if val not in indices:
                indices.append(val)
        return BotCommand(kind="sum", indices=indices)

    limit: int | None = None
    if len(args) > 1:
        return BotCommand(kind="invalid")
    if len(args) == 1:
        if not args[0].isdigit():
            return BotCommand(kind="invalid")
        val = int(args[0])
        if 1 <= val <= 25:
            limit = val
        else:
            return BotCommand(kind="invalid")

    if cmd_lower == "defaults":
        return BotCommand(kind="defaults", limit=limit)

    if SUBREDDIT_RE.match(cmd_body):
        return BotCommand(kind="subreddit", subreddit=cmd_body, limit=limit)

    return BotCommand(kind="invalid")


def render_help_html(default_subs: list[str], default_limit: int) -> str:
    subs_str = ", ".join(f"r/{html.escape(s)}" for s in default_subs)
    return (
        "<b>🤖 Hướng dẫn sử dụng Reddit AI Digest Bot:</b>\n\n"
        f"• <code>/defaults [N]</code> — Xem danh sách bài hot từ các subreddit mặc định ({subs_str}, mặc định {default_limit} bài/subreddit)\n"
        f"• <code>/&lt;subreddit&gt; [N]</code> — Xem danh sách bài hot (7 ngày qua) của <code>r/&lt;subreddit&gt;</code> (mặc định {default_limit} bài, VD: <code>/python</code> hoặc <code>/robotics 10</code>)\n"
        "• <code>/sum &lt;số&gt; [số...]</code> — Tóm tắt AI các bài viết được chọn từ danh sách gần nhất (VD: <code>/sum 2</code> hoặc <code>/sum 1 3</code>)\n"
        "• <code>/help</code> — Hiển thị hướng dẫn này"
    )


def send_telegram_message(creds: CredentialsConfig, html_text: str) -> None:
    url = f"https://api.telegram.org/bot{creds.telegram_bot_token}/sendMessage"
    # shortcut: hard-splits if a single post summary exceeds 4096 chars; switch to line-aware splitting if HTML tags get cut
    chunks = [html_text[i : i + MAX_TG_LEN] for i in range(0, len(html_text), MAX_TG_LEN)]
    for chunk in chunks:
        try:
            resp = _http_client.post(
                url,
                json={
                    "chat_id": creds.telegram_chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        except httpx.HTTPError as exc:
            # Never include `exc` directly because httpx embeds the full bot token URL in request errors
            raise RuntimeError(f"Telegram network error: {type(exc).__name__}") from None
        if not resp.is_success:
            raise RuntimeError(f"Telegram API returned HTTP {resp.status_code}")


def fetch_telegram_updates(
    creds: CredentialsConfig,
    offset: int | None = None,
    timeout: int = 30,
) -> list[dict]:
    url = f"https://api.telegram.org/bot{creds.telegram_bot_token}/getUpdates"
    params: dict[str, int] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    try:
        resp = _http_client.get(url, params=params, timeout=timeout + 10.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Telegram network error: {type(exc).__name__}") from None
    if not resp.is_success:
        raise RuntimeError(f"Telegram API returned HTTP {resp.status_code}")
    data = resp.json()
    return data.get("result", []) if data.get("ok") else []
