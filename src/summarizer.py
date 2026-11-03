from google import genai
from google.genai import types
from src.config import AppConfig, PROJECT_ROOT
from src.schemas import Comment, DigestSummary, Post

PROMPT_PATH = PROJECT_ROOT / "prompts" / "digest.md"


def format_untrusted_payload(post: Post, comments: list[Comment]) -> str:
    lines = [
        "<untrusted_reddit_data>",
        f"Subreddit: r/{post.subreddit}",
        f"Title: {post.title}",
        f"URL: {post.url}",
        f"Score: {post.score} | Comments: {post.num_comments}",
        f"Body:\n{post.selftext or '(Link post - no body text)'}",
        "\nSelected Comments:",
    ]
    if not comments:
        lines.append("(No qualifying comments)")
    for c in comments:
        lines.append(f"- [score={c.score}] u/{c.author}: {c.body}")
        for r in c.replies:
            lines.append(f"  - [reply score={r.score}] u/{r.author}: {r.body}")
    lines.append("</untrusted_reddit_data>")
    return "\n".join(lines)


class Summarizer:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.client = genai.Client(api_key=cfg.credentials.gemini_api_key)
        self.system_template = PROMPT_PATH.read_text(encoding="utf-8")

    def summarize(self, post: Post, comments: list[Comment]) -> DigestSummary:
        system_instruction = self.system_template.format(reader_profile=self.cfg.reader_profile)
        content = format_untrusted_payload(post, comments)
        resp = self.client.models.generate_content(
            model=self.cfg.llm.model_name,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=DigestSummary,
                temperature=0.2,
            ),
        )
        return DigestSummary.model_validate_json(resp.text)
