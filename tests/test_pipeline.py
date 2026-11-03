from pathlib import Path
import pytest
from src.collector import extract_md_text
from src.config import CollectionConfig, CredentialsConfig, load_config
from src.digest import render_telegram_html, save_markdown_digest
from src.filters import filter_posts
from src.schemas import DigestSummary, Post
from src.storage import Storage


def make_post(id: str = "p1", is_self: bool = True, selftext: str = "x" * 100, num_comments: int = 5, stickied: bool = False) -> Post:
    return Post(
        id=id,
        subreddit="Embedded",
        title="DMA UART Ring Buffer on STM32",
        selftext=selftext,
        url="https://reddit.com/r/Embedded/p1",
        permalink="https://www.reddit.com/r/Embedded/comments/p1",
        created_utc=1700000000.0,
        score=25,
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
    cfg = CollectionConfig(limit_per_subreddit=10, min_selftext_chars=80, min_comments_for_link_post=3)

    good = make_post(id="good")
    short_self = make_post(id="short", selftext="too short")
    quiet_link = make_post(id="link", is_self=False, selftext="", num_comments=1)
    sticky = make_post(id="sticky", stickied=True)

    res = filter_posts([good, short_self, quiet_link, sticky], cfg, storage)
    assert [p.id for p in res] == ["good"]

    # Once marked SUMMARIZED, it must be skipped on next run
    storage.save_post(good, status="SUMMARIZED")
    assert filter_posts([good], cfg, storage) == []
    storage.close()


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
