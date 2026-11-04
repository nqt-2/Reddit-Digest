import os
from pathlib import Path
from typing import Literal
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) reddit-ai-digest/0.1"


class CollectionConfig(BaseModel):
    limit_per_subreddit: int = Field(default=5, gt=0, le=100)
    fetch_pool_size: int = Field(default=10, gt=0, le=100)
    time_filter: Literal["hour", "day", "week", "month", "year", "all"] = "week"
    max_age_days: int = Field(default=7, gt=0)
    min_selftext_chars: int = Field(default=80, ge=0)
    min_comments: int = Field(default=2, ge=0)


class CommentsConfig(BaseModel):
    max_top_level: int = Field(gt=0)
    max_replies_per_comment: int = Field(ge=0)
    min_comment_length: int = Field(ge=0)
    max_total_chars: int = Field(gt=0)


class LLMConfig(BaseModel):
    model_name: str = Field(min_length=1)
    min_relevance_score: int = Field(ge=1, le=5)


class ScheduleConfig(BaseModel):
    interval_hours: float = Field(gt=0)


class StorageConfig(BaseModel):
    db_path: Path
    digest_dir: Path

    @field_validator("db_path", "digest_dir", mode="after")
    @classmethod
    def resolve_path(cls, v: Path) -> Path:
        return v if v.is_absolute() else PROJECT_ROOT / v


class CredentialsConfig(BaseModel):
    gemini_api_key: str = Field(repr=False)
    telegram_bot_token: str = Field(repr=False)
    telegram_chat_id: str = Field(repr=False)
    reddit_user_agent: str = DEFAULT_USER_AGENT

    @field_validator("gemini_api_key", "telegram_bot_token", "telegram_chat_id")
    @classmethod
    def check_secret(cls, v: str, info) -> str:
        v = v.strip()
        if not v or "your_" in v.lower():
            raise ValueError(f"Missing or placeholder secret: {info.field_name.upper()}")
        return v


class AppConfig(BaseModel):
    subreddits: list[str] = Field(min_length=1)
    collection: CollectionConfig
    comments: CommentsConfig
    llm: LLMConfig
    reader_profile: str = Field(min_length=1)
    schedule: ScheduleConfig
    storage: StorageConfig
    credentials: CredentialsConfig

    @field_validator("subreddits")
    @classmethod
    def clean_subs(cls, subs: list[str]) -> list[str]:
        return [s.strip().removeprefix("/r/").removeprefix("r/").strip("/") for s in subs if s.strip()]


def load_config(
    config_path: Path = PROJECT_ROOT / "config.yaml",
    env_path: Path = PROJECT_ROOT / ".env",
) -> AppConfig:
    load_dotenv(env_path, override=False)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    creds = CredentialsConfig(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        reddit_user_agent=os.getenv("REDDIT_USER_AGENT", DEFAULT_USER_AGENT),
    )
    return AppConfig(**raw, credentials=creds)
