from datetime import datetime
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
import httpx
from src.config import CollectionConfig, CredentialsConfig
from src.schemas import Post

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
log = logging.getLogger("digest")


def extract_md_text(raw_html: str) -> str:
    """Extract plain text from Reddit's <div class="md"> HTML block."""
    m = re.search(r'<div class="md">(.*?)</div>', raw_html, re.DOTALL)
    chunk = m.group(1) if m else raw_html
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", chunk)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _parse_rss_entries(root: ET.Element, subreddit: str) -> list[Post]:
    posts = []
    for entry in root.findall("a:entry", ATOM_NS):
        raw_id = entry.findtext("a:id", default="", namespaces=ATOM_NS)
        post_id = raw_id.removeprefix("t3_")
        if not post_id:
            continue

        title = html.unescape(entry.findtext("a:title", default="", namespaces=ATOM_NS))
        link_el = entry.find("a:link", ATOM_NS)
        raw_link = link_el.attrib.get("href", "") if link_el is not None else ""
        permalink = raw_link if raw_link.startswith("https://www.reddit.com/") else f"https://www.reddit.com/comments/{post_id}"
        content_html = entry.findtext("a:content", default="", namespaces=ATOM_NS)
        selftext = extract_md_text(content_html) if '<div class="md">' in content_html else ""

        ext_match = re.search(r'<a href="([^"]+)">\[link\]</a>', content_html)
        ext_url = html.unescape(ext_match.group(1)) if ext_match else permalink
        is_self = ext_url == permalink

        published_str = (
            entry.findtext("a:published", default="", namespaces=ATOM_NS)
            or entry.findtext("a:updated", default="", namespaces=ATOM_NS)
        )
        created_utc = datetime.fromisoformat(published_str).timestamp() if published_str else 0.0

        posts.append(
            Post(
                id=post_id,
                subreddit=subreddit,
                title=title,
                selftext=selftext,
                url=ext_url,
                permalink=permalink,
                created_utc=created_utc,
                score=1,
                hot_score=0.0,
                num_comments=-1,
                is_self=is_self,
            )
        )
    return posts


def merge_and_score_posts(top_posts: list[Post], comment_posts: list[Post], pool_size: int) -> list[Post]:
    """Combine posts from Top Upvotes and Most Comments feeds into a single hot-scored list."""
    n = max(pool_size, len(top_posts), len(comment_posts), 1)
    by_id: dict[str, Post] = {}
    upvote_norm: dict[str, float] = {}
    comment_norm: dict[str, float] = {}

    for idx, p in enumerate(top_posts):
        by_id[p.id] = p
        upvote_norm[p.id] = max(0.0, (n - idx) / n)

    for idx, p in enumerate(comment_posts):
        if p.id not in by_id:
            by_id[p.id] = p
        comment_norm[p.id] = max(0.0, (n - idx) / n)

    merged: list[Post] = []
    for post_id, post in by_id.items():
        hot = 60.0 * upvote_norm.get(post_id, 0.0) + 40.0 * comment_norm.get(post_id, 0.0)
        post.hot_score = round(hot, 2)
        post.score = max(1, int(round(hot)))
        merged.append(post)

    merged.sort(key=lambda p: (p.hot_score, p.created_utc), reverse=True)
    return merged


class RedditClient:
    def __init__(self, creds: CredentialsConfig):
        self.http = httpx.Client(
            headers={"User-Agent": creds.reddit_user_agent},
            follow_redirects=True,
            timeout=15.0,
        )

    def get_rss(self, url: str, params: dict) -> ET.Element:
        for attempt in range(3):
            time.sleep(2.5)
            resp = self.http.get(url, params=params)
            if resp.status_code == 429 and attempt < 2:
                wait = int(resp.headers.get("Retry-After", 6 * (attempt + 1)))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return ET.fromstring(resp.text)
        raise RuntimeError(f"Rate limited on {url}")

    def fetch_hot_posts(self, subreddit: str, cfg: CollectionConfig) -> list[Post]:
        top_posts: list[Post] = []
        comment_posts: list[Post] = []

        try:
            top_root = self.get_rss(
                f"https://www.reddit.com/r/{subreddit}/top/.rss",
                params={"t": cfg.time_filter, "limit": cfg.fetch_pool_size},
            )
            top_posts = _parse_rss_entries(top_root, subreddit)
        except Exception as exc:
            log.warning("Failed fetching top RSS for r/%s: %s", subreddit, exc)

        try:
            comment_root = self.get_rss(
                f"https://www.reddit.com/r/{subreddit}/search.rss",
                params={
                    "q": "self:yes OR self:no",
                    "restrict_sr": "on",
                    "sort": "comments",
                    "t": cfg.time_filter,
                    "limit": cfg.fetch_pool_size,
                },
            )
            comment_posts = _parse_rss_entries(comment_root, subreddit)
        except Exception as exc:
            log.warning("Failed fetching comments RSS for r/%s: %s", subreddit, exc)

        if not top_posts and not comment_posts:
            raise RuntimeError(f"Could not fetch any RSS feed for r/{subreddit}")

        return merge_and_score_posts(top_posts, comment_posts, cfg.fetch_pool_size)

    def close(self) -> None:
        self.http.close()
