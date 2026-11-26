# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được lấy trực tiếp từ các file report JSON trong `reports/` (và sẽ bổ sung CSV/screenshot ở phần 4–5 khi chạy stack CP8).

**Họ tên:** Nguyen Tan Chau (MSSV: 2A202603846)  
**Ngày chạy:** 2026-11-26  
**Môi trường:** Windows + WSL2 (Ubuntu-22.04), 8 CPU / 7.6 GiB RAM, Docker Engine 29.9.3, Python 3.10.12

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Với mock LLM có độ trễ nền ~120–180 ms và bước retrieval ~20 ms, ngưỡng 500 ms đảm bảo 95% người dùng nhận phản hồi mượt (< 0.5s) kể cả khi có tải vừa (`c=10`), đồng thời phát hiện ngay khi hệ thống quá tải hoặc tỉ lệ slow request vượt 5%. |
| Error rate `/ask` | `< 2.0 %` | Upstream LLM có tỉ lệ lỗi ngẫu nhiên mặc định ~1% (`MOCK_ERROR_RATE=0.01`), nên chọn ngưỡng SLO 2% tạo error budget hợp lý mà vẫn báo động sớm nếu upstream bất ổn nặng (alert đặt cao hơn ở > 5% để tránh alert fatigue). |
| Accuracy trên golden dataset | `≥ 85 %` (mục tiêu sau sửa KB: `100 %`, không regression) | Đảm bảo agent v2 giữ chất lượng trả lời cao trên toàn bộ 23 câu hỏi kiến thức lõi và chặn mọi PR làm tụt chất lượng hoặc gây regression so với baseline. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

*(Ghi chú Exercise 7.1: đã bổ sung metric Histogram `agent_question_length_chars` vào `06-lab-complete/benchmark-observability/develop/app.py` với các bucket `20, 50, 100, 200, 500, 1000, 2000` và xác nhận metric xuất hiện đúng trên `GET /metrics`; không dùng độ dài câu hỏi làm label để tránh bùng nổ cardinality).*

### 2.1 Concurrency vs latency (agent v2, 300 requests/mức, nguồn: `reports/load_v2_c*.json`)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.04 | 194.0 | 222.3 | 1717.3 | 0.33% | PASS |
| 10 | 37.80 | 195.2 | 251.9 | 1720.8 | 0.67% | PASS |
| 50 | 41.38 | 424.3 | 3285.8 | 5005.1 | 1.00% | FAIL |
| 100 | 40.47 | 1366.9 | 5380.6 | 5899.3 | 0.67% | FAIL |

**Nhận xét:** RPS **không tăng tuyến tính** theo concurrency. Từ `c=1` lên `c=10`, RPS tăng gần tuyến tính (`4.04 → 37.80 req/s`, ~9.4×) trong khi p50 (`194.0 → 195.2 ms`) và p95 (`222.3 → 251.9 ms`) gần như giữ nguyên. Tuy nhiên từ `c=50` sang `c=100`, một tiến trình uvicorn đơn lẻ đã chạm điểm bão hòa (~`40–41 req/s`), RPS chững lại thậm chí giảm nhẹ (`41.38 → 40.47 req/s`) trong khi hàng đợi request tăng mạnh khiến p50 nhảy vọt (`424.3 → 1366.9 ms`) và p95/p99 vượt xa ngưỡng SLO `500 ms` (`3285.8 → 5380.6 ms`).

### 2.2 Tail latency (`--requests 300 --concurrency 20`, nguồn: `reports/load_v2_slow_*.json`)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 191.7 | 222.3 | 242.2 |
| 0.03 (mặc định) | 254.2 | 246.7 | 1701.2 |
| 0.1 | 320.9 | 1689.7 | 1718.2 |

