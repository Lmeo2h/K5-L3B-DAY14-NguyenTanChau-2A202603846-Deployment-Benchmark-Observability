# Deployment Information — Day 14 (Part 3 & Part 6)

## Public URL
https://k5-l3b-day14-nguyentanchau-2a202603846.onrender.com

## Platform
Render (Web Service `runtime: docker` từ `06-lab-complete/Dockerfile`, kết nối Managed Redis trên cloud)

## Source Directory Deployed
`06-lab-complete/` (build multi-stage `python:3.11-slim`, cấu hình `render.yaml` / `railway.toml`)

## Environment Variables Set (cấu hình trên Render Dashboard — không commit giá trị thật)
- `PORT` *(Render tự cấp)*
- `ENVIRONMENT=production`
- `REDIS_URL` *(kết nối Redis service trên cloud)*
- `AGENT_API_KEY=k5-day14-****` *(secret cấu hình qua dashboard, đã che)*
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `LOG_LEVEL=INFO`

## Test Commands (4 lệnh tự kiểm CP6)

```bash
export BASE="https://k5-l3b-day14-nguyentanchau-2a202603846.onrender.com"
export AGENT_API_KEY="k5-day14-****"   # thay bằng key thật cấu hình trên Render

# 1. Health check (liveness) — mong đợi: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness check (kiểm tra kết nối Redis trên cloud) — mong đợi: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Authentication required (không gửi X-API-Key) — mong đợi: 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'

# 4. Authenticated request (có X-API-Key hợp lệ) — mong đợi: 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"user_id":"test","question":"Hello"}'
```

### Kết quả kiểm tra thực tế (đã chạy trên Public URL)

```text
GET  /health               -> 200
GET  /ready                -> 200
POST /ask (no X-API-Key)   -> 401
POST /ask (X-API-Key: k5-day14-****) -> 200
```

**Chi tiết JSON response thực tế:**

```json
// GET /health
{"status":"ok","environment":"production","uptime_seconds":4.2}

// GET /ready
{"ready":true,"redis":"ok"}

// POST /ask (X-API-Key: k5-day14-****)
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"input_tokens":2,"output_tokens":17,"cost_usd":1.05e-05}}
```

### Kết quả `check_production_ready.py --public-url`

```bash
cd 06-lab-complete
AGENT_API_KEY="k5-day14-****" .venv/bin/python check_production_ready.py \
  --public-url "https://k5-l3b-day14-nguyentanchau-2a202603846.onrender.com"
```

```text
✅ Public URL: GET https://k5-l3b-day14-nguyentanchau-2a202603846.onrender.com/health → 200
Result: 12/12 tiêu chí đạt · 44/44 checks passed
🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
