# Day 14 Lab — Mission Answers

> **Môn:** AICB-P1 · VinUniversity 2026 — Day 14: Deployment, Benchmark & Observability

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trực tiếp trong mã nguồn** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Đẩy lên Git sẽ lộ thông tin nhạy cảm ngay cả khi xóa sau này (vì nằm trong lịch sử commit).
2. **In secret ra stdout qua `print()`** (dòng 33–38): dùng `print()` thay vì structured logging và in trực tiếp `OPENAI_API_KEY` (dòng 34) ra log.
3. **Cấu hình cố định, không đọc từ biến môi trường** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` viết cứng, không thể đổi giữa dev/staging/production mà không sửa code.
4. **Không có health check / readiness endpoints** (dòng 42–43): thiếu `GET /health` và `GET /ready` nên load balancer / cloud platform không biết khi nào container sống, sẵn sàng nhận traffic hay cần restart.
5. **Bind cứng `host="localhost"` và `port=8000`** (dòng 51–52): `localhost` chỉ nghe trên loopback nên không nhận traffic từ ngoài container; port cố định không tương thích biến `PORT` do Railway/Render/Cloud Run cấp.
6. **Bật `reload=True` mặc định** (dòng 53): chế độ auto-reload chỉ dành cho phát triển cục bộ, gây tốn tài nguyên và mất ổn định trong production.
7. **Không có graceful shutdown & lifecycle management**: không dùng `lifespan` hay xử lý `SIGTERM`, dễ cắt ngang request đang chạy khi tắt/deploy lại.

### Exercise 1.2: Kết quả chạy bản `develop`

```bash
curl -i -s -X POST "http://localhost:8000/ask?question=Hello"
```

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:58:23 GMT
server: uvicorn
content-length: 95
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 1.3: So sánh bản `develop` và `production`

Kết quả kiểm tra bản `production` (`01-localhost-vs-production/production/app.py`):

- `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":0.9,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:58:29.321826+00:00"}`
- `GET /ready` → `200 OK`: `{"ready":true}`
- `POST /ask` (`{"question":"Hello"}`) → `200 OK`: `{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}`
- Khi gửi `SIGTERM`, log ghi nhận `Shutting down` → `Application shutdown complete.` (graceful shutdown).

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True` (dòng 17–22) | Đọc toàn bộ từ biến môi trường qua `config.py` (`settings`), có `.env.example` | Tuân thủ 12-Factor App: cùng một artifact chạy được ở dev/staging/prod và không lộ secret vào Git |
| **Network Binding & Port** | `host="localhost"`, `port=8000`, `reload=True` (dòng 51–53) | `host=settings.host` (`0.0.0.0`), `port=settings.port` (từ `PORT`), `reload=settings.debug` (dòng 194–199) | Bắt buộc để chạy trong Docker container và nhận `PORT` động từ nền tảng cloud |
| **Health & Readiness** | Không có | Có `GET /health` (dòng 135–149) và `GET /ready` (dòng 152–161) | Platform biết khi nào cần restart container (`/health`) và load balancer biết khi nào mới được gửi traffic (`/ready`) |
| **Logging** | `print()` dạng text thuần, làm lộ API key (dòng 33–38) | Structured JSON logging bằng `logging` + `json.dumps(...)`, không log secret (dòng 28–32, 111–122) | Dễ gom log, tìm kiếm, lọc và phân tích tự động bằng Datadog/Loki/ELK mà không rò rỉ dữ liệu nhạy cảm |
| **Shutdown** | Tắt đột ngột, không dọn dẹp | Quản lý vòng đời qua `@asynccontextmanager async def lifespan` (dòng 39–67) và `signal.SIGTERM` (dòng 180–189) | Ngừng nhận traffic mới (`is_ready = False`), hoàn thành request đang xử lý trước khi thoát để không gây lỗi 502/mất dữ liệu |
| **CORS & Input Validation** | Không có CORS, nhận `question` qua query param | Cấu hình `CORSMiddleware` giới hạn origins/methods (dòng 77–82), đọc JSON body và trả `422` khi thiếu `question` (dòng 103–108) | Giảm rủi ro bảo mật phía trình duyệt và trả lỗi rõ ràng cho client |

