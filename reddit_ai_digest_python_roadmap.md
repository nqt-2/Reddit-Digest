# Reddit AI Digest --- Python Project Roadmap

> Mục tiêu: xây dựng một ứng dụng Python cá nhân tự theo dõi các
> subreddit, thu thập bài đăng và bình luận, dùng LLM tạo bản tóm tắt có
> ích cho việc học, rồi gửi bản tin đến Telegram và lưu thành Markdown.
>
> Nguyên tắc học: **tự thiết kế và hiểu từng phần; dùng AI như
> mentor/code reviewer, không giao toàn bộ project cho AI tạo một lần.**

------------------------------------------------------------------------

## 1. Kết quả cuối cùng

Mỗi ngày, hệ thống sẽ:

1.  Kiểm tra các subreddit trong danh sách cấu hình.
2.  Tìm bài đăng mới kể từ lần chạy trước.
3.  Loại bài đã xử lý hoặc không phù hợp.
4.  Thu thập một lượng bình luận có chọn lọc.
5.  Gửi nội dung đã chuẩn hóa đến mô hình AI.
6.  Nhận bản phân tích có cấu trúc, kiểm tra và lưu kết quả.
7.  Gửi bản tin đến Telegram và lưu bản Markdown để đọc lại.

### Nội dung bản tin cho mỗi bài

-   **Bài đăng nói về gì?** Tóm tắt vấn đề chính.
-   **Liên quan đến mình thế nào?** Kết nối với mục tiêu học tập/dự án
    đã cấu hình.
-   **Có thể học được gì từ bình luận?** Kinh nghiệm, giải pháp, quan
    điểm trái chiều.
-   **Có thể làm gì tiếp theo?** Một hành động nhỏ, thực tế.
-   **Nguồn:** link bài đăng Reddit.

Hệ thống phải nói rõ khi nguồn không đủ dữ liệu; không tự bịa nội dung
hoặc xem ý kiến bình luận là sự thật đã được xác minh.

------------------------------------------------------------------------

## 2. Phạm vi MVP

Giữ phiên bản đầu tiên nhỏ để hoàn thành được.

### Có trong MVP

-   Một hoặc hai subreddit.
-   Chạy thủ công trước; sau đó mới thêm lịch chạy.
-   Lấy bài đăng mới qua Reddit API.
-   Lấy bình luận và giới hạn số lượng.
-   Tóm tắt bằng một LLM API.
-   Lưu ID bài đã xử lý bằng SQLite.
-   Gửi bản tin Telegram.
-   Lưu bản tin Markdown.
-   Có logging, xử lý lỗi cơ bản và một số test.

### Chưa cần làm ban đầu

-   Web UI hoặc mobile app.
-   Vector database / RAG.
-   Fine-tuning.
-   Multi-agent architecture.
-   Dashboard phức tạp.
-   Chạy trên cloud ngay từ ngày đầu.

------------------------------------------------------------------------

## 3. Kiến trúc tổng thể

``` text
Schedule / Manual Run
        |
        v
Reddit Collector
        |
        v
Normalize + Filter + Deduplicate
        |
        v
Comment Collector / Selector
        |
        v
LLM Summarizer
        |
        v
Validate Structured Output
        |
        +------> SQLite (processed posts, results)
        |
        +------> Markdown Archive
        |
        +------> Telegram Bot
```

### Vai trò của từng module

  Module            Trách nhiệm
  ----------------- --------------------------------------------
  `collector.py`    Lấy bài đăng từ Reddit
  `comments.py`     Lấy và chọn bình luận
  `filters.py`      Lọc bài, giới hạn số lượng, loại bài trùng
  `schemas.py`      Định nghĩa cấu trúc dữ liệu
  `summarizer.py`   Gọi LLM và xử lý phản hồi
  `storage.py`      Lưu trạng thái và kết quả trong SQLite
  `telegram.py`     Gửi bản tin
  `digest.py`       Render bản tin Markdown
  `config.py`       Đọc cấu hình và biến môi trường
  `main.py`         Điều phối pipeline

Không cần tạo tất cả file ngay từ đầu. Chỉ thêm module khi có nhu cầu rõ
ràng.

------------------------------------------------------------------------

## 4. Công nghệ đề xuất

