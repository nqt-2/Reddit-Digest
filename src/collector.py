from datetime import datetime
import html
import re
import time
import xml.etree.ElementTree as ET
import httpx
from src.config import CredentialsConfig
from src.schemas import Post

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def extract_md_text(raw_html: str) -> str:
    """Extract plain text from Reddit's <div class="md"> HTML block."""
    m = re.search(r'<div class="md">(.*?)</div>\s*(?:<!-- SC_ON -->|$)', raw_html, re.DOTALL)
    chunk = m.group(1) if m else raw_html
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", chunk)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


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

    def fetch_new_posts(self, subreddit: str, limit: int) -> list[Post]:
        root = self.get_rss(
            f"https://www.reddit.com/r/{subreddit}/new/.rss",
            params={"limit": limit},
        )
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
            is_self = (ext_url == permalink) or bool(selftext)

            updated_str = entry.findtext("a:updated", default="", namespaces=ATOM_NS)
            created_utc = datetime.fromisoformat(updated_str).timestamp() if updated_str else 0.0

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
                    num_comments=-1,
                    is_self=is_self,
                    stickied=False,
                )
            )
        return posts

    def close(self) -> None:
        self.http.close()
