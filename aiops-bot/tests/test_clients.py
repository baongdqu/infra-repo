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