Bắt đầu bằng công cụ đơn giản, quen thuộc:

-   **Python:** ngôn ngữ chính.
-   **Reddit API:** lấy bài đăng và bình luận. Có thể dùng `PRAW` hoặc
    `requests`; chọn một cách và đọc tài liệu chính thức.
-   **Pydantic:** kiểm tra cấu trúc dữ liệu đầu vào/đầu ra.
-   **SQLite:** lưu bài đã xử lý và bản tóm tắt.
-   **Gemini API hoặc LLM API khác:** tạo bản phân tích.
-   **Telegram Bot API:** gửi bản tin.
-   **pytest:** kiểm thử.
-   **APScheduler hoặc cron:** lập lịch sau khi pipeline chạy thủ công
    ổn định.
-   **Docker:** tùy chọn ở giai đoạn triển khai.

Không commit API key, bot token, client secret hoặc file `.env` lên
GitHub.

------------------------------------------------------------------------

## 5. Lộ trình theo milestone

### Milestone 0 --- Thiết lập project

**Mục tiêu:** có môi trường Python sạch và repository dễ hiểu.

Việc cần làm:

-   Tạo Git repository.
-   Tạo virtual environment.
-   Thêm `.gitignore`.
-   Tạo `requirements.txt` hoặc dùng công cụ quản lý dependency mà bạn
    đã quen.
-   Tạo `.env.example` chỉ chứa tên biến, không chứa secret.
-   Viết README ngắn mô tả mục tiêu project.

**Hoàn thành khi:**

-   Có thể cài dependencies từ đầu.
-   Project chạy được một file Python đơn giản.
-   Secret không bị đưa vào Git.

### Milestone 1 --- Reddit Collector

**Mục tiêu:** lấy bài đăng từ một subreddit và chuẩn hóa thành dữ liệu
Python.

Việc cần làm:

-   Tạo cấu hình subreddit.
-   Xác thực với Reddit API theo hướng dẫn hiện hành.
-   Lấy bài mới.
-   Chuẩn hóa các trường cần thiết: ID, subreddit, title, body, URL,
    thời gian, score và số comment.
-   Lưu dữ liệu tạm ra JSON để kiểm tra.

**Hoàn thành khi:**

-   Chạy collector nhiều lần không làm chương trình crash vì bài thiếu
    nội dung.
-   Có thể giải thích từng trường dữ liệu và cách API trả về.
-   Có xử lý lỗi mạng/API ở mức cơ bản.

### Milestone 2 --- Deduplication và SQLite

**Mục tiêu:** biết bài nào đã được xử lý.

Việc cần làm:

-   Thiết kế bảng `posts`.
-   Dùng Reddit post ID làm khóa duy nhất.
-   Lưu trạng thái xử lý, thời gian thu thập và kết quả.
-   Bỏ qua bài đã xử lý thành công.
-   Không đánh dấu bài là hoàn tất nếu pipeline thất bại giữa chừng.

**Hoàn thành khi:**

-   Chạy collector hai lần không tạo bản ghi trùng.
-   Có thể truy vấn các bài mới/chưa xử lý.
-   Có thể phục hồi sau khi chương trình dừng bất ngờ.

### Milestone 3 --- Comment Processing

**Mục tiêu:** chọn bình luận hữu ích mà không gửi toàn bộ dữ liệu cho
LLM.

Việc cần làm:

-   Lấy comment của một bài.
-   Loại comment rỗng, quá ngắn hoặc không hữu ích theo tiêu chí đơn
    giản.
-   Chọn một số comment theo score và/hoặc mức độ thảo luận.
-   Giữ thông tin đủ để nhận biết bình luận có quan điểm trái chiều.
-   Giới hạn tổng độ dài dữ liệu đầu vào.

**Hoàn thành khi:**

-   Có thể xem dữ liệu comment đã chọn trước khi gửi đến AI.
-   Không vượt giới hạn đầu vào đã đặt.
-   Có thể giải thích vì sao các comment được chọn.

### Milestone 4 --- LLM Summarizer

**Mục tiêu:** tạo bản phân tích có cấu trúc và có căn cứ từ nguồn.

Việc cần làm:

