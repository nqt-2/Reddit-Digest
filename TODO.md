# Audit TODO

## Must Fix

- [x] **1. Candidate posts cut to limit before checking comments or AI relevance** (`src/filters.py`, `src/main.py`)
  - **Issue:** `filter_posts` sliced candidates to `limit` before `run_pipeline` checked `min_comments` and `min_relevance_score`, causing fewer than `N` posts (or 0) to be returned when top candidates were skipped.
  - **Fix:** Pass full pool to `filter_posts` in `run_pipeline` and stop per subreddit only after `max_per_sub` posts pass comment and relevance checks.

- [x] **2. Failed Telegram sends never retried and out of sync with Markdown digest** (`src/storage.py`, `src/main.py`)
  - **Issue:** `Storage.is_processed` treated `"SUMMARIZED"` as completed, skipping failed Telegram deliveries on future runs; `run_pipeline` also wrote Markdown before Telegram delivery and ignored cached summaries in normal mode.
  - **Fix:** Only treat `"DELIVERED"` and `"SKIPPED"` as processed, always reuse `storage.get_summary(post.id)`, and only write delivered items to the daily Markdown file.

- [x] **3. Fresh posts with fewer than 2 comments permanently marked `SKIPPED`** (`src/main.py`, `src/storage.py`)
  - **Issue:** Posts with `< min_comments` were marked `"SKIPPED"`, permanently excluding new posts that later gained comments.
  - **Fix:** Keep low-comment posts in `"COLLECTED"` status so future runs recheck them; only mark `"SKIPPED"` when AI relevance is below threshold.

- [x] **4. Link, image, and video posts with short captions misclassified as self posts and dropped** (`src/collector.py:L41`, `src/filters.py:L29`)
  - **Issue:** `is_self = (ext_url == permalink) or bool(selftext)` marks link/media posts with a short caption (< 80 chars) as `is_self = True`, causing `filter_posts` to drop them.
  - **Fix:** Change `is_self` in `_parse_rss_entries` to `is_self = ext_url == permalink`.

- [x] **5. `--schedule` mode runs scheduler and bot loop on separate threads without coordinating rate limits or file writes** (`src/main.py:L308-L318`, `requirements.txt:L6`)
  - **Issue:** `BackgroundScheduler` and `run_bot_loop` can run `run_pipeline` simultaneously on different threads, doubling Reddit request rates and writing to SQLite and `digests/*.md` concurrently.
  - **Fix:** Remove `APScheduler` and trigger scheduled runs inside `run_bot_loop` using `time.monotonic()`.

## Should Fix

- [x] **6. Duplicated pipeline setup, comment fetching, and summarization across runner functions** (`src/main.py:L30-L181`)
  - **Issue:** `run_pipeline`, `run_quick_list`, and `run_summarize_posts` duplicate setup and summarization logic, and `handle_telegram_command` loads config twice per command.
  - **Fix:** Extract a shared helper for summarizing/delivering posts and pass the loaded `AppConfig` into runner functions.

- [x] **7. Dead code and fake fields left over from Reddit JSON API** (`src/collector.py:L58-L62, L115-L120`, `src/comments.py:L36-L44`, `src/summarizer.py:L22-L24`, `src/schemas.py`)
  - **Issue:** `fetch_new_posts` is unused; RSS feeds never populate `Post.stickied`, `Comment.score`, or `Comment.replies` (sending fake `[score=1]` labels to Gemini); `max_top_level * (1 + max_replies_per_comment)` is an opaque way to set 24 comments.
  - **Fix:** Delete `fetch_new_posts`, `Post.stickied`, `Comment.score`, `Comment.replies`, and `max_replies_per_comment`; use a single `max_comments` setting.

- [x] **8. Missing tests for RSS XML parsing and comment selection** (`src/collector.py:L24-L65`, `src/comments.py:L13-L49`, `tests/test_pipeline.py`)
  - **Issue:** Tests only use synthetic `make_post()` objects and never exercise `_parse_rss_entries` or `fetch_and_select_comments` against sample Atom XML.
  - **Fix:** Add a unit test in `tests/test_pipeline.py` covering post and comment RSS XML parsing.

- [x] **9. `extract_md_text` leaks RSS HTML footer if `<!-- SC_ON -->` is absent** (`src/collector.py:L17`)
  - **Issue:** `r'<div class="md">(.*?)</div>\s*(?:<!-- SC_ON -->|$)'` fails to match if trailing HTML follows `</div>` without `<!-- SC_ON -->`, falling back to `raw_html`.
  - **Fix:** Simplify the regex to `r'<div class="md">(.*?)</div>'`.

## Nice to Have

- [x] **10. New HTTP client created on every Telegram poll and message** (`src/telegram.py:L109, L137`)
  - **Issue:** `send_telegram_message` and `fetch_telegram_updates` open and close a new `httpx.Client` on every call, repeating TLS handshakes every 30s in `--bot` mode.
  - **Fix:** Reuse a single `httpx.Client` instance across Telegram API calls.

- [x] **11. Unescaped square brackets in post titles can break Markdown digest links** (`src/digest.py:L15`)
  - **Issue:** `## [{post.title}]({post.permalink})` does not escape `[` or `]` in `post.title`.
  - **Fix:** Escape brackets in `post.title` when rendering Markdown links.
