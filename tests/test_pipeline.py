from pathlib import Path
import pytest
from src.collector import extract_md_text, merge_and_score_posts
from src.config import CollectionConfig, CredentialsConfig, load_config
from src.digest import render_telegram_html, save_markdown_digest
from src.filters import filter_posts
from src.schemas import DigestSummary, Post
from src.storage import Storage

NOW_TS = 1700000000.0


def make_post(
    id: str = "p1",
    is_self: bool = True,
    selftext: str = "x" * 100,
    num_comments: int = 5,
    stickied: bool = False,
    created_utc: float = NOW_TS - 3600,
    hot_score: float = 50.0,
) -> Post:
    return Post(
        id=id,
        subreddit="Embedded",
        title="DMA UART Ring Buffer on STM32",
        selftext=selftext,
        url="https://reddit.com/r/Embedded/p1",
        permalink="https://www.reddit.com/r/Embedded/comments/p1",
        created_utc=created_utc,
        score=25,
        hot_score=hot_score,
        num_comments=num_comments,
        is_self=is_self,
        stickied=stickied,
    )


def test_config_rejects_placeholders_and_hides_repr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=your_gemini_api_key_here\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_api_key_here")
    with pytest.raises(ValueError, match="Missing or placeholder secret"):
        load_config(env_path=env_file)

    creds = CredentialsConfig(
        gemini_api_key="super_secret_gemini",
        telegram_bot_token="super_secret_tg_token",
        telegram_chat_id="999999",
    )
    assert "super_secret" not in repr(creds)
    assert "999999" not in repr(creds)


def test_filter_and_sqlite_dedup(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    cfg = CollectionConfig(
        limit_per_subreddit=10,
        fetch_pool_size=20,
        max_age_days=7,
        min_selftext_chars=80,
        min_comments=2,
    )

    good = make_post(id="good", num_comments=5)
    short_self = make_post(id="short", selftext="too short")
    quiet_post = make_post(id="quiet", is_self=True, num_comments=1)
    old_post = make_post(id="old", created_utc=NOW_TS - (8 * 86400))
    sticky = make_post(id="sticky", stickied=True)

    res = filter_posts([good, short_self, quiet_post, old_post, sticky], cfg, storage, now_ts=NOW_TS)
    assert [p.id for p in res] == ["good"]

    # Once marked SUMMARIZED, it must be skipped on next run
    storage.save_post(good, status="SUMMARIZED")
    assert filter_posts([good], cfg, storage, now_ts=NOW_TS) == []
    storage.close()


def test_hot_priority_before_recency(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    cfg = CollectionConfig(limit_per_subreddit=5, max_age_days=7, min_selftext_chars=80, min_comments=2)

    # Newer post with lower hot_score vs Older post (within 7 days) with higher hot_score
    newer_less_hot = make_post(id="newer_low", created_utc=NOW_TS - 1800, hot_score=40.0)
    older_very_hot = make_post(id="older_hot", created_utc=NOW_TS - (3 * 86400), hot_score=85.0)
    same_hot_older = make_post(id="tie_older", created_utc=NOW_TS - (2 * 86400), hot_score=60.0)
    same_hot_newer = make_post(id="tie_newer", created_utc=NOW_TS - 3600, hot_score=60.0)

    res = filter_posts(
        [newer_less_hot, same_hot_older, older_very_hot, same_hot_newer],
        cfg,
        storage,
        now_ts=NOW_TS,
    )
    assert [p.id for p in res] == ["older_hot", "tie_newer", "tie_older", "newer_low"]
    storage.close()


def test_merge_and_score_posts_combines_upvotes_and_comments():
    p_both = make_post(id="both", created_utc=NOW_TS - 7200)
    p_top_only = make_post(id="top_only", created_utc=NOW_TS - 3600)
    p_com_only = make_post(id="com_only", created_utc=NOW_TS - 1800)

    top_feed = [p_top_only, p_both]
    comment_feed = [p_both, p_com_only]

    merged = merge_and_score_posts(top_feed, comment_feed, pool_size=2)
    assert [p.id for p in merged] == ["both", "top_only", "com_only"]
    assert merged[0].hot_score == 70.0  # 60*(1/2) + 40*(2/2) = 30 + 40 = 70
    assert merged[1].hot_score == 60.0  # 60*(2/2) + 0 = 60
    assert merged[2].hot_score == 20.0  # 0 + 40*(1/2) = 20


def test_extract_md_text_strips_html():
    raw_html = '<!-- SC_OFF --><div class="md"><p>Use <code>DMA</code> &amp; idle line.</p><p>Second line</p></div><!-- SC_ON -->'
    assert extract_md_text(raw_html) == "Use DMA & idle line.\nSecond line"


def test_markdown_and_telegram_rendering(tmp_path: Path):
    post = make_post(id="p1", selftext="content")
    post.title = "C++ <template> & tricks"
    summary = DigestSummary(
        relevance_score=4,
        post_type="problem",
        summary="OP gặp lỗi tăng kích thước firmware khi dùng template trên STM32, đã thử bật -Os nhưng chưa giảm.",
        comment_insights=[],
        study_topics=["Type Erasure trong C++ — Kỹ thuật giảm sinh mã trùng lặp khi dùng template"],
        notes=[],
    )
    md_file = save_markdown_digest([(post, summary)], tmp_path)
    assert md_file.exists()
    md_text = md_file.read_text(encoding="utf-8")
    assert "OP gặp lỗi tăng kích thước firmware" in md_text
    assert "Chưa có bình luận" in md_text

    tg_html = render_telegram_html(post, summary)
    assert "&lt;template&gt; &amp; tricks" in tg_html
    assert "<b>🛠️ Bối cảnh &amp; Vấn đề:</b>" in tg_html
    assert "• Chưa có bình luận" in tg_html
    assert "⚠️ Lưu ý" not in tg_html