**Nhận xét:** **p99 và p95** nhạy nhất với request chậm bất thường (tail latency):
- Khi tăng `MOCK_SLOW_RATE` từ `0 → 0.03` (3% request chậm), `avg` chỉ tăng `+62.5 ms` (`191.7 → 254.2 ms`), nhưng **p99 nhảy gấp ~7 lần** (`242.2 → 1701.2 ms`).
- Khi tăng lên `0.1` (10% request chậm > 5%), `avg` mới đạt `320.9 ms` (trông vẫn "nhanh" hơn ngưỡng 500 ms), nhưng **cả p95 (`1689.7 ms`) lẫn p99 (`1718.2 ms`) đều vọt lên ~1.7 giây** và vi phạm SLO.
- Vì vậy **SLO không nên đặt theo average**: trung bình cộng bị kéo phẳng bởi đa số request nhanh và che giấu nhóm người dùng đang phải chờ rất lâu.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json` (chạy trên cùng 23 câu hỏi cố định trong `golden_dataset.jsonl`, không chỉnh sửa dataset).

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.8 | 109.3 | 113.9 |
| Tổng cost (USD) | 0.000414 | 0.000764 | 0.000792 |
| Cost / câu đúng (USD) | 0.00041355 | 0.00003639 | 0.00003445 |
| Latency p50 / p95 (ms) | 162.6 / 187.2 | 194.0 / 220.7 | 205.0 / 228.0 |
| Quality gate | FAIL | PASS | PASS (0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` với từ khóa kích hoạt `["jwt"]` giải thích sự khác biệt giữa API key và JWT (token có chữ ký số, chứa thông tin user và thời điểm hết hạn). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` với từ khóa kích hoạt `["hpa", "kubernetes", "autoscal"]` mô tả Kubernetes HPA scale số pod dựa trên CPU, memory hoặc custom metrics (RPS, độ dài hàng đợi). |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent v2 thêm bước retrieval (RAG) và đưa context vào prompt nên tốn gần **gấp đôi số token mỗi câu** (`109.3` → `113.9` so với `57.8` của v1) và tăng nhẹ latency (`p95`: `220.7–228.0 ms` so với `187.2 ms`).
- Đổi lại, accuracy tăng vọt từ **4.3% (1/23) lên 91.3% (21/23)** và đạt **100.0% (23/23)** sau khi bổ sung 2 tài liệu thiếu vào `KNOWLEDGE_BASE` mà **không gây regression** nào (`0 regression`).
- Xét theo chỉ số **cost / câu đúng**, v2 sau khi sửa chỉ tốn `0.00003445 USD/câu đúng` — **rẻ hơn ~12 lần** so với v1 (`0.00041355 USD/câu đúng`). Đây là bằng chứng rõ ràng rằng chi thêm token hợp lý cho RAG mang lại hiệu quả chi phí vượt trội trên mỗi câu trả lời đúng.

**Quality gate trong CI/CD (Exercise 7.3):**
- Đã kiểm chứng chạy `python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json` cho v1: script phát hiện accuracy `4.3% < 80%` cùng **20 câu bị regression** và thoát với **exit code `1`** (`Quality gate ... ❌ FAIL`). Trong khi chạy `eval_v2_fixed.json` với `--min-accuracy 1.0 --baseline reports/eval_v2.json` thoát với **exit code `0`** (`✅ PASS`).
- Trong GitHub Actions (hoặc GitLab CI), đặt bước chạy `run_eval.py --min-accuracy 0.85 --baseline reports/eval_v2.json` trên mỗi `pull_request`: nếu bất kỳ thay đổi prompt/retrieval/model nào làm accuracy giảm xuống dưới ngưỡng hoặc gây regression, lệnh trả exit code `1` làm CI job fail và **tự động chặn merge PR** trước khi deploy lên production:

```yaml
# .github/workflows/eval.yml
name: quality-gate
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Run agent & eval quality gate
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: |
          pip install -r requirements.txt
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
          sleep 3
          python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85 --baseline reports/eval_v2.json
