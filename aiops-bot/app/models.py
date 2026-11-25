from typing import Any
from pydantic import BaseModel, Field


class AlertItem(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    endsAt: str | None = None

    @property
    def alertname(self) -> str:
        return self.labels.get("alertname", "UnknownAlert")

    @property
    def namespace(self) -> str:
        return self.labels.get("namespace", "default")

    @property
    def pod(self) -> str:
        return (
            self.labels.get("pod")
            or self.labels.get("pod_name")
            or self.labels.get("instance")
            or "unknown"
        )

    @property
    def severity(self) -> str:
        return self.labels.get("severity", "warning")

    @property
    def summary(self) -> str:
        return self.annotations.get("summary", self.alertname)

    @property
    def description(self) -> str:
        return self.annotations.get("description", "")


class AlertmanagerPayload(BaseModel):
    version: str = "4"
    status: str = "firing"
    receiver: str = "aiops-bot-webhook"
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    alerts: list[AlertItem] = Field(default_factory=list)


class K8sPodContext(BaseModel):
    pod_phase: str = "Unknown"
    waiting_reason: str | None = None
    terminated_reason: str | None = None
    exit_code: int | None = None
    restart_count: int = 0
    events: list[str] = Field(default_factory=list)
    error: str | None = None


class WebhookResponse(BaseModel):
    processed: int = 0
    skipped_cooldown: int = 0
    skipped_resolved: int = 0
    results: list[dict[str, Any]] = Field(default_factory=list)
