import argparse
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from src.collector import RedditClient
from src.comments import fetch_and_select_comments
from src.config import load_config
from src.digest import render_telegram_html, save_markdown_digest
from src.filters import filter_posts
from src.storage import Storage
from src.summarizer import Summarizer
from src.telegram import send_telegram_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("digest")


def run_pipeline() -> None:
    cfg = load_config()
    storage = Storage(cfg.storage.db_path)
    reddit = RedditClient(cfg.credentials)
    summarizer = Summarizer(cfg)
    delivered_items = []

    try:
        for sub in cfg.subreddits:
            log.info("Fetching r/%s (top & comments in %s)...", sub, cfg.collection.time_filter)
            try:
                raw_posts = reddit.fetch_hot_posts(sub, cfg.collection)
            except Exception as exc:
                log.error("Failed fetching r/%s: %s", sub, exc)
                continue

            candidates = filter_posts(raw_posts, cfg.collection, storage)
            log.info("r/%s: %d unique hot posts in pool, %d candidates after filtering", sub, len(raw_posts), len(candidates))

            processed_in_sub = 0
            for post in candidates:
                if processed_in_sub >= cfg.collection.limit_per_subreddit:
                    break
                try:
                    comments = fetch_and_select_comments(reddit, post.id, cfg.comments)
                    post.num_comments = len(comments)
                    if len(comments) < cfg.collection.min_comments:
                        log.info("Skipping post %s (only %d/%d qualifying comments)", post.id, len(comments), cfg.collection.min_comments)
                        continue

                    processed_in_sub += 1
                    storage.save_post(post, status="COLLECTED")
                    summary = summarizer.summarize(post, comments)

                    if summary.relevance_score < cfg.llm.min_relevance_score:
                        log.info("Skipping %s (relevance=%d)", post.id, summary.relevance_score)
                        storage.save_post(post, status="SKIPPED", summary=summary)
                        continue

                    storage.save_post(post, status="SUMMARIZED", summary=summary)
                    delivered_items.append((post, summary))
                except Exception as exc:
                    log.error("Error processing post %s: %s", post.id, exc)

        if delivered_items:
            md_path = save_markdown_digest(delivered_items, cfg.storage.digest_dir)
            log.info("Saved %d items to %s", len(delivered_items), md_path)

            for post, summary in delivered_items:
                try:
                    send_telegram_message(cfg.credentials, render_telegram_html(post, summary))
                    storage.mark_status(post.id, "DELIVERED")
                except Exception as exc:
                    log.error("Telegram delivery failed for %s: %s", post.id, exc)
    finally:
        reddit.close()
        storage.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reddit AI Digest")
    parser.add_argument("--once", action="store_true", help="Run pipeline once and exit (default)")
    parser.add_argument("--schedule", action="store_true", help="Run periodically on schedule")
    args = parser.parse_args()

    if args.schedule:
        cfg = load_config()
        scheduler = BlockingScheduler()
        scheduler.add_job(run_pipeline, "interval", hours=cfg.schedule.interval_hours)
        log.info("Scheduled pipeline every %s hours. Running initial pass now...", cfg.schedule.interval_hours)
        run_pipeline()
        scheduler.start()
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