```

---

## 4. Observability stack (production)

### 4.1 Unit test alert rules, kết quả Exercise 7.4 & Screenshot

- **Unit test alert rules (`promtool`):** chạy `docker run --rm -v "$PWD/prometheus:/p" --entrypoint promtool prom/prometheus:v3.16.0 test rules /p/alert_rules_test.yml` → **`SUCCESS`** (exit code `0`).
- **Kết quả trả lời Exercise 7.4 (quan sát stack `k5-day14-observability` có tải):**
  1. **p95 và avg:** Khi chạy tải bình thường (`mock-llm-small`, `MOCK_SLOW_RATE=0.03`), Prometheus ghi nhận `avg ≈ 247.0 ms` còn `p95 ≈ 420.3 ms` (và `p99 ≈ 1700 ms` trên Locust). Khoảng cách lớn giữa `avg` và `p95`/`p99` phản ánh hiện tượng **tail latency** (~3% request bị chậm thêm 1.5s kéo phân vị cao lên mạnh dù trung bình vẫn thấp).
  2. **Phân bố tải theo instance:** Với 3 instance agent, Prometheus (`sum by (instance) (rate(http_requests_total{job="agent",route="/ask"}[1m]))`) đo được:
     - `172.18.0.4:8000`: **21.49 req/s**
     - `172.18.0.8:8000`: **21.42 req/s**
     - `172.18.0.9:8000`: **21.23 req/s**
     → Nginx round-robin + DNS `resolve` chia tải rất đồng đều (~33.3% mỗi instance).
  3. **Vì sao input tokens/s lớn hơn output tokens/s?** Prometheus đo được `input ≈ 4704.0 tokens/s` so với `output ≈ 2497.8 tokens/s` (gấp ~1.88×) vì agent v2 (RAG) luôn gửi kèm **system prompt + đoạn tài liệu retrieve được + câu hỏi** làm đầu vào cho LLM, trong khi câu trả lời đầu ra ngắn gọn hơn.
  4. **Kiểm tra `curl -i http://localhost:8080/metrics`:** trả về **`HTTP/1.1 404 Not Found`** từ Nginx (`nginx/1.28.3`). Nginx cố tình chặn `/metrics` từ bên ngoài để không lộ thông tin nội bộ hệ thống và tránh bị tấn công DoS qua endpoint scrape; chỉ Prometheus trong mạng nội bộ `obs_net` mới gọi trực tiếp `agent:8000/metrics`.

- **Screenshot bằng chứng (lưu trong `screenshots/`):**
  - [x] Dashboard Grafana khi đang có tải (thấy rõ 4 Golden Signals): `screenshots/grafana-dashboard.png`
  - [x] Một trace chậm trong Jaeger (thấy span `chat mock-llm-large` chiếm 98.9% thời gian): `screenshots/jaeger-slow-trace.png`
  - [x] Một trace lỗi trong Jaeger (có event `exception` từ lỗi 503): `screenshots/jaeger-error-trace.png`
  - [x] Trang Alerts của Prometheus với 2 alert đang cùng **firing** (`AgentHighErrorRate` & `LLMCostBurnRateHigh`): `screenshots/prometheus-alert-firing.png`

### 4.2 Thí nghiệm "phá hệ thống"

