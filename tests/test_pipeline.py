from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from src.collector import _parse_rss_entries, extract_md_text, merge_and_score_posts
from src.config import CollectionConfig, CredentialsConfig, load_config
from src.digest import render_quick_list_html, render_telegram_html, save_markdown_digest
from src.filters import filter_posts
from src.schemas import DigestSummary, Post
from src.storage import Storage
from src.telegram import BotCommand, parse_bot_command

NOW_TS = 1700000000.0


def make_post(
    id: str = "p1",
    is_self: bool = True,
    selftext: str = "x" * 100,
    num_comments: int = 5,
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

    res = filter_posts([good, short_self, quiet_post, old_post], cfg, storage, now_ts=NOW_TS)
    assert [p.id for p in res] == ["good"]

    # COLLECTED and SUMMARIZED (undelivered) remain eligible for retry; DELIVERED and SKIPPED are skipped
    storage.save_post(good, status="COLLECTED")
    assert [p.id for p in filter_posts([good], cfg, storage, now_ts=NOW_TS)] == ["good"]
    storage.save_post(good, status="SUMMARIZED")
    assert [p.id for p in filter_posts([good], cfg, storage, now_ts=NOW_TS)] == ["good"]
    storage.save_post(good, status="DELIVERED")
    assert filter_posts([good], cfg, storage, now_ts=NOW_TS) == []
    storage.close()


def test_hot_priority_before_recency(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    cfg = CollectionConfig(limit_per_subreddit=3, max_age_days=7, min_selftext_chars=80, min_comments=2)

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
    assert [p.id for p in res] == ["older_hot", "tie_newer", "tie_older"]
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
    # Without <!-- SC_ON --> and with trailing RSS footer HTML
    no_sc_on = '<div class="md"><p>Body text only</p></div> <span><a href="https://reddit.com">[link]</a></span>'
    assert extract_md_text(no_sc_on) == "Body text only"


def test_markdown_and_telegram_rendering(tmp_path: Path):
    post = make_post(id="p1", selftext="content")
    post.title = "[Question] C++ <template> & tricks"
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
    assert r"## [\[Question\] C++ <template> & tricks](https://www.reddit.com/r/Embedded/comments/p1)" in md_text
    assert "OP gặp lỗi tăng kích thước firmware" in md_text
    assert "Chưa có bình luận" in md_text

    tg_html = render_telegram_html(post, summary)
    assert "&lt;template&gt; &amp; tricks" in tg_html
    assert "<b>🛠️ Bối cảnh &amp; Vấn đề:</b>" in tg_html
    assert "• Chưa có bình luận" in tg_html
    assert "⚠️ Lưu ý" not in tg_html


def test_parse_bot_command():
    assert parse_bot_command("hello world") is None
    assert parse_bot_command("/help") == BotCommand(kind="help")
    assert parse_bot_command("/start@MyDigestBot") == BotCommand(kind="help")

    assert parse_bot_command("/defaults") == BotCommand(kind="defaults", limit=None)
    assert parse_bot_command("/defaults 3") == BotCommand(kind="defaults", limit=3)

    assert parse_bot_command("/news") == BotCommand(kind="subreddit", subreddit="news", limit=None)
    assert parse_bot_command("/news 5") == BotCommand(kind="subreddit", subreddit="news", limit=5)
    assert parse_bot_command("/robotics") == BotCommand(kind="subreddit", subreddit="robotics", limit=None)
    assert parse_bot_command("/AskRobotics@MyBot 4") == BotCommand(kind="subreddit", subreddit="AskRobotics", limit=4)

    assert parse_bot_command("/sum 2") == BotCommand(kind="sum", indices=[2])
    assert parse_bot_command("/sum 1 3 1") == BotCommand(kind="sum", indices=[1, 3])
    assert parse_bot_command("/sum").kind == "invalid"
    assert parse_bot_command("/sum 0").kind == "invalid"
    assert parse_bot_command("/sum abc").kind == "invalid"

    assert parse_bot_command("/defaults quick").kind == "invalid"
    assert parse_bot_command("/python quick 10").kind == "invalid"
    assert parse_bot_command("/defaults 999").kind == "invalid"
    assert parse_bot_command("/invalid-sub-name!").kind == "invalid"


def test_filter_posts_skip_processed_and_custom_limit(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    cfg = CollectionConfig(limit_per_subreddit=5, max_age_days=7, min_selftext_chars=80, min_comments=2)

    p1 = make_post(id="p1", hot_score=90.0)
    p2 = make_post(id="p2", hot_score=80.0)
    summary = DigestSummary(
        relevance_score=2,
        post_type="discussion",
        summary="Test summary",
        comment_insights=[],
        study_topics=[],
        notes=[],
    )
    storage.save_post(p1, status="DELIVERED", summary=summary)

    # Default mode skips already processed p1
    assert [p.id for p in filter_posts([p1, p2], cfg, storage, now_ts=NOW_TS)] == ["p2"]
    # Custom subreddit mode includes p1 and respects custom limit=1
    assert [p.id for p in filter_posts([p1, p2], cfg, storage, now_ts=NOW_TS, skip_processed=False, limit=1)] == ["p1"]
    assert storage.get_summary("p1") == summary
    assert storage.get_summary("p2") is None
    storage.close()


def test_render_quick_list_html():
    p1 = make_post(id="p1", hot_score=88.4)
    p1.title = "ROS2 & <Nav2> Guide"
    html_out = render_quick_list_html("robotics", [p1], max_age_days=7)
    assert "<b>🔥 Top bài viết r/robotics (7 ngày qua):</b>" in html_out
    assert '1. <a href="https://www.reddit.com/r/Embedded/comments/p1">ROS2 &amp; &lt;Nav2&gt; Guide</a> (🔥 88)' in html_out

    empty_out = render_quick_list_html("robotics", [], max_age_days=7)
    assert "Không tìm thấy bài viết phù hợp." in empty_out


def test_pipeline_backfills_limit_and_retries_summarized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import src.main as main_mod
    from src.schemas import Comment

    p_no_comments = make_post(id="p_no_com", hot_score=95.0, created_utc=0.0)
    p_cached = make_post(id="p_cached", hot_score=85.0, created_utc=0.0)
    p_fresh = make_post(id="p_fresh", hot_score=75.0, created_utc=0.0)

    cached_sum = DigestSummary(
        relevance_score=4,
        post_type="problem",
        summary="Cached summary",
        comment_insights=["Fix A"],
        study_topics=[],
        notes=[],
    )
    db_path = tmp_path / "test.db"
    st = Storage(db_path)
    st.save_post(p_cached, status="SUMMARIZED", summary=cached_sum)
    st.close()

    for k in ("GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(k, "test_secret_val")
    cfg = load_config(env_path=tmp_path / "no.env")
    cfg.storage.db_path = db_path
    cfg.storage.digest_dir = tmp_path / "digests"
    cfg.collection.limit_per_subreddit = 2

    summarize_calls = []
    sent_msgs = []

    monkeypatch.setattr(main_mod, "load_config", lambda: cfg)
    monkeypatch.setattr(main_mod.Summarizer, "__init__", lambda self, c: None)
    monkeypatch.setattr(main_mod.RedditClient, "fetch_hot_posts", lambda self, sub, c: [p_no_comments, p_cached, p_fresh])
    monkeypatch.setattr(
        main_mod,
        "fetch_and_select_comments",
        lambda client, pid, c: [] if pid == "p_no_com" else [Comment(id="c1", author="u", body="x" * 30)] * 2,
    )
    monkeypatch.setattr(
        main_mod.Summarizer,
        "summarize",
        lambda self, post, comments: (summarize_calls.append(post.id) or cached_sum),
    )
    monkeypatch.setattr(main_mod, "send_telegram_message", lambda creds, html_text: sent_msgs.append(html_text))

    count, failed = main_mod.run_pipeline(subreddits=["robotics"], limit=2)
    assert count == 2
    assert not failed
    assert summarize_calls == ["p_fresh"]  # p_cached reused SQLite summary without calling Gemini

    st = Storage(db_path)
    assert not st.is_processed("p_no_com")  # remains COLLECTED, not SKIPPED
    assert st.is_processed("p_cached")
    assert st.is_processed("p_fresh")
    st.close()


def test_rss_link_post_with_short_caption_and_scheduled_bot_loop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import src.main as main_mod

    xml_str = """<feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>t3_abc123</id>
        <title>New robot arm demo</title>
        <link href="https://www.reddit.com/r/robotics/comments/abc123/new_robot_arm_demo/" />
        <published>2023-11-14T22:00:00+00:00</published>
        <content type="html">&lt;!-- SC_OFF --&gt;&lt;div class="md"&gt;&lt;p&gt;Short caption&lt;/p&gt;&lt;/div&gt;&lt;!-- SC_ON --&gt; &amp;#32; &lt;span&gt;&lt;a href="https://i.redd.it/demo.mp4"&gt;[link]&lt;/a&gt;&lt;/span&gt;</content>
      </entry>
    </feed>"""
    posts = _parse_rss_entries(ET.fromstring(xml_str), "robotics")
    assert len(posts) == 1
    assert posts[0].is_self is False
    assert posts[0].selftext == "Short caption"

    cfg = CollectionConfig(limit_per_subreddit=5, max_age_days=7, min_selftext_chars=80, min_comments=2)
    assert [p.id for p in filter_posts(posts, cfg, storage=None, now_ts=NOW_TS)] == ["abc123"]

    for k in ("GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(k, "test_secret_val")
    app_cfg = load_config(env_path=tmp_path / "no.env")
    monkeypatch.setattr(main_mod, "load_config", lambda: app_cfg)

    ticks = iter([0.0, 3601.0])
    monkeypatch.setattr(main_mod.time, "monotonic", lambda: next(ticks, 3602.0))
    runs = []
    monkeypatch.setattr(main_mod, "run_pipeline", lambda: runs.append(1) or (0, []))

    calls = 0

    def fake_updates(creds, offset=None, timeout=30):
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        raise KeyboardInterrupt

    monkeypatch.setattr(main_mod, "fetch_telegram_updates", fake_updates)
    main_mod.run_bot_loop(schedule_interval_hours=1)
    assert len(runs) == 1


def test_fetch_and_select_comments_rss_parsing():
    from src.comments import fetch_and_select_comments
    from src.config import CommentsConfig

    comment_xml = """<feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>t3_post1</id>
        <author><name>/u/op_user</name></author>
        <content type="html">&lt;div class="md"&gt;&lt;p&gt;Post body that must be skipped as entry[0]&lt;/p&gt;&lt;/div&gt;</content>
      </entry>
      <entry>
        <id>t1_c_automod</id>
        <author><name>/u/AutoModerator</name></author>
        <content type="html">&lt;div class="md"&gt;&lt;p&gt;Automated moderation message long enough.&lt;/p&gt;&lt;/div&gt;</content>
      </entry>
      <entry>
        <id>t1_c_short</id>
        <author><name>/u/dev1</name></author>
        <content type="html">&lt;div class="md"&gt;&lt;p&gt;Too short&lt;/p&gt;&lt;/div&gt;</content>
      </entry>
      <entry>
        <id>t1_c_valid1</id>
        <author><name>/u/dev2</name></author>
        <content type="html">&lt;div class="md"&gt;&lt;p&gt;Check your clock tree and DMA stream priority settings.&lt;/p&gt;&lt;/div&gt;</content>
      </entry>
      <entry>
        <id>t1_c_valid2</id>
        <author><name>/u/dev3</name></author>
        <content type="html">&lt;div class="md"&gt;&lt;p&gt;Enable UART idle line interrupt to flush the ring buffer.&lt;/p&gt;&lt;/div&gt;</content>
      </entry>
    </feed>"""

    class DummyClient:
        def get_rss(self, url: str, params: dict) -> ET.Element:
            return ET.fromstring(comment_xml)

    cfg = CommentsConfig(max_comments=1, min_comment_length=20, max_total_chars=6000)
    selected = fetch_and_select_comments(DummyClient(), "post1", cfg)
    assert len(selected) == 1
    assert selected[0].id == "c_valid1"
    assert selected[0].author == "dev2"
    assert "DMA stream priority" in selected[0].body
