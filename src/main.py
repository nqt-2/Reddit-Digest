import argparse
import html
import logging
import time
from src.collector import RedditClient
from src.comments import fetch_and_select_comments
from src.config import AppConfig, CollectionConfig, load_config
from src.digest import render_quick_list_html, render_telegram_html, save_markdown_digest
from src.filters import filter_posts
from src.schemas import DigestSummary, Post
from src.storage import Storage
from src.summarizer import Summarizer
from src.telegram import (
    BotCommand,
    fetch_telegram_updates,
    parse_bot_command,
    render_help_html,
    send_telegram_message,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("digest")

LAST_QUICK_POSTS: list[Post] = []


def _collection_cfg(cfg: AppConfig, limit: int | None) -> CollectionConfig:
    if not limit:
        return cfg.collection
    return cfg.collection.model_copy(update={"fetch_pool_size": max(cfg.collection.fetch_pool_size, limit)})


def _get_or_create_summary(
    post: Post,
    cfg: AppConfig,
    storage: Storage,
    reddit: RedditClient,
    summarizer: Summarizer,
    require_min_comments: bool = True,
) -> DigestSummary | None:
    summary = storage.get_summary(post.id)
    if summary is not None:
        return summary

    storage.save_post(post, status="COLLECTED")
    comments = fetch_and_select_comments(reddit, post.id, cfg.comments)
    post.num_comments = len(comments)
    if require_min_comments and len(comments) < cfg.collection.min_comments:
        log.info("Skipping post %s (only %d/%d qualifying comments)", post.id, len(comments), cfg.collection.min_comments)
        return None

    summary = summarizer.summarize(post, comments)
    storage.save_post(post, status="SUMMARIZED", summary=summary)
    return summary


def run_pipeline(
    subreddits: list[str] | None = None,
    limit: int | None = None,
    custom_sub_mode: bool = False,
    cfg: AppConfig | None = None,
) -> tuple[int, list[str]]:
    cfg = cfg or load_config()
    target_subs = subreddits if subreddits is not None else cfg.subreddits
    collection_cfg = _collection_cfg(cfg, limit)
    storage = Storage(cfg.storage.db_path)
    reddit = RedditClient(cfg.credentials)
    summarizer = Summarizer(cfg)
    delivered_items = []
    sent_items = []
    failed_subs: list[str] = []

    try:
        for sub in target_subs:
            log.info("Fetching r/%s (top & comments in %s)...", sub, collection_cfg.time_filter)
            try:
                raw_posts = reddit.fetch_hot_posts(sub, collection_cfg)
            except Exception as exc:
                log.error("Failed fetching r/%s: %s", sub, exc)
                failed_subs.append(sub)
                continue

            max_per_sub = limit or collection_cfg.limit_per_subreddit
            candidates = filter_posts(
                raw_posts,
                collection_cfg,
                storage,
                skip_processed=not custom_sub_mode,
                limit=len(raw_posts),
            )
            log.info("r/%s: %d unique hot posts in pool, %d candidates after filter", sub, len(raw_posts), len(candidates))

            sub_items = []
            for post in candidates:
                if len(sub_items) >= max_per_sub:
                    break
                try:
                    summary = _get_or_create_summary(post, cfg, storage, reddit, summarizer, require_min_comments=True)
                    if summary is None:
                        continue

                    if not custom_sub_mode and summary.relevance_score < cfg.llm.min_relevance_score:
                        log.info("Skipping %s (relevance=%d)", post.id, summary.relevance_score)
                        storage.save_post(post, status="SKIPPED", summary=summary)
                        continue

                    sub_items.append((post, summary))
                except Exception as exc:
                    log.error("Error processing post %s: %s", post.id, exc)

            delivered_items.extend(sub_items)

        sent_items = []
        for post, summary in delivered_items:
            try:
                send_telegram_message(cfg.credentials, render_telegram_html(post, summary))
                storage.mark_status(post.id, "DELIVERED")
                sent_items.append((post, summary))
            except Exception as exc:
                log.error("Telegram delivery failed for %s: %s", post.id, exc)

        if sent_items and not custom_sub_mode:
            md_path = save_markdown_digest(sent_items, cfg.storage.digest_dir)
            log.info("Saved %d items to %s", len(sent_items), md_path)
    finally:
        reddit.close()
        storage.close()

    return len(sent_items), failed_subs


def run_quick_list(
    subreddits: list[str] | None = None,
    limit: int | None = None,
    cfg: AppConfig | None = None,
) -> tuple[list[Post], list[str]]:
    cfg = cfg or load_config()
    target_subs = subreddits if subreddits is not None else cfg.subreddits
    collection_cfg = _collection_cfg(cfg, limit)
    storage = Storage(cfg.storage.db_path)
    reddit = RedditClient(cfg.credentials)
    listed_posts: list[Post] = []
    failed_subs: list[str] = []

    try:
        for sub in target_subs:
            log.info("Quick fetching r/%s...", sub)
            try:
                raw_posts = reddit.fetch_hot_posts(sub, collection_cfg)
            except Exception as exc:
                log.error("Failed fetching r/%s: %s", sub, exc)
                failed_subs.append(sub)
                continue

            candidates = filter_posts(
                raw_posts,
                collection_cfg,
                storage=storage,
                skip_processed=False,
                skip_delivered_only=True,
                limit=limit,
            )
            start_idx = len(listed_posts) + 1
            listed_posts.extend(candidates)
            msg = render_quick_list_html(sub, candidates, collection_cfg.max_age_days, start_index=start_idx)
            send_telegram_message(cfg.credentials, msg)
    finally:
        reddit.close()
        storage.close()

    return listed_posts, failed_subs


def run_summarize_posts(posts: list[Post], cfg: AppConfig | None = None) -> int:
    cfg = cfg or load_config()
    storage = Storage(cfg.storage.db_path)
    reddit = RedditClient(cfg.credentials)
    summarizer = Summarizer(cfg)
    delivered = 0

    try:
        for post in posts:
            try:
                summary = _get_or_create_summary(post, cfg, storage, reddit, summarizer, require_min_comments=False)
                if summary is None:
                    continue
                send_telegram_message(cfg.credentials, render_telegram_html(post, summary))
                storage.mark_status(post.id, "DELIVERED")
                delivered += 1
            except Exception as exc:
                log.error("Error summarizing selected post %s: %s", post.id, exc)
    finally:
        reddit.close()
        storage.close()

    return delivered


def handle_telegram_command(cmd: BotCommand) -> None:
    global LAST_QUICK_POSTS
    cfg = load_config()
    creds = cfg.credentials
    effective_limit = cmd.limit or cfg.collection.limit_per_subreddit

    if cmd.kind == "help":
        send_telegram_message(creds, render_help_html(cfg.subreddits, cfg.collection.limit_per_subreddit))
        return

    if cmd.kind == "invalid":
        send_telegram_message(
            creds,
            "⚠️ Lệnh không hợp lệ. Gõ <code>/help</code> để xem danh sách lệnh hỗ trợ.",
        )
        return

    if cmd.kind == "sum":
        if not LAST_QUICK_POSTS:
            send_telegram_message(
                creds,
                "⚠️ Chưa có danh sách bài viết nào. Hãy chạy <code>/defaults</code> hoặc <code>/&lt;subreddit&gt;</code> trước.",
            )
            return

        total_avail = len(LAST_QUICK_POSTS)
        invalid_nums = [i for i in cmd.indices if i < 1 or i > total_avail]
        if invalid_nums:
            send_telegram_message(
                creds,
                f"⚠️ Số thứ tự không hợp lệ (danh sách hiện có từ 1 đến {total_avail}).",
            )
            return

        selected = [LAST_QUICK_POSTS[i - 1] for i in cmd.indices]
        nums_str = ", ".join(f"#{i}" for i in cmd.indices)
        send_telegram_message(creds, f"⏳ Đang tóm tắt AI bài viết {nums_str}...")
        count = run_summarize_posts(selected, cfg=cfg)
        if count == 0:
            send_telegram_message(creds, "❌ Không thể tóm tắt bài viết đã chọn.")
        return

    if cmd.kind == "defaults":
        subs_label = ", ".join(f"r/{html.escape(s)}" for s in cfg.subreddits)
        send_telegram_message(creds, f"⏳ Đang lấy danh sách bài viết từ {subs_label} (tối đa {effective_limit} bài/subreddit)...")
        listed, failed = run_quick_list(subreddits=cfg.subreddits, limit=effective_limit, cfg=cfg)
        if listed:
            LAST_QUICK_POSTS = listed
        if failed:
            failed_str = ", ".join(f"r/{html.escape(s)}" for s in failed)
            send_telegram_message(creds, f"⚠️ Không thể tải dữ liệu từ: {failed_str}.")
        return

    if cmd.kind == "subreddit" and cmd.subreddit:
        sub = cmd.subreddit
        sub_esc = html.escape(sub)
        send_telegram_message(creds, f"⏳ Đang lấy top {effective_limit} bài viết từ <b>r/{sub_esc}</b>...")
        listed, failed = run_quick_list(subreddits=[sub], limit=effective_limit, cfg=cfg)
        if listed:
            LAST_QUICK_POSTS = listed
        if failed:
            send_telegram_message(creds, f"❌ Không thể truy cập <b>r/{sub_esc}</b> (subreddit không tồn tại, riêng tư hoặc lỗi mạng).")


def run_bot_loop(schedule_interval_hours: int | None = None) -> None:
    cfg = load_config()
    creds = cfg.credentials
    offset: int | None = None
    last_run = time.monotonic()

    try:
        initial = fetch_telegram_updates(creds, offset=-1, timeout=0)
        if initial:
            offset = initial[-1]["update_id"] + 1
    except Exception as exc:
        log.warning("Could not flush initial Telegram updates: %s", exc)

    log.info("Telegram bot listening for commands (/defaults, /<subreddit>, /sum, /help)...")
    while True:
        try:
            if schedule_interval_hours and (time.monotonic() - last_run >= schedule_interval_hours * 3600):
                log.info("Running scheduled pipeline pass...")
                last_run = time.monotonic()
                run_pipeline()

            updates = fetch_telegram_updates(creds, offset=offset, timeout=30)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id != str(creds.telegram_chat_id):
                    log.warning("Ignoring message from unauthorized chat_id=%s", chat_id)
                    continue
                text = msg.get("text", "")
                cmd = parse_bot_command(text)
                if cmd is not None:
                    log.info("Executing Telegram command: %s", text.strip())
                    try:
                        handle_telegram_command(cmd)
                    except Exception as exc:
                        log.error("Error handling Telegram command '%s': %s", text, exc)
        except KeyboardInterrupt:
            log.info("Stopping Telegram bot listener.")
            break
        except Exception as exc:
            log.error("Telegram polling error: %s", exc)
            time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reddit AI Digest")
    parser.add_argument("--once", action="store_true", help="Run pipeline once and exit (default)")
    parser.add_argument("--schedule", action="store_true", help="Run periodically on schedule and listen for Telegram commands")
    parser.add_argument("--bot", action="store_true", help="Listen for Telegram bot commands (/defaults, /<subreddit>, /sum, /help)")
    args = parser.parse_args()

    if args.schedule:
        cfg = load_config()
        log.info("Scheduled pipeline every %s hours. Running initial pass now...", cfg.schedule.interval_hours)
        run_pipeline()
        run_bot_loop(schedule_interval_hours=cfg.schedule.interval_hours)
    elif args.bot:
        run_bot_loop()
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