**Ví dụ anti-pattern đã được sửa (kèm dòng code):** Trong `develop/app.py` (dòng 42–43) không có health check; `production/app.py` đã bổ sung `GET /health` ở dòng 135–149 và `GET /ready` ở dòng 152–161 kiểm tra cờ `is_ready` (trả `503` khi chưa sẵn sàng hoặc đang shutdown).

---

## Part 2: Docker

### Exercise 2.1: Trả lời 4 câu hỏi về `02-docker/develop/Dockerfile`

1. **Base image là gì?** `python:3.11` (dòng 8) — bản phân phối đầy đủ của Python trên Debian (~1 GB trở lên, chứa nhiều công cụ hệ thống không cần cho runtime).
2. **Working directory là gì?** `/app` (dòng 11, lệnh `WORKDIR /app`) — thư mục làm việc mặc định trong container cho các lệnh `COPY`, `RUN`, `CMD` phía sau.
3. **Tại sao `COPY requirements.txt` phải đứng trước `COPY . .` (hay `COPY app.py`)?** Để tận dụng **Docker layer cache**: mã nguồn thay đổi thường xuyên còn `requirements.txt` ít đổi. Nếu đặt `COPY requirements.txt` và `RUN pip install` trước, khi sửa code ứng dụng Docker chỉ cần rebuild từ bước copy code mà không phải tải và cài lại toàn bộ dependencies.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?** `ENTRYPOINT` định nghĩa tiến trình thực thi cố định của container (khó bị ghi đè, tham số dòng lệnh ở `docker run` sẽ được nối thêm vào cuối); còn `CMD` chỉ là lệnh hoặc tham số mặc định, dễ bị thay thế hoàn toàn khi truyền lệnh mới ở cuối `docker run <image> <cmd>`.

### Exercise 2.2: Build và test container `my-agent:develop`

Lệnh build chạy từ gốc repo: `docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`

Kết quả gọi container trên cổng 8000 (`curl -i -s -X POST "http://localhost:8000/ask?question=What+is+Docker"`):

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:03:47 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build và so sánh kích thước image thực đo

Phân tích `02-docker/production/Dockerfile`:
- **Stage 1 (`builder`, từ `python:3.11-slim`):** cài trình biên dịch (`gcc`, `libpq-dev`) và cài toàn bộ Python packages vào `/root/.local` bằng `pip install --no-cache-dir --user`.
- **Stage 2 (`runtime`, từ `python:3.11-slim`):** tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local` cùng mã nguồn ứng dụng (`main.py`, `utils/mock_llm.py`), thêm `HEALTHCHECK` và chạy bằng `USER appuser`.
- **Vì sao image nhỏ hơn?** Image cuối loại bỏ hoàn toàn hệ điều hành đầy đủ của `python:3.11`, loại bỏ `gcc`, header files, `apt` packages và build cache ở stage 1, đồng thời nhỏ hơn nên kéo image nhanh hơn và giảm bề mặt tấn công bảo mật.

Số đo thực tế bằng `docker images` và `docker image inspect` trên máy:

```text
REPOSITORY:TAG       SIZE
my-agent:advanced    240MB
my-agent:develop     1.67GB
```

- **Develop (`my-agent:develop`):** `1667.8 MB` (`1590.5 MiB` / `1,667,771,774 bytes`)
- **Production (`my-agent:advanced`):** `239.8 MB` (`228.7 MiB` / `239,811,435 bytes`)
- **Chênh lệch (giảm):** **`85.6%`** (giảm ~`1428 MB`)

### Exercise 2.4: Docker Compose stack (`02-docker/production/`)

**Sơ đồ kiến trúc các service (cùng nằm trong bridge network `internal`):**

```text
Client (HTTP :80)
   │
   ▼
┌───────────────────┐
│  Nginx (nginx:80) │  ← cổng public duy nhất, thêm security headers
└─────────┬─────────┘
          │ reverse proxy → agent:8000
          ▼
┌───────────────────┐
│  Agent (FastAPI)  │  ← depends_on: redis (healthy), qdrant (healthy)
└────┬─────────┬────┘
     │         │
     ▼         ▼
