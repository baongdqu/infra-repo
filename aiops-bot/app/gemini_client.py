import httpx
from app.models import AlertItem, K8sPodContext


class GeminiAnalyzer:
    """Calls Google Gemini (gemini-2.5-flash) to perform Root Cause Analysis (RCA)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout

    def _build_prompt(
        self, alert: AlertItem, k8s_ctx: K8sPodContext, logs: str
    ) -> str:
        events_str = "\n".join(k8s_ctx.events) if k8s_ctx.events else "None"
        return (
            "Bạn là chuyên gia SRE/DevSecOps Kubernetes. Hãy phân tích sự cố sau và trả lời ngắn gọn bằng tiếng Việt "
            "theo 3 mục: (1) Nguyên nhân gốc rễ (Root Cause), (2) Bằng chứng từ K8s Events & Logs, "
            "(3) Các lệnh kubectl / bước khắc phục cụ thể.\n\n"
            f"--- ALERT ---\n"
            f"Alert: {alert.alertname} (Severity: {alert.severity})\n"
            f"Namespace: {alert.namespace} | Pod: {alert.pod}\n"
            f"Summary: {alert.summary}\n"
            f"Description: {alert.description}\n\n"
            f"--- KUBERNETES STATUS & EVENTS ---\n"
            f"Phase: {k8s_ctx.pod_phase} | Waiting: {k8s_ctx.waiting_reason} | "
            f"Terminated: {k8s_ctx.terminated_reason} (exit_code={k8s_ctx.exit_code}) | "
            f"Restarts: {k8s_ctx.restart_count}\n"
            f"Events:\n{events_str}\n\n"
            f"--- LOKI LOGS (Last 10m) ---\n{logs}\n"
        )

    def _fallback_rca(
        self,
        alert: AlertItem,
        k8s_ctx: K8sPodContext,
        logs: str,
        reason: str = "Gemini API key not configured",
    ) -> str:
        symptom = (
            k8s_ctx.terminated_reason
            or k8s_ctx.waiting_reason
            or alert.alertname
        )
        log_tail = logs[-250:] if len(logs) > 250 else logs
        return (
            f"[Fallback RCA - {reason}]\n"
            f"1. Nguyên nhân gốc rễ: Phát hiện cảnh báo {alert.alertname} trên pod "
            f"{alert.namespace}/{alert.pod} (trạng thái: {symptom}, exit_code={k8s_ctx.exit_code}, "
            f"restarts={k8s_ctx.restart_count}).\n"
            f"2. Bằng chứng: K8s Phase={k8s_ctx.pod_phase}; Log snippet: {log_tail}\n"
            f"3. Khắc phục đề xuất:\n"
            f"   - Kiểm tra chi tiết pod: `kubectl describe pod {alert.pod} -n {alert.namespace}`\n"
            f"   - Xem log container trước khi crash: `kubectl logs {alert.pod} -n {alert.namespace} --previous`"
        )

    @staticmethod
    def _sanitize_error(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            return f"HTTP {exc.response.status_code}"
        if isinstance(exc, httpx.TimeoutException):
            return "Request Timeout"
        return exc.__class__.__name__

    async def analyze_root_cause(
        self, alert: AlertItem, k8s_ctx: K8sPodContext, logs: str
    ) -> str:
        if not self.api_key:
            return self._fallback_rca(alert, k8s_ctx, logs)

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": self._build_prompt(alert, k8s_ctx, logs)}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1500,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    url,
                    headers={"x-goog-api-key": self.api_key},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = (
                        candidates[0]
                        .get("content", {})
                        .get("parts", [])
                    )
                    text = "".join(p.get("text", "") for p in parts).strip()
                    if text:
                        return text
                return self._fallback_rca(
                    alert, k8s_ctx, logs, reason="Empty Gemini candidate response"
                )
        except Exception as exc:
            safe_reason = f"Gemini API error ({self._sanitize_error(exc)})"
            return self._fallback_rca(
                alert, k8s_ctx, logs, reason=safe_reason
            )
