from src.collector import ATOM_NS, RedditClient, extract_md_text
from src.config import CommentsConfig
from src.schemas import Comment

IGNORED_BODIES = {"[deleted]", "[removed]"}


def _valid_body(body: str, min_len: int) -> bool:
    cleaned = body.strip()
    return len(cleaned) >= min_len and cleaned.lower() not in IGNORED_BODIES


def fetch_and_select_comments(client: RedditClient, post_id: str, cfg: CommentsConfig) -> list[Comment]:
    root = client.get_rss(
        f"https://www.reddit.com/comments/{post_id}/.rss",
        params={"limit": 50},
    )
    entries = root.findall("a:entry", ATOM_NS)
    comments: list[Comment] = []

    # Skip entries[0] which is the post itself (t3_...)
    for entry in entries[1:]:
        raw_id = entry.findtext("a:id", default="", namespaces=ATOM_NS)
        if not raw_id.startswith("t1_"):
            continue
        author_el = entry.find("a:author/a:name", ATOM_NS)
        author = (author_el.text or "unknown").removeprefix("/u/") if author_el is not None else "unknown"
        content_html = entry.findtext("a:content", default="", namespaces=ATOM_NS)
        body = extract_md_text(content_html)
        if author == "AutoModerator" or not _valid_body(body, cfg.min_comment_length):
            continue
        comments.append(
            Comment(
                id=raw_id.removeprefix("t1_"),
                author=author,
                body=body,
            )
        )

    selected: list[Comment] = []
    used_chars = 0
    for c in comments[: cfg.max_comments]:
        if used_chars + len(c.body) > cfg.max_total_chars:
            break
        used_chars += len(c.body)
        selected.append(c)
    return selected
