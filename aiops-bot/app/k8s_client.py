from kubernetes import client, config
from app.models import K8sPodContext


class K8sClient:
    """Read-only Kubernetes API collector for Pod status, termination reasons, and Warning events."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._core_v1: client.CoreV1Api | None = None

    def _get_api(self) -> client.CoreV1Api:
        if self._core_v1 is not None:
            return self._core_v1
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self._core_v1 = client.CoreV1Api()
        return self._core_v1

    def fetch_pod_context(self, namespace: str, pod: str) -> K8sPodContext:
        if not self.enabled:
            return K8sPodContext(
                pod_phase="Unknown",
                error="Kubernetes API querying disabled (K8S_ENABLED=false).",
            )
        if not pod or pod == "unknown":
            return K8sPodContext(
                pod_phase="Unknown",
                error="No pod name present in alert labels.",
            )

        try:
            api = self._get_api()
            pod_obj = api.read_namespaced_pod(name=pod, namespace=namespace)
            phase = getattr(pod_obj.status, "phase", "Unknown") or "Unknown"
            waiting_reason: str | None = None
            terminated_reason: str | None = None
            exit_code: int | None = None
            restart_count = 0

            statuses = getattr(pod_obj.status, "container_statuses", None) or []
            for cs in statuses:
                restart_count += int(getattr(cs, "restart_count", 0) or 0)
                state = getattr(cs, "state", None)
                if state and getattr(state, "waiting", None):
                    waiting_reason = state.waiting.reason or waiting_reason
                if state and getattr(state, "terminated", None):
                    terminated_reason = state.terminated.reason or terminated_reason
                    exit_code = state.terminated.exit_code

                last_state = getattr(cs, "last_state", None)
                if last_state and getattr(last_state, "terminated", None):
                    terminated_reason = (
                        terminated_reason or last_state.terminated.reason
                    )
                    if exit_code is None:
                        exit_code = last_state.terminated.exit_code

            events_list = api.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod}",
            )
            formatted_events: list[str] = []
            for ev in (events_list.items or [])[-5:]:
                ev_type = getattr(ev, "type", "Normal")
                reason = getattr(ev, "reason", "")
                message = getattr(ev, "message", "")
                formatted_events.append(f"[{ev_type}] {reason}: {message}")

            return K8sPodContext(
                pod_phase=phase,
                waiting_reason=waiting_reason,
                terminated_reason=terminated_reason,
                exit_code=exit_code,
                restart_count=restart_count,
                events=formatted_events,
            )
        except Exception as exc:
            return K8sPodContext(
                pod_phase="Unknown",
                error=f"Kubernetes API context unavailable: {exc}",
            )
