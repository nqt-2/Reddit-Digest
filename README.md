# Reddit AI Digest

Ứng dụng Python tự động theo dõi các subreddit kỹ thuật, chọn lọc bài đăng và thảo luận đáng chú ý, phân tích và tóm tắt có cấu trúc bằng Google Gemini (`gemini-2.5-flash`), lưu trữ trạng thái bằng SQLite, xuất bản tin Markdown hằng ngày và gửi thông báo qua Telegram.

## Kiến trúc tổng quan

```text
Schedule / CLI (--once | --schedule)
        |
        v
Reddit OAuth Collector (httpx -> /r/{sub}/new)
        |
        v
Filter & Deduplicate (filters.py + SQLite state)
        |
        v
2-Level Comment Selector (comments.py: Top-N depth 0 + replies depth 1)
        |
        v
LLM Summarizer (Gemini 2.5 Flash + Pydantic Structured Output)
        |
        +------> SQLite (COLLECTED -> SUMMARIZED -> DELIVERED)
        +------> Markdown Archive (digests/YYYY-MM-DD.md)
        +------> Telegram Bot (HTML mode)
```

## Cài đặt môi trường

1. Tạo và kích hoạt virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Cài đặt dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
3. Sao chép `.env.example` thành `.env` và điền các API keys:
   ```powershell
   Copy-Item .env.example .env
   ```
4. Chạy chương trình:
   - Chạy một lần rồi thoát: `python -m src.main --once`
   - Chạy lắng nghe lệnh Telegram Bot: `python -m src.main --bot`
   - Chạy định kỳ theo lịch kèm lắng nghe lệnh Telegram Bot: `python -m src.main --schedule`

## Lệnh Telegram Bot

- `/defaults [N]` — Xem danh sách tiêu đề + link các bài hot nhất (7 ngày qua) từ các subreddit mặc định trong `config.yaml`.
- `/<subreddit> [N]` — Xem danh sách tiêu đề + link các bài hot nhất (7 ngày qua) của `r/<subreddit>` bất kỳ (ví dụ: `/python`, `/news 5`, `/robotics 10`).
- `/sum <số> [số...]` — Tóm tắt AI bài viết cụ thể theo số thứ tự từ danh sách vừa lấy gần nhất (ví dụ: `/sum 2` hoặc `/sum 1 3`).
- `/help` — Hiển thị hướng dẫn sử dụng.


