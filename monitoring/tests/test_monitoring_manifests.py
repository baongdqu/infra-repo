from pathlib import Path
import json
import yaml

MONITORING_DIR = Path(__file__).resolve().parent.parent


def load_yaml(rel_path: str) -> dict:
    path = MONITORING_DIR / rel_path
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_all_yaml(rel_path: str) -> list[dict]:
    path = MONITORING_DIR / rel_path
    with path.open("r", encoding="utf-8") as f:
        return [doc for doc in yaml.safe_load_all(f) if doc is not None]


def load_json(rel_path: str) -> dict:
    path = MONITORING_DIR / rel_path
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_kube_prometheus_stack_values_constraints():
    data = load_yaml("kube-prometheus-stack-values.yaml")
    prom_spec = data["prometheus"]["prometheusSpec"]
    assert prom_spec["retention"] == "2d"
    assert prom_spec["resources"]["limits"]["memory"] == "1Gi"
    assert prom_spec["serviceMonitorSelectorNilUsesHelmValues"] is False
    assert prom_spec["ruleSelectorNilUsesHelmValues"] is False

    am_cfg = data["alertmanager"]["config"]
    assert am_cfg["route"]["group_wait"] == "30s"
    assert am_cfg["route"]["repeat_interval"] == "15m"
    receivers = am_cfg["receivers"]
    aiops_receiver = next(r for r in receivers if r["name"] == "aiops-bot-webhook")
    assert (
        aiops_receiver["webhook_configs"][0]["url"]
        == "http://aiops-bot.aiops.svc.cluster.local:8000/webhook"
    )
    assert aiops_receiver["webhook_configs"][0]["send_resolved"] is False


def test_loki_singlebinary_values_constraints():
    data = load_yaml("loki-singlebinary-values.yaml")
    assert data["deploymentMode"] == "SingleBinary"
    assert data["singleBinary"]["replicas"] == 1
    assert data["loki"]["limits_config"]["retention_period"] == "72h"
    assert data["backend"]["replicas"] == 0
    assert data["read"]["replicas"] == 0
    assert data["write"]["replicas"] == 0
    assert data["chunksCache"]["enabled"] is False
    assert data["resultsCache"]["enabled"] is False


def test_promtail_values_constraints():
    data = load_yaml("promtail-values.yaml")
    clients = data["config"]["clients"]
    assert (
        clients[0]["url"]
        == "http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push"
    )
    assert "limits" in data["resources"]
    assert "requests" in data["resources"]