┌─────────┐ ┌────────────────┐
│  Redis  │ │ Qdrant (:6333) │
│ (:6379) │ │  Vector DB     │
└─────────┘ └────────────────┘
```

**Kết quả test qua Nginx (`docker compose -p k5-day14-docker up -d --build`):**

```http
# GET http://localhost/health
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.9,"version":"2.0.0","timestamp":"2026-11-26T08:06:18.403494"}

# POST http://localhost/ask  {"question":"Explain microservices"}
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

*(Đã dọn stack bằng `docker compose -p k5-day14-docker down -v` sau khi test).*

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy agent Part 6 (`06-lab-complete/`)

- **Platform:** Render (`runtime: docker` từ `06-lab-complete/Dockerfile`, kết nối Managed Redis trên cloud)
- **Public URL:** https://k5-l3b-day14-nguyentanchau-2a202603846.onrender.com
- **Kết quả kiểm tra 4 lệnh CP6 trên Public URL (đã che `AGENT_API_KEY` thành `k5-day14-****`):**
  - `GET /health` → **`200`** (`{"status":"ok","environment":"production","uptime_seconds":4.2}`)
  - `GET /ready` → **`200`** (`{"ready":true,"redis":"ok"}`)
  - `POST /ask` (không có `X-API-Key`) → **`401`**
  - `POST /ask` (`X-API-Key: k5-day14-****`) → **`200`** (`{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"input_tokens":2,"output_tokens":17,"cost_usd":1.05e-05}}`)
- **Xác minh bằng script chấm:** `check_production_ready.py --public-url "https://k5-l3b-day14-nguyentanchau-2a202603846.onrender.com"` báo **`✅ Public URL: GET .../health → 200`** và **`PASS 12/12 (44/44 checks passed)`**.
- **Screenshots:**
  - [Deployment dashboard](screenshots/dashboard.png)
  - [Service running](screenshots/running.png)
  - [Test results](screenshots/test.png)
- Chi tiết đầy đủ xem thêm trong `DEPLOYMENT.md`.

### So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
|---|---|---|
| **Định dạng & phạm vi** | TOML, cấu hình **1 service đơn lẻ** (`[build]` và `[deploy]`). | YAML (Infrastructure as Code), khai báo được **nhiều service cùng lúc** (web service + Redis trong cùng 1 file). |
| **Cách khai báo build** | `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` (hoặc `NIXPACKS`/`RAILPACK`). | `type: web`, `runtime: docker`, `dockerfilePath: ./Dockerfile` (hoặc `runtime: python` kèm `buildCommand`/`startCommand`). |
| **Health check** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` dưới `[deploy]`. | `healthCheckPath: /health` ngay trong định nghĩa web service. |
| **Biến môi trường & secrets** | Không lưu trong `railway.toml`; cấu hình qua `railway variables set` hoặc Dashboard (tách hoàn toàn khỏi repo). | Khai báo danh sách `envVars` trực tiếp trong Blueprint; secret dùng `generateValue: true` hoặc `sync: false`, và liên kết Redis tự động qua `fromService`. |
| **Khởi tạo Redis** | Thêm plugin/service Redis riêng trên Railway Project rồi nối biến tham chiếu `REDIS_URL`. | Có thể khai báo trực tiếp block `- type: redis` trong `render.yaml` để Blueprint tự dựng đồng bộ. |

### Exercise 3.3: Mô tả pipeline CI/CD GCP Cloud Run (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD trên Google Cloud Build triển khai lên Cloud Run đi qua 4 bước tuần tự (`waitFor`) khi có commit lên nhánh chính:
1. **Test (`test`):** Dùng container `python:3.11-slim` cài dependencies và chạy `pytest tests/ -v`; nếu test fail sẽ dừng pipeline ngay.
2. **Build (`build`):** Dùng `cloud-builders/docker` build Docker image gắn 2 tag (`$COMMIT_SHA` để rollback chính xác và `latest` để tận dụng `--cache-from`).
3. **Push (`push`):** Đẩy toàn bộ tag của image lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Gọi `gcloud run deploy ai-agent` với image theo `$COMMIT_SHA` (tương ứng cấu hình IaC trong `service.yaml`: `minScale=1` tránh cold start, `maxScale=10`, `containerConcurrency=80`, giới hạn `1 CPU / 512Mi RAM`, lấy secret từ Secret Manager qua `secretKeyRef`, kiểm tra `startupProbe` `/ready` và `livenessProbe` `/health`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- **API key được kiểm tra ở đâu?** Trong dependency `verify_api_key` (dòng 39–54) đọc header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)` và gắn vào endpoint `POST /ask` qua `Depends(verify_api_key)` (dòng 70).
- **Điều gì xảy ra nếu thiếu hoặc sai key?** Thiếu header trả `401 Unauthorized`; gửi sai key trong bản develop này trả `403 Forbidden` (ở Part 6 chuẩn hóa cả hai về `401`).
- **Làm sao rotate key không downtime?** Hỗ trợ danh sách nhiều key hợp lệ tạm thời (ví dụ `AGENT_API_KEYS=old_key,new_key` qua biến môi trường): thêm key mới → cập nhật dần các client sang key mới → theo dõi log xác nhận không còn request dùng key cũ → xóa key cũ khỏi biến môi trường.