Áp dụng đồng thời thí nghiệm **A** (`MOCK_ERROR_RATE=0.2`) và **C** (`LLM_MODEL=mock-llm-large`) qua file `.env` tạm trong `production/`, chạy `docker compose -p k5-day14-observability up -d --scale agent=2` cùng tải Locust liên tục (30 users, ramp-up 5):

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`critical`, error rate thực đo `19.4%–19.55%` > 5%) | **95 giây** (`pending` ở giây thứ `32`, chuyển `firing` ở giây thứ `95`, khớp điều kiện `for: 1m`) | **Error rate** (hàng Golden Signals chuyển đỏ) & **LLM calls ok/error** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`warning`, tốc độ chi tiêu tăng vọt lên **`11.09 → 13.95 USD/giờ`** > `2 USD/giờ`) | Đã `firing` ngay từ giây thứ **19** sau khi reload (do `rate(...[5m])` đã vượt `2 USD/giờ` từ phiên benchmark 100 users liền trước; chuyển sang `mock-llm-large` đẩy burn rate vọt mạnh lên `13.95 USD/giờ`; từ trạng thái lạnh sẽ mất `for: 2m` ≈ ~130–145s) | **Cost USD/giờ** & **LLM p95 latency** (hàng LLM) |
| D *(phân tích thêm)* | `docker pause` 1 instance | `AgentInstanceDown` (`up{job="agent"} == 0` với `for: 30s`) | Không chạy trực tiếp trong phiên này; lưu ý: lỗi `504 Gateway Timeout` khi container bị pause xảy ra ở tầng **Nginx** (request không hoàn tất trên agent) nên **không hiện trên panel Error rate của agent** — production cần giám sát thêm metric ở tầng Load Balancer / synthetic probe ngoài. | **Instances up** |
| E *(phân tích)* | `AGENT_VERSION=v1` | Không có alert hạ tầng nào firing | — | **Retrieval hit ratio** giảm về 0, **Tokens/s** giảm, bảng **Agent version** đổi sang `v1` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Các alert hạ tầng (error rate, latency, instance down, cost) vẫn xanh vì agent v1 vẫn trả HTTP `200 OK` nhanh và thậm chí rẻ hơn. Để phát hiện sự cố suy giảm chất lượng trả lời trong production, cần kết hợp:
1. **CI/CD Quality Gate trước khi deploy:** chạy `eval/run_eval.py` trên golden dataset và so sánh với baseline (`--baseline`), chặn merge/deploy ngay nếu accuracy tụt hoặc có regression.
2. **Giám sát tín hiệu nghiệp vụ/RAG (domain metrics):** đặt alert khi `retrieval_hit_ratio` tụt bất thường (về 0 như khi tắt RAG) hoặc `agent_info{version=...}` thay đổi ngoài kế hoạch.
3. **Online Evaluation & User Feedback:** lấy mẫu traffic thật (sampling) để chấm tự động bằng LLM-as-judge định kỳ, kết hợp theo dõi tỉ lệ phản hồi tiêu cực (thumbs-down / retry câu hỏi) từ người dùng.

### 4.3 Debug bằng trace

**1. Trace chậm nhất tìm được trong Jaeger (`http://localhost:16686/trace/5d992beda3602a4bd2454d09923db2a6`):**

