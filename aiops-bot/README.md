# 🤖 AIOps RCA Bot & Observability Stack (Part 4)

Dịch vụ phân tích nguyên nhân gốc rễ tự động (**AI-Powered Root Cause Analysis**) kết hợp **Prometheus Alertmanager**, **Grafana Loki (`SingleBinary`)**, **Kubernetes Events API**, và **Google Gemini (`gemini-2.5-flash`)**.

## 🔄 Luồng Hoạt Động

1. **Prometheus** phát hiện sự cố qua `PrometheusRule` (`PodCrashLoopBackOff`, `PodOOMKilled`, `PodImagePullBackOff`, `HighCpuUsage`, `HighMemoryUsage`).
2. **Alertmanager** gom nhóm cảnh báo (`group_wait: 30s`, `repeat_interval: 15m`) và bắn webhook nội bộ tới `http://aiops-bot.aiops.svc.cluster.local:8000/webhook`.
3. **AIOps Bot**:
   - Kiểm tra **Cooldown Cache (TTL 15 phút)** theo bộ khóa `(alertname, namespace, pod)` để chống bão cảnh báo và bảo vệ quota Gemini.
   - Truy vấn **Loki HTTP API** lấy log container 10 phút gần nhất.
   - Truy vấn **Kubernetes API** (qua `ServiceAccount` read-only) lấy trạng thái Pod, `waiting.reason`, `terminated.reason` (`OOMKilled`, `exit_code=137`) và các `Warning` Events.
   - Gọi **Google Gemini (`gemini-2.5-flash`)** phân tích RCA có cấu trúc bằng tiếng Việt và gửi báo cáo tới **Telegram / Discord**.

## 🧪 Kiểm Thử Độc Lập Tại Local

```bash
# 1. Chạy bộ Unit & Integration Tests
pytest ../monitoring/tests/ tests/ -v

# 2. Khởi chạy stack local (AIOps Bot + Loki)
docker compose up --build -d

# 3. Giả lập bắn webhook từ Alertmanager vào Bot
python scripts/send_mock_alert.py --scenario crashloop
python scripts/send_mock_alert.py --scenario oom
python scripts/send_mock_alert.py --scenario imagepull
```