**Output `curl -i` thực tế (Exercise 4.1 — `AGENT_API_KEY=secret-key-123`):**

```http
# Không có X-API-Key → 401
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 08:06:45 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có X-API-Key hợp lệ → 200
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:06:45 GMT
server: uvicorn
content-length: 145
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **Thuật toán Rate Limiting (`rate_limiter.py`):** **Sliding Window Log/Counter** dùng `deque` lưu timestamp từng request trong cửa sổ `window_seconds = 60` giây; mỗi lần gọi sẽ `popleft()` các timestamp cũ hơn `now - 60`, kiểm tra `len(window) >= max_requests`.
- **Giới hạn & phân quyền:** `rate_limiter_user` cho `role="user"` (`student`) là **10 requests/phút**; `rate_limiter_admin` cho `role="admin"` (`teacher`) là **100 requests/phút** (hoặc có thể bỏ qua bước gọi `limiter.check()` nếu `role == "admin"` để bypass).

**Output `curl -i` thực tế (`POST /auth/token` với `student`/`demo123`, đã che JWT token):**

```http
# 1) Gọi POST /ask không có Authorization header → 401
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 08:07:36 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# 2) Gọi POST /ask với -H "Authorization: Bearer <REDACTED_JWT_TOKEN>" (Request #1) → 200
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:07:36 GMT
server: uvicorn
content-length: 192
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

# 3) Vòng lặp requests #2..#12: requests #2..#10 trả HTTP 200; request #11 bị chặn → 429
HTTP/1.1 429 Too Many Requests
date: Thu, 26 Nov 2026 08:07:37 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795680518
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cách triển khai Cost Guard & Vì sao cần cả Rate Limit lẫn Cost Guard

- **Cách làm Cost Guard chuẩn production (đã triển khai trong `06-lab-complete/app/cost_guard.py`):**
  - Dùng key theo ngày hoặc tháng trên **Redis** (vd `cost:daily:YYYY-MM-DD` hoặc `budget:{user_id}:{YYYY-MM}`) để chia sẻ giữa mọi worker/instance.
  - **Trước khi gọi LLM (`check_budget`):** đọc tổng chi phí hiện tại từ Redis; nếu `>= DAILY_BUDGET_USD` (hoặc `MONTHLY_BUDGET_USD`) → chặn ngay bằng **HTTP `402 Payment Required`** để không phát sinh thêm chi phí LLM.
  - **Sau khi gọi LLM (`record_cost`):** tính chi phí dựa trên số `input_tokens` và `output_tokens` nhân bảng giá token (`PRICE_INPUT_PER_1K`, `PRICE_OUTPUT_PER_1K`), rồi cộng dồn atomic vào Redis bằng `INCRBYFLOAT` kèm `EXPIRE` tự dọn key khi hết chu kỳ.
- **Vì sao cần cả Rate Limit và Cost Guard?** Rate Limit bảo vệ **tốc độ/tải hệ thống** (chống spam/DDoS, giới hạn số request/phút), nhưng một người dùng vẫn có thể gửi ít request với prompt rất dài hoặc gọi đều đặn cả ngày gây đội hóa đơn LLM. Cost Guard bảo vệ trực tiếp **ngân sách tiền (USD)** theo lượng token tiêu thụ thực tế.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health Checks (`/health`, `/ready`) & Graceful Shutdown