- `trace_id`: `5d992beda3602a4bd2454d09923db2a6`
- Tổng thời gian (`POST /ask`): **2014.9 ms** (`agent.run`: `2011.2 ms` = `99.8%`, `agent.retrieve_context`: `17.7 ms` = `0.9%`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-large`** (**1993.2 ms**, **98.9%**) → xác nhận nút thắt nằm ở lời gọi LLM upstream (tail latency + hệ số model lớn), không phải code FastAPI hay bước retrieval.
- Dòng log JSON tương ứng (grep theo `trace_id` trong `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-26T08:45:40.815764+00:00", "level": "INFO", "service": "observable-agent", "instance": "ad29b137f431", "event": "llm_call", "trace_id": "5d992beda3602a4bd2454d09923db2a6", "span_id": "ef907fbeda3de9f3", "request_id": "f620ff35779d", "model": "mock-llm-large", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 0.000788, "llm_ms": 1993.3}
{"ts": "2026-11-26T08:45:40.816263+00:00", "level": "INFO", "service": "observable-agent", "instance": "ad29b137f431", "event": "http_request", "trace_id": "5d992beda3602a4bd2454d09923db2a6", "span_id": "ef907fbeda3de9f3", "request_id": "f620ff35779d", "method": "POST", "route": "/ask", "status": 200, "ms": 2013.9}
```

**2. Trace lỗi (`llm_error`) đối chiếu trong Jaeger (`http://localhost:16686/trace/a327485a305e698b149141ef9d3c4ada`):**

- `trace_id`: `a327485a305e698b149141ef9d3c4ada` (tổng thời gian `241.8 ms`, span `chat mock-llm-large`: `216.0 ms`, `agent.retrieve_context`: `23.3 ms`)
- Dòng log JSON `llm_error` khớp `trace_id`:

```json
{"ts": "2026-11-26T08:46:57.753281+00:00", "level": "INFO", "service": "observable-agent", "instance": "53d7297b62b7", "event": "llm_error", "trace_id": "a327485a305e698b149141ef9d3c4ada", "span_id": "123270ae776e9586", "request_id": "e1294be29933", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn: `benchmark-results/scale_1_stats.csv` (1 instance) và `benchmark-results/scale_3_stats.csv` (3 instances, chạy kèm `--no-deps` để giữ chính xác số replica). Bảng ghi số liệu của endpoint chính **`POST /ask`** (kèm giá trị dòng `Aggregated` trong ngoặc để đối chiếu trực tiếp với CSV):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 61.88 *(Agg: 68.26)* | 200 *(Agg: 200)* | 500 *(Agg: 480)* | 1700 *(Agg: 1700)* | 91 / 6969 = 1.31% *(Agg: 91 / 7687 = 1.18%)* |
| 3 | 62.28 *(Agg: 68.41)* | 200 *(Agg: 200)* | 360 *(Agg: 340)* | 1700 *(Agg: 1700)* | 71 / 7078 = 1.00% *(Agg: 71 / 7774 = 0.91%)* |

**Giải thích kết quả:**
- **Scale từ 1 lên 3 instance có cải thiện p95** (giảm từ `500 ms → 360 ms` trên `/ask`, tức giảm ~28%, và `Aggregated` từ `480 ms → 340 ms`) vì mỗi container bị giới hạn `0.5 CPU`; khi chia tải đều ra 3 container (~`21.4 req/s` mỗi container thay vì ~`62 req/s` dồn vào 1 container), thời gian xếp hàng và tranh chấp CPU/event-loop giảm đáng kể.
- **Tuy nhiên RPS (`~62 req/s` `/ask`, `~68 req/s` tổng), p50 (`200 ms`) và p99 (`1700 ms`) gần như không đổi.** Nút thắt nằm ở **hai phía ngoài tầng agent**:
  1. **Upstream LLM latency (I/O-bound):** bản thân mỗi lời gọi LLM mất tối thiểu ~120–180 ms (+ ~20 ms retrieval) và ~3% request bị tail latency +1500 ms (~1700 ms). Thêm bao nhiêu container agent cũng không làm LLM trả lời nhanh hơn.
  2. **Lưu lượng phát sinh từ Locust:** 100 users có `wait_time = between(0.5, 2)` (trung bình ~1.25s nghỉ + ~0.25s chờ response ≈ 1.5s/vòng) nên tải đầu vào tự nhiên chỉ đạt tối đa ~`100 / 1.5 ≈ 67–68 req/s`.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Đo đúng chỉ số thay vì nhìn trung bình:** `average` che giấu tail latency (`p95`/`p99`), còn `cost / câu đúng` phản ánh đúng giá trị thực tế hơn `cost / câu` khi so sánh các phiên bản agent (v2 tốn gấp đôi token nhưng rẻ hơn ~12× trên mỗi câu đúng).
  2. **Liên kết 3 trụ cột Metrics → Traces → Logs giúp debug cực nhanh:** Grafana/Prometheus cho biết *hệ thống đang lỗi hay chậm lúc nào*, Jaeger chỉ ra chính xác *span nào chiếm 98.9% thời gian*, và `trace_id` giúp grep ngay dòng JSON log chi tiết của đúng request đó.
  3. **Hạ tầng xanh không đồng nghĩa chất lượng tốt:** Observability hạ tầng không bắt được lỗi giảm chất lượng trả lời (thí nghiệm E) và không thấy lỗi xảy ra trước tầng app (504 tại Nginx); cần kết hợp eval chất lượng (golden dataset + quality gate trong CI) và giám sát cả tầng edge/load balancer.
- **Nếu đưa agent này lên production thật, sẽ thêm các metric / alert sau:**
  - **Nginx / Load Balancer metrics:** `nginx_http_requests_total{status=~"5.."}` (bắt `502`/`504` khi agent treo hoặc quá tải) và synthetic uptime check từ bên ngoài.
  - **Security & Cost protection metrics:** counter theo dõi số request bị chặn `401` (brute-force/key lỗi), `429` (rate limit), `402` (vượt budget) và alert khi đột biến.
  - **Redis & dependency metrics:** latency `redis_command_duration_seconds`, tỉ lệ lỗi kết nối Redis và cảnh báo sớm khi dung lượng bộ nhớ Redis > 80%.
  - **AI quality & RAG metrics:** alert khi `retrieval_hit_ratio` giảm dưới ngưỡng (vd < 70%), điểm đánh giá online LLM-as-judge tụt, hoặc tỉ lệ người dùng bấm dislike tăng đột biến.
