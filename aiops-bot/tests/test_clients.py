import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gemini_client import GeminiAnalyzer
from app.k8s_client import K8sClient
from app.loki_client import LokiClient
from app.models import AlertItem, K8sPodContext
from app.notifier import Notifier


@pytest.mark.asyncio
async def test_loki_client_returns_fallback_when_unreachable():
    client = LokiClient(base_url="http://127.0.0.1:59999", timeout=0.5)
    logs = await client.fetch_pod_logs("dev", "backend-imgpull")
    assert "No application logs" in logs or "unavailable" in logs.lower()


@pytest.mark.asyncio
async def test_loki_client_parses_streams_and_handles_empty():
    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return self._payload

    client = LokiClient(base_url="http://loki:3100")
    parsed = client._extract_lines(
        {
            "data": {
                "result": [
                    {
                        "values": [
                            ["1700000002000000000", "ERROR: Database connection refused"],
                            ["1700000001000000000", "INFO: Starting NestJS server"],
                        ]
                    }
                ]
            }
        }
    )
    assert "INFO: Starting NestJS server" in parsed
    assert "ERROR: Database connection refused" in parsed
    assert parsed.index("INFO:") < parsed.index("ERROR:")

    empty_parsed = client._extract_lines({"data": {"result": []}})
    assert "No application logs found in Loki" in empty_parsed


def test_k8s_client_degrades_gracefully_outside_cluster():
    k8s = K8sClient(enabled=False)
    ctx = k8s.fetch_pod_context("dev", "backend-123")
    assert ctx.pod_phase == "Unknown"
    assert ctx.error is not None


@pytest.mark.asyncio
async def test_gemini_analyzer_fallback_on_missing_key_or_api_error():
    analyzer = GeminiAnalyzer(api_key="", model="gemini-2.5-flash")
    alert = AlertItem(
        status="firing",
        labels={
            "alertname": "PodOOMKilled",
            "namespace": "production",
            "pod": "backend-1",
            "severity": "critical",
        },
        annotations={"summary": "Pod production/backend-1 was OOMKilled"},
    )
    ctx = K8sPodContext(
        pod_phase="Running",
        terminated_reason="OOMKilled",
        exit_code=137,
        restart_count=3,
        events=["Warning BackOff: Back-off restarting failed container"],
    )
    rca = await analyzer.analyze_root_cause(
        alert, ctx, "FATAL ERROR: Reached heap limit Allocation failed"
    )
    assert "PodOOMKilled" in rca
    assert "OOMKilled" in rca
    assert "kubectl" in rca


def test_notifier_formats_and_truncates_within_telegram_limit():
    notifier = Notifier(
        telegram_token="",
        telegram_chat_id="",
        discord_webhook_url="",
    )
    alert = AlertItem(
        status="firing",
        labels={
            "alertname": "PodCrashLoopBackOff",
            "namespace": "dev",
            "pod": "backend-1",
            "severity": "critical",
        },
    )
    ctx = K8sPodContext(
        pod_phase="Running",
        waiting_reason="CrashLoopBackOff",
        restart_count=5,
        events=["Back-off restarting failed container"],
    )
    msg = notifier.format_message(
        alert,
        ctx,
        "ERROR_LINE_[unmatched*markdown_\n" * 400,
        "RCA_ANALYSIS_" * 400,
    )
    assert len(msg) <= 4000
    assert "PodCrashLoopBackOff" in msg
    assert "CrashLoopBackOff" in msg



@pytest.mark.asyncio
async def test_gemini_analyzer_does_not_leak_api_key_on_http_error_and_uses_log_tail(monkeypatch):
    import httpx

    secret_key = "AIzaSySECRET_KEY_DO_NOT_LEAK_12345"
    captured_headers = {}

    async def mock_post(self, url, **kwargs):
        captured_headers.update(kwargs.get("headers") or {})
        request = httpx.Request("POST", f"{url}?key={secret_key}")
        response = httpx.Response(429, request=request, text="Quota exceeded")
        raise httpx.HTTPStatusError(
            f"Client error '429 Too Many Requests' for url '{url}?key={secret_key}'",
            request=request,
            response=response,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    analyzer = GeminiAnalyzer(api_key=secret_key, model="gemini-2.5-flash")
    alert = AlertItem(
        status="firing",
        labels={"alertname": "PodOOMKilled", "namespace": "production", "pod": "backend-1"},
    )
    ctx = K8sPodContext(pod_phase="Running", terminated_reason="OOMKilled", exit_code=137)
    long_logs = ("OLD_HEAD_LOG\n" * 40) + "TAIL_FATAL_OOM_SIGNATURE"

    rca = await analyzer.analyze_root_cause(alert, ctx, long_logs)
    assert secret_key not in rca
    assert captured_headers.get("x-goog-api-key") == secret_key
    assert "TAIL_FATAL_OOM_SIGNATURE" in rca


def test_k8s_client_fetches_events_when_pod_not_found_and_prioritizes_warnings():
    class FakeEvent:
        def __init__(self, ev_type: str, reason: str, message: str) -> None:
            self.type = ev_type
            self.reason = reason
            self.message = message

    class FakeEventList:
        def __init__(self, items):
            self.items = items

    class FakeNotFoundError(Exception):
        status = 404

    class FakeCoreV1:
        def read_namespaced_pod(self, name: str, namespace: str, **kwargs):
            raise FakeNotFoundError("Pod not found")

        def list_namespaced_event(self, namespace: str, field_selector: str, **kwargs):
            return FakeEventList(
                [
                    FakeEvent("Normal", "Scheduled", "Successfully assigned"),
                    FakeEvent("Warning", "Failed", "Failed to pull image"),
                ]
            )

    k8s = K8sClient(enabled=True)
    k8s._core_v1 = FakeCoreV1()
    ctx = k8s.fetch_pod_context("dev", "deleted-pod-1")
    assert ctx.pod_phase == "NotFound"
    assert any("Failed to pull image" in e for e in ctx.events)
    assert ctx.events[0].startswith("[Warning]")


@pytest.mark.asyncio
async def test_notifier_discord_format_preserves_rca_section_and_sends(monkeypatch):
    import httpx

    sent_payloads = []

    async def mock_post(self, url, **kwargs):
        sent_payloads.append((url, kwargs.get("json", {})))
        return httpx.Response(204, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    notifier = Notifier(
        telegram_token="",
        telegram_chat_id="",
        discord_webhook_url="https://discord.com/api/webhooks/test/token",
    )
    alert = AlertItem(
        status="firing",
        labels={"alertname": "PodCrashLoopBackOff", "namespace": "dev", "pod": "backend-1"},
        annotations={"summary": "SUMMARY_" * 50},
    )
    ctx = K8sPodContext(
        pod_phase="Running",
        waiting_reason="CrashLoopBackOff",
        events=["EVENT_LINE_" * 30 for _ in range(4)],
    )
    ok = await notifier.send_report(
        alert,
        ctx,
        "LOG_LINE_" * 300,
        ("RCA_BODY_" * 60) + "GEMINI_RCA_TAIL_MARKER",
    )
    assert ok is True
    assert len(sent_payloads) == 1
    discord_content = sent_payloads[0][1]["content"]
    assert len(discord_content) <= 1900
    assert "🤖 [GEMINI 2.5 FLASH RCA]" in discord_content
    assert "GEMINI_RCA_TAIL_MARKER" in discord_content
