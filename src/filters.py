import time
from src.config import CollectionConfig
from src.schemas import Post
from src.storage import Storage


def filter_posts(
    posts: list[Post],
    cfg: CollectionConfig,
    storage: Storage,
    now_ts: float | None = None,
) -> list[Post]:
    now = now_ts if now_ts is not None else time.time()
    cutoff_utc = now - (cfg.max_age_days * 86400)

    accepted = []
    seen = set()
    for p in posts:
        if p.id in seen or p.stickied or storage.is_processed(p.id):
            continue
        seen.add(p.id)
        if p.created_utc > 0 and p.created_utc < cutoff_utc:
            continue
        if p.is_self and len(p.selftext.strip()) < cfg.min_selftext_chars:
            continue
        if 0 <= p.num_comments < cfg.min_comments:
            continue
        accepted.append(p)

    accepted.sort(key=lambda p: (p.hot_score, p.created_utc), reverse=True)
    return accepted