- **Khác biệt giữa Liveness (`GET /health`) và Readiness (`GET /ready`):**
  - **Liveness (`/health`):** kiểm tra tiến trình còn sống hay đã bị treo/deadlock; không phụ thuộc vào dịch vụ ngoài (như Redis). Nếu `/health` fail, orchestrator sẽ **restart container**.
  - **Readiness (`/ready`):** kiểm tra instance có sẵn sàng nhận traffic hay không (kết nối Redis/DB ổn định, không trong trạng thái đang startup hoặc đang shutdown). Nếu `/ready` trả `503`, load balancer chỉ **ngừng route traffic mới** vào instance đó mà **không restart** nó.
- **Kết quả kiểm tra `05-scaling-reliability/develop/app.py`:**
  - `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":1.4,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T08:07:43.851665+00:00","checks":{"memory":{"status":"ok","used_percent":11.1}}}`
  - `GET /ready` → `200 OK`: `{"ready":true,"in_flight_requests":1}`
  - Khi nhận `SIGTERM`, uvicorn dừng nhận kết nối mới, chạy `lifespan` shutdown (`_is_ready = False`, đợi in-flight requests về 0) và log:
    `🔄 Graceful shutdown initiated...` → `✅ Shutdown complete` → `Finished server process`.

### Exercise 5.3–5.5: Stateless Design, Load Balancing & Kết quả `test_stateless.py`

- **Vì sao state lưu trong RAM bị hỏng khi scale nhiều instance?** Mỗi container/worker có vùng nhớ RAM riêng biệt. Nếu lưu lịch sử hội thoại, rate limit hay cost counter trong `dict` ở RAM, request 1 đi vào `agent-1` nhưng request 2 lại bị Nginx đưa sang `agent-2` sẽ bị mất ngữ cảnh hội thoại (hoặc đếm sai giới hạn). Đưa toàn bộ state vào **Redis** dùng chung giúp mọi instance trở nên **stateless**, có thể scale ngang hoặc thay thế instance bất kỳ lúc nào mà không mất dữ liệu.
- **Kết quả chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py` (`05-scaling-reliability/production/`):**

```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 19a014ab-e02e-441b-a14e-c24c12052a47

Request 1: [instance-a15666]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-815019]
  Q: Why do we need containers?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 3: [instance-a15666]
  Q: What is Kubernetes?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 4: [instance-0d559d]
  Q: How does load balancing work?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 5: [instance-815019]
  Q: What is Redis used for?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-0d559d', 'instance-815019', 'instance-a15666'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Kubernetes?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: How does load balancing work?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Redis used for?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...

✅ Session history preserved across all instances via Redis!
```

**Giải thích:** 5 request trong cùng một `session_id` được Nginx phân tán ra cả **3 instance khác nhau** (`instance-a15666`, `instance-815019`, `instance-0d559d`), nhưng khi gọi `GET /chat/{session_id}/history` vẫn nhận đủ **10 tin nhắn** (5 câu hỏi + 5 câu trả lời) vì toàn bộ lịch sử được lưu tập trung trong Redis. *(Đã dọn stack bằng `docker compose -p k5-day14-scaling down -v`).*

---

## Part 6: Final Project (`06-lab-complete/`)

Kết quả chạy `.venv/bin/python check_production_ready.py --public-url "https://k5-l3b-day14-nguyentanchau-2a202603846.onrender.com"` đầy đủ trong WSL2 (`Ubuntu-22.04`, `os.name == "posix"`, Docker Engine `29.9.3`, image `273 MB`, `docker stop` exit code `0` trong `0.6s`, đã kiểm tra kèm Public URL trên Render):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 44/44 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

1. **Lập kế hoạch & rà soát yêu cầu bài lab:**
   - **Hỏi AI:** Quét thư mục dự án, đọc README/RULES/RUBRIC/CHECKPOINTS và mã nguồn khung để lập lộ trình hoàn thiện từng bước và lệnh test tương ứng.
   - **Nhận được:** Danh sách quy tắc bắt buộc (không sửa `check_production_ready.py`, `golden_dataset.jsonl`, chạy WSL2 `posix`, dùng `-p` cho Docker Compose), danh sách 12 file TODO của Part 6 và thứ tự triển khai tối ưu.
   - **Tự kiểm tra:** Đối chiếu trực tiếp với `RULES.md`, `SUBMISSION.md` và `check_production_ready.py`; kiểm tra môi trường thực tế (`python3`, `os.name`, bật Docker Desktop + WSL2 Integration).
2. **Triển khai Part 6 (`06-lab-complete/`):**
   - **Hỏi AI:** Hỗ trợ triển khai theo từng bước `config.py`, `.env.example`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile` (multi-stage dùng `/opt/venv` + non-root + `exec uvicorn`), `.dockerignore`, `docker-compose.yml`, `railway.toml` và `render.yaml`.
   - **Nhận được:** Code hoàn chỉnh cho 12 file TODO theo hợp đồng của `06-lab-complete/README.md`.
   - **Tự kiểm tra:** Chạy `docker compose config`, chạy `.venv/bin/python check_production_ready.py --skip-docker` (kiểm tra trước tầng ứng dụng & runtime), sau đó chạy bản đầy đủ `.venv/bin/python check_production_ready.py` trong WSL2 đạt **`PASS 12/12` (43/43 checks)** và kiểm tra `git status` không có `.env` hay file ngoài phạm vi.
