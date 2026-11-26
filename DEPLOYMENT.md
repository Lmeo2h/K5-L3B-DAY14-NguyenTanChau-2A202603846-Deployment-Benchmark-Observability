# Deployment Information — Day 14 (Part 3 & Part 6)

## Public URL
https://<your-deployed-agent-url>

## Platform
Railway *(hoặc Render — giữ lại nền tảng bạn deploy)*

## Source Directory Deployed
`06-lab-complete/` (build từ `Dockerfile` multi-stage, dùng cấu hình `railway.toml` / `render.yaml`)

## Environment Variables Set (trên Platform Dashboard — không commit giá trị thật)
- `PORT` *(platform tự cấp)*
- `ENVIRONMENT=production`
- `REDIS_URL` *(trỏ tới managed Redis service trên cùng nền tảng)*
- `AGENT_API_KEY` *(secret cấu hình qua dashboard/CLI, không ghi vào code)*
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `LOG_LEVEL=INFO`

## Test Commands (4 lệnh tự kiểm CP6)

Đặt `BASE` là Public URL ở trên và `AGENT_API_KEY` là key đã cấu hình trên nền tảng:

```bash
export BASE="https://<your-deployed-agent-url>"
export AGENT_API_KEY="<YOUR_API_KEY>"

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

### Kết quả kiểm tra thực tế (dán output 4 lệnh trên)

```text
# /health      -> 200
# /ready       -> 200
# /ask (no key)-> 401
# /ask (valid) -> 200
```

### Kiểm tra chi tiết JSON response (tùy chọn, đã che key)

```bash
curl -s "$BASE/health"
curl -s "$BASE/ready"
curl -s -X POST "$BASE/ask" \
  -H "X-API-Key: <REDACTED>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
```

```bash
# Kiểm tra bổ sung bằng script chấm:
cd 06-lab-complete
.venv/bin/python check_production_ready.py --public-url "$BASE"
```

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
