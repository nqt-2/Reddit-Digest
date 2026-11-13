import sqlite3
from pathlib import Path
from src.schemas import DigestSummary, Post


class Storage:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # shortcut: single sqlite connection per run, move to connection pool only if multi-threaded
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                permalink TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def is_processed(self, post_id: str) -> bool:
        row = self.conn.execute(
            "SELECT status FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        return row is not None and row["status"] in ("DELIVERED", "SKIPPED")

    def is_delivered(self, post_id: str) -> bool:
        row = self.conn.execute(
            "SELECT status FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        return row is not None and row["status"] == "DELIVERED"

    def get_summary(self, post_id: str) -> DigestSummary | None:
        row = self.conn.execute(
            "SELECT summary_json FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        if row and row["summary_json"]:
            return DigestSummary.model_validate_json(row["summary_json"])
        return None

    def save_post(self, post: Post, status: str = "COLLECTED", summary: DigestSummary | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO posts (id, subreddit, title, permalink, status, summary_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                summary_json = COALESCE(excluded.summary_json, posts.summary_json),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                post.id,
                post.subreddit,
                post.title,
                post.permalink,
                status,
                summary.model_dump_json() if summary else None,
            ),
        )
        self.conn.commit()

    def mark_status(self, post_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE posts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, post_id),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