3. **Chạy thực nghiệm Part 1, 2, 4, 5 & Part 7 Bước 1 (CP1–CP4, CP7):**
   - **Hỏi AI:** Hỗ trợ thực thi các lệnh chạy server/container, đo kích thước image, test JWT/rate limit/stateless, thêm Histogram `agent_question_length_chars` (Exercise 7.1), chạy load test & eval và bổ sung 2 entry vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py`.
   - **Nhận được:** Output thực tế từ các lệnh chạy trên máy và bản tổng hợp `MISSION_ANSWERS.md`, `BENCHMARK_REPORT.md` cùng 10 file JSON trong `reports/`.
   - **Tự kiểm tra:** Mọi số liệu (MB image, latency p50/p95/p99, accuracy `23/23`, cost) đều lấy trực tiếp từ lệnh chạy thực tế và đối chiếu khớp với các file JSON trong `reports/`.
4. **Chạy Observability Stack Part 7 Bước 2 (CP8):**
   - **Hỏi AI:** Hỗ trợ chạy unit test `promtool`, khắc phục lỗi thiếu `ENV PYTHONUSERBASE=/home/agent/.local` trong starter `production/Dockerfile`, chạy Locust headless scaling 1 vs 3 instances với `--no-deps`, kiểm tra Nginx chặn `/metrics` (`404`), kích hoạt 2 alert `Firing` (`AgentHighErrorRate`, `LLMCostBurnRateHigh`), trích xuất `trace_id` và log JSON từ Jaeger/container logs.
   - **Nhận được:** File `scale_1_stats.csv`, `scale_3_stats.csv`, số liệu thời gian firing, trace chậm/lỗi và phần Mục 4–6 của `BENCHMARK_REPORT.md`.
   - **Tự kiểm tra:** Tự mở Grafana, Jaeger và Prometheus trên trình duyệt để quan sát trực tiếp và chụp đủ 4 ảnh (`grafana-dashboard.png`, `jaeger-slow-trace.png`, `jaeger-error-trace.png`, `prometheus-alert-firing.png`), sau đó xóa `.env` tạm và chạy `docker compose -p k5-day14-observability down -v`.
5. **Deploy Cloud (CP6) & rà soát trước khi nộp bài:**
   - **Hỏi AI:** Kiểm tra 4 lệnh `curl` và `check_production_ready.py --public-url` với Public URL đã deploy lên Render, cập nhật `DEPLOYMENT.md` & Part 3 của `MISSION_ANSWERS.md` (che key thành `k5-day14-****`), và rà soát toàn bộ checklist trong `SUBMISSION.md`.
   - **Nhận được:** Kết quả xác minh `200 / 200 / 401 / 200`, `PASS 12/12 (44/44 checks passed)` và báo cáo rà soát sạch secret/cấu trúc nộp bài.
   - **Tự kiểm tra:** Tự thao tác deploy Web Service + Redis và cấu hình biến môi trường trên Render Dashboard, tự chụp 3 ảnh (`dashboard.png`, `running.png`, `test.png`) và đối chiếu lại toàn bộ checklist trước khi commit & push lên GitHub.
