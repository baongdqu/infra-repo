import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.cooldown import CooldownCache
from app.models import AlertItem, AlertmanagerPayload, K8sPodContext


def test_cooldown_blocks_duplicate_within_ttl():
    clock = [1000.0]
    cache = CooldownCache(ttl_seconds=900, time_fn=lambda: clock[0])
    assert cache.should_process("PodCrashLoopBackOff", "dev", "backend-abc") is True
    assert cache.should_process("PodCrashLoopBackOff", "dev", "backend-abc") is False
    clock[0] += 901.0
    assert cache.should_process("PodCrashLoopBackOff", "dev", "backend-abc") is True


def test_cooldown_isolates_different_pods_or_alerts():
    cache = CooldownCache(ttl_seconds=900)
    assert cache.should_process("PodCrashLoopBackOff", "dev", "backend-1") is True
    assert cache.should_process("PodCrashLoopBackOff", "dev", "backend-2") is True
    assert cache.should_process("PodOOMKilled", "dev", "backend-1") is True


def test_alertmanager_payload_extracts_labels_with_defaults():
    payload = AlertmanagerPayload.model_validate(
        {
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "PodOOMKilled",
                        "namespace": "production",
                        "pod": "backend-xyz",
                        "severity": "critical",
                    },
                    "annotations": {
                        "summary": "Pod production/backend-xyz was OOMKilled",
                        "description": "Exceeded memory limit",
                    },
                }
            ],
        }
    )
    alert = payload.alerts[0]
    assert alert.alertname == "PodOOMKilled"
    assert alert.namespace == "production"
    assert alert.pod == "backend-xyz"
    assert alert.severity == "critical"
    assert "OOMKilled" in alert.summary


def test_settings_defaults_match_spec():
    settings = Settings()
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.cooldown_seconds == 900
    assert "loki.monitoring.svc.cluster.local:3100" in settings.loki_url
