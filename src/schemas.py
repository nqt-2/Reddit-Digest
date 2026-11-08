from typing import Literal
from pydantic import BaseModel, Field


class Comment(BaseModel):
    id: str
    author: str
    body: str


class Post(BaseModel):
    id: str
    subreddit: str
    title: str
    selftext: str
    url: str
    permalink: str
    created_utc: float
    score: int
    hot_score: float = 0.0
    num_comments: int
    is_self: bool


class DigestSummary(BaseModel):
    relevance_score: int = Field(ge=1, le=5, description="1 (irrelevant) to 5 (highly relevant to reader profile)")
    post_type: Literal["problem", "discussion"] = Field(
        description="'problem' for bugs/questions/troubleshooting; 'discussion' for sharing, news, showcases, or general discussions"
    )
    summary: str = Field(
        description="1.1: For 'problem': context, issue faced, and what OP already tried. For 'discussion': context and main topic."
    )
    comment_insights: list[str] = Field(
        description="1.2: Up to 5 concise approaches/solutions (for 'problem') or key perspectives (for 'discussion') from comments, without usernames, merging duplicates. Empty list [] if no comments."
    )
    study_topics: list[str] = Field(
        description="1.3: Up to 3 topics to research in format 'Keyword/Tech — 1-sentence explanation'. Empty list [] if nothing notable to study."
    )
    notes: list[str] = Field(
        description="1.4: Critical caveats, debates, or unverified claims. Empty list [] if none."
    )