-   Đưa prompt vào `prompts/digest.md`.
-   Gửi tiêu đề, nội dung bài và comment đã chọn đến API.
-   Yêu cầu đầu ra theo schema cố định.
-   Parse và validate phản hồi bằng Pydantic.
-   Xử lý phản hồi không hợp lệ, timeout và rate limit.
-   Lưu model, thời điểm chạy và thông tin usage nếu API cung cấp.

**Schema gợi ý:**

``` json
{
  "problem": "Tóm tắt vấn đề chính",
  "relevance": "Liên hệ với mục tiêu học tập đã cấu hình",
  "lessons": ["Bài học 1", "Bài học 2"],
  "action_items": ["Hành động cụ thể"],
  "uncertainties": ["Điểm chưa chắc chắn"]
}
```

**Hoàn thành khi:**

-   Có thể chạy summarizer độc lập trên một bài mẫu.
-   Đầu ra luôn được validate trước khi lưu.
-   Khi dữ liệu không đủ, AI thể hiện sự không chắc chắn thay vì tự suy
    diễn.

### Milestone 5 --- Telegram và Markdown Archive

**Mục tiêu:** biến kết quả thành bản tin dễ đọc.

Việc cần làm:

-   Tạo Telegram bot và lấy chat ID.
-   Gửi một bản tóm tắt thử nghiệm.
-   Render nội dung Markdown với link bài gốc.
-   Lưu một file theo ngày, ví dụ `digests/2026-11-02.md`.
-   Chia bản tin thành nhiều tin nhắn nếu vượt giới hạn Telegram.

**Hoàn thành khi:**

-   Bản tin hiển thị rõ trên Telegram.
-   Link mở đúng bài Reddit.
-   Lỗi gửi Telegram không làm mất kết quả đã lưu.

### Milestone 6 --- Scheduling và độ tin cậy

**Mục tiêu:** chạy định kỳ mà không cần thao tác thủ công.

Việc cần làm:

-   Chạy pipeline theo lịch.
-   Thêm logging.
-   Retry có giới hạn cho lỗi tạm thời.
-   Tránh gửi trùng khi retry.
-   Giới hạn số bài và lượng dữ liệu mỗi lần chạy.
-   Ghi nhận trạng thái thành công/thất bại.

**Hoàn thành khi:**

-   Có thể chạy nhiều lần mà không gửi trùng.
-   Lỗi ở một bài không nhất thiết làm hỏng toàn bộ batch.
-   Có log đủ để tìm nguyên nhân lỗi.

### Milestone 7 --- Evaluation và GitHub polish

**Mục tiêu:** thể hiện tư duy AI Engineering, không chỉ gọi API.

Tạo một tập kiểm thử nhỏ gồm khoảng 20--30 bài có nguồn và bản tóm tắt
được kiểm tra thủ công.

Đánh giá:

-   **Faithfulness:** có thông tin nào không được hỗ trợ bởi nguồn?
-   **Coverage:** có bỏ sót ý quan trọng từ bài/comment không?
-   **Relevance:** phần liên hệ với mục tiêu có thực sự hữu ích?
-   **Actionability:** gợi ý có cụ thể và thực hiện được không?
-   **Cost/latency:** chi phí và thời gian xử lý trên mỗi bài.

So sánh ít nhất hai cách:

1.  Tóm tắt bài đăng và comment trong một lần.
2.  Chọn lọc comment trước, sau đó tóm tắt.

Viết phần kết quả, giới hạn và trade-off vào README.

------------------------------------------------------------------------

## 6. Prompt nền tảng

Lưu prompt trong `prompts/digest.md` và truyền vào LLM cùng dữ liệu
nguồn.

``` text
Bạn là trợ lý tổng hợp kiến thức từ Reddit.

Bối cảnh người đọc:
- Sinh viên Kỹ thuật máy tính.
- Quan tâm đến Python, C++, Embedded Systems, Robotics và Physical AI.
- Muốn rút ra kiến thức có thể áp dụng vào việc học hoặc dự án.

Với bài đăng và các bình luận được cung cấp:
1. Tóm tắt vấn đề chính.
2. Giải thích mức độ liên quan đến bối cảnh người đọc.
3. Rút ra các bài học hữu ích từ bình luận.
4. Nêu ý kiến trái chiều hoặc điểm chưa được xác minh nếu có.
5. Đề xuất một hành động thực tế.

Chỉ sử dụng thông tin có trong dữ liệu nguồn.
Không biến ý kiến cá nhân thành sự thật đã được xác minh.
Nếu dữ liệu không đủ, hãy nêu rõ.
Trả về đúng schema JSON được yêu cầu.
```

