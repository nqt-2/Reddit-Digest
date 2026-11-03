from src.config import CollectionConfig
from src.schemas import Post
from src.storage import Storage


def filter_posts(posts: list[Post], cfg: CollectionConfig, storage: Storage) -> list[Post]:
    accepted = []
    seen = set()
    for p in posts:
        if p.id in seen or p.stickied or storage.is_processed(p.id):
            continue
        seen.add(p.id)
        if p.is_self and len(p.selftext.strip()) < cfg.min_selftext_chars:
            continue
        if not p.is_self and 0 <= p.num_comments < cfg.min_comments_for_link_post:
            continue
        accepted.append(p)
    return accepted
