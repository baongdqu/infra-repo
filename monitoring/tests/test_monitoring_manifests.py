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


def test_servicemonitor_matches_backend_contract():
    sm = load_yaml("servicemonitor-backend.yaml")
    assert sm["kind"] == "ServiceMonitor"
    assert sm["metadata"]["labels"]["release"] == "kube-prometheus-stack"
    assert sm["spec"]["selector"]["matchLabels"]["app"] == "backend"
    assert set(sm["spec"]["namespaceSelector"]["matchNames"]) == {"dev", "production"}
    endpoint = sm["spec"]["endpoints"][0]
    assert endpoint["port"] == "http"
    assert endpoint["path"] == "/metrics"


def test_prometheus_alert_rules_cover_required_incidents():
    rules_doc = load_yaml("alert-rules.yaml")
    assert rules_doc["kind"] == "PrometheusRule"
    assert rules_doc["metadata"]["labels"]["release"] == "kube-prometheus-stack"
    rules = [r["alert"] for g in rules_doc["spec"]["groups"] for r in g["rules"]]
    required = {
        "PodCrashLoopBackOff",
        "PodOOMKilled",
        "PodImagePullBackOff",
        "HighCpuUsage",
        "HighMemoryUsage",
    }
    assert required.issubset(set(rules))


def test_grafana_dashboards_are_valid_json():
    for name in ("app-metrics-dashboard.json", "loki-logs-dashboard.json"):
        dashboard = load_json(f"grafana-dashboards/{name}")
        assert "panels" in dashboard and len(dashboard["panels"]) >= 4
        assert "title" in dashboard and dashboard["title"]


def test_argocd_reference_apps_are_valid():
    mon_apps = load_all_yaml("argocd-apps/07-monitoring.yaml")
    assert len(mon_apps) >= 1
    assert all(app["kind"] == "Application" for app in mon_apps)

    aiops_app = load_yaml("argocd-apps/08-aiops-bot.yaml")
    assert aiops_app["kind"] == "Application"
    assert aiops_app["spec"]["destination"]["namespace"] == "aiops"
    assert aiops_app["spec"]["source"]["path"] == "aiops-bot/k8s"