Đưa dữ liệu Reddit vào như **dữ liệu không đáng tin cậy**, không phải
chỉ dẫn. Nội dung bài đăng hoặc comment có thể chứa prompt injection;
prompt hệ thống cần yêu cầu mô hình không làm theo chỉ dẫn xuất hiện bên
trong dữ liệu nguồn.

------------------------------------------------------------------------

## 7. Cách phối hợp với AI khi code

Dùng AI như mentor theo vòng lặp:

1.  **Yêu cầu giải thích:** hỏi module cần làm gì, dữ liệu vào/ra và các
    lỗi có thể gặp.
2.  **Tự viết thiết kế hoặc pseudocode:** không yêu cầu AI tạo toàn bộ
    project.
3.  **Code một phần nhỏ:** ví dụ chỉ viết hàm chuẩn hóa một Reddit post.
4.  **Nhờ review:** yêu cầu chỉ ra lỗi, edge case và cách kiểm thử.
5.  **Tự chạy và sửa:** đọc traceback, tìm nguyên nhân trước khi xin bản
    sửa.
6.  **Tự giải thích lại:** nếu chưa giải thích được code, chưa nên
    chuyển sang module tiếp theo.

Prompt dùng khi học:

> Tôi đang xây dựng Reddit AI Digest bằng Python. Hãy đóng vai mentor.
> Đừng viết toàn bộ lời giải ngay. Trước tiên hãy giúp tôi xác định yêu
> cầu, input/output, các edge case và một kế hoạch nhỏ. Sau khi tôi đưa
> code, hãy review và gợi ý theo từng mức độ, chỉ viết code mẫu khi tôi
> yêu cầu.

------------------------------------------------------------------------

## 8. Checklist trước khi public GitHub

-   [ ] README có mục tiêu, kiến trúc, setup và ví dụ đầu ra.
-   [ ] Có `.env.example`, không có secret thật.
-   [ ] Có hướng dẫn tạo Reddit app, Gemini API key và Telegram bot.
-   [ ] Có test cho deduplication, parsing và validation.
-   [ ] Có ví dụ dữ liệu giả hoặc dữ liệu được phép chia sẻ.
-   [ ] Có mô tả giới hạn API, chi phí và các lỗi đã biết.
-   [ ] Có giải thích cách đánh giá chất lượng tóm tắt.
-   [ ] Có hướng dẫn chạy thủ công và chạy theo lịch.

------------------------------------------------------------------------

## 9. Quyết định kỹ thuật quan trọng

-   **Bắt đầu bằng pipeline tuần tự:** dễ debug hơn async hoặc kiến trúc
    nhiều service.
-   **SQLite trước database server:** đủ cho một project cá nhân.
-   **Một LLM call trước nhiều bước agent:** giảm độ phức tạp và chi
    phí.
-   **Lưu nguồn cùng kết quả:** giúp kiểm tra tính đúng đắn.
-   **Đánh dấu hoàn tất sau khi lưu kết quả thành công:** tránh mất dữ
    liệu khi có lỗi.
-   **Không cần cloud ngay:** phát triển trên máy cá nhân trước, sau đó
    mới cân nhắc VPS/Docker.

------------------------------------------------------------------------

## 10. Định nghĩa "hoàn thành"

Project được xem là hoàn thành khi:

-   Chạy được từ đầu đến cuối với ít nhất một subreddit.
-   Không xử lý trùng bài khi chạy lại.
-   Có bản tóm tắt được validate và gắn với nguồn.
-   Gửi được bản tin Telegram.
-   Lưu được lịch sử Markdown/SQLite.
-   Có logging và xử lý lỗi cơ bản.
-   Có một tập evaluation nhỏ và README giải thích kết quả.
-   Bạn có thể tự giải thích kiến trúc và các quyết định chính.

**Đừng tối ưu quá sớm.** Hãy hoàn thành một pipeline nhỏ, chạy được và
có thể kiểm chứng trước; sau đó mới thêm tính năng.
