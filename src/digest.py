from datetime import date
import html
from pathlib import Path
from src.schemas import DigestSummary, Post


def render_markdown_item(post: Post, s: DigestSummary) -> str:
    is_prob = s.post_type == "problem"
    tag = "🛠️ Vấn đề" if is_prob else "📢 Thảo luận"
    h_sum = "Vấn đề & Đã thử" if is_prob else "Bối cảnh & Chủ đề"
    h_com = "Hướng giải quyết (Comments)" if is_prob else "Ý kiến nổi bật (Comments)"

    comments_md = "\n".join(f"- {c}" for c in s.comment_insights) if s.comment_insights else "- Chưa có bình luận"
    safe_title = post.title.replace("[", r"\[").replace("]", r"\]")
    lines = [
        f"## [{safe_title}]({post.permalink}) (r/{post.subreddit} | {tag} | ⭐ {s.relevance_score}/5)",
        f"**1.1 {h_sum}:** {s.summary}",
        f"**1.2 {h_com}:**\n{comments_md}",
    ]
    if s.study_topics:
        topics_md = "\n".join(f"- {t}" for t in s.study_topics)
        lines.append(f"**1.3 Bài học / Cần nghiên cứu:**\n{topics_md}")
    if s.notes:
        notes_md = "\n".join(f"- {n}" for n in s.notes)
        lines.append(f"**1.4 Lưu ý:**\n{notes_md}")
    lines.append("---\n")
    return "\n\n".join(lines)


def save_markdown_digest(items: list[tuple[Post, DigestSummary]], digest_dir: Path, run_date: date | None = None) -> Path:
    digest_dir.mkdir(parents=True, exist_ok=True)
    d = run_date or date.today()
    file_path = digest_dir / f"{d.isoformat()}.md"
    header = f"# Reddit AI Digest — {d.isoformat()}\n\n" if not file_path.exists() else ""
    body = "\n".join(render_markdown_item(p, s) for p, s in items)
    with file_path.open("a", encoding="utf-8") as f:
        f.write(header + body + "\n")
    return file_path


def render_telegram_html(post: Post, s: DigestSummary) -> str:
    esc = html.escape
    is_prob = s.post_type == "problem"
    tag = "🛠️ Vấn đề" if is_prob else "📢 Thảo luận"
    h_sum = "🛠️ Bối cảnh &amp; Vấn đề" if is_prob else "📢 Bối cảnh &amp; Chủ đề"
    h_com = "💬 Hướng giải quyết (Comments)" if is_prob else "💬 Ý kiến thảo luận (Comments)"

    comments_html = "\n".join(f"• {esc(i)}" for i in s.comment_insights[:5]) if s.comment_insights else "• Chưa có bình luận"
    parts = [
        f"<b>[r/{esc(post.subreddit)} | {tag}] <a href=\"{esc(post.permalink)}\">{esc(post.title)}</a></b> (⭐ {s.relevance_score}/5)",
        f"<b>{h_sum}:</b> {esc(s.summary)}",
        f"<b>{h_com}:</b>\n{comments_html}",
    ]
    if s.study_topics:
        topics_html = "\n".join(f"• {esc(i)}" for i in s.study_topics[:3])
        parts.append(f"<b>📚 Cần nghiên cứu:</b>\n{topics_html}")
    if s.notes:
        notes_html = "\n".join(f"• {esc(i)}" for i in s.notes[:3])
        parts.append(f"<b>⚠️ Lưu ý:</b>\n{notes_html}")
    return "\n\n".join(parts)


def render_quick_list_html(
    subreddit: str,
    posts: list[Post],
    max_age_days: int = 7,
    start_index: int = 1,
) -> str:
    esc = html.escape
    header = f"<b>🔥 Top bài viết r/{esc(subreddit)} ({max_age_days} ngày qua):</b>"
    if not posts:
        return f"{header}\n\nKhông tìm thấy bài viết phù hợp."
    lines = [header, ""]
    for idx, p in enumerate(posts, start=start_index):
        lines.append(f'{idx}. <a href="{esc(p.permalink)}">{esc(p.title)}</a> (🔥 {p.hot_score:.0f})')
    return "\n".join(lines)
