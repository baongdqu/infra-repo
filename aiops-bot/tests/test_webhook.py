import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.main import create_app


def _make_test_client() -> TestClient:
    settings = Settings(
        loki_url="http://127.0.0.1:59999",
        gemini_api_key="",
        gemini_model="gemini-2.5-flash",
        cooldown_seconds=900,
        k8s_enabled=False,
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_health_and_ready_endpoints():
    client = _make_test_client()
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_ready = client.get("/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["model"] == "gemini-2.5-flash"


def test_webhook_processes_firing_and_deduplicates_cooldown():
    client = _make_test_client()
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "PodCrashLoopBackOff",
                    "namespace": "dev",
                    "pod": "backend-7d89f",
                    "severity": "critical",
                },
                "annotations": {
                    "summary": "Pod dev/backend-7d89f is in CrashLoopBackOff"
                },
            }
        ],
    }

    resp1 = client.post("/webhook", json=payload)
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1["processed"] == 1
    assert body1["skipped_cooldown"] == 0
    assert body1["skipped_resolved"] == 0
    assert "PodCrashLoopBackOff" in body1["results"][0]["rca"]

    # Immediate duplicate must be suppressed by cooldown cache
    resp2 = client.post("/webhook", json=payload)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["processed"] == 0
    assert body2["skipped_cooldown"] == 1


def test_webhook_skips_resolved_alerts():
    client = _make_test_client()
    payload = {
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "PodOOMKilled",
                    "namespace": "production",
                    "pod": "backend-prod-1",
                },
            }
        ],
    }

    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["processed"] == 0
    assert body["skipped_resolved"] == 1
