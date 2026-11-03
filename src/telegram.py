import httpx
from src.config import CredentialsConfig

MAX_TG_LEN = 4096


def send_telegram_message(creds: CredentialsConfig, html_text: str) -> None:
    url = f"https://api.telegram.org/bot{creds.telegram_bot_token}/sendMessage"
    # shortcut: hard-splits if a single post summary exceeds 4096 chars; switch to line-aware splitting if HTML tags get cut
    chunks = [html_text[i : i + MAX_TG_LEN] for i in range(0, len(html_text), MAX_TG_LEN)]
    with httpx.Client(timeout=15.0) as client:
        for chunk in chunks:
            try:
                resp = client.post(
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
