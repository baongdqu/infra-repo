"""CLI utility to send mock Alertmanager v4 webhooks to the local AIOps RCA Bot."""

import argparse
import json
import urllib.request

SCENARIOS = {
    "crashloop": {
        "alertname": "PodCrashLoopBackOff",
        "namespace": "dev",
        "pod": "backend-7d89f-x9k2p",
        "severity": "critical",
        "summary": "Pod dev/backend-7d89f-x9k2p is in CrashLoopBackOff",
        "description": "Container backend in pod dev/backend-7d89f-x9k2p has been restarting repeatedly for over 1 minute.",
    },
    "oom": {
        "alertname": "PodOOMKilled",
        "namespace": "production",
        "pod": "backend-6f4b9-m4p1z",
        "severity": "critical",
        "summary": "Pod production/backend-6f4b9-m4p1z was OOMKilled",
        "description": "Container backend exceeded its 384Mi memory limit and terminated with OOMKilled (exit code 137).",
    },
    "imagepull": {
        "alertname": "PodImagePullBackOff",
        "namespace": "dev",
        "pod": "frontend-5c8a1-q7w8e",
        "severity": "critical",
        "summary": "Pod dev/frontend-5c8a1-q7w8e cannot pull container image",
        "description": "Container frontend is stuck in ImagePullBackOff.",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Send mock Alertmanager webhook to AIOps Bot.")
    parser.add_argument(
        "--url",
        default="http://localhost:8000/webhook",
        help="Target AIOps Bot webhook URL",
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default="crashloop",
        help="Incident scenario to simulate",
    )
    args = parser.parse_args()

    s = SCENARIOS[args.scenario]
    payload = {
        "version": "4",
        "status": "firing",
        "receiver": "aiops-bot-webhook",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": s["alertname"],
                    "namespace": s["namespace"],
                    "pod": s["pod"],
                    "severity": s["severity"],
                },
                "annotations": {
                    "summary": s["summary"],
                    "description": s["description"],
                },
            }
        ],
    }

    req = urllib.request.Request(
        args.url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        print(json.dumps(body, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
