from kubernetes import client, config
from app.models import K8sPodContext


class K8sClient:
    """Read-only Kubernetes API collector for Pod status, termination reasons, and Warning events."""

    def __init__(self, enabled: bool = True, request_timeout: int = 5) -> None:
        self.enabled = enabled
        self.request_timeout = request_timeout
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
        except Exception as exc:
            return K8sPodContext(
                pod_phase="Unknown",
                error=f"Kubernetes API context unavailable: {exc}",
            )

        phase = "Unknown"
        waiting_reason: str | None = None
        terminated_reason: str | None = None
        exit_code: int | None = None
        restart_count = 0
        pod_error: str | None = None

        try:
            pod_obj = api.read_namespaced_pod(
                name=pod,
                namespace=namespace,
                _request_timeout=self.request_timeout,
            )
            phase = getattr(pod_obj.status, "phase", "Unknown") or "Unknown"
            init_statuses = (
                getattr(pod_obj.status, "init_container_statuses", None) or []
            )
            app_statuses = (
                getattr(pod_obj.status, "container_statuses", None) or []
            )
            for cs in list(init_statuses) + list(app_statuses):
                restart_count += int(getattr(cs, "restart_count", 0) or 0)
                state = getattr(cs, "state", None)
                if state and getattr(state, "waiting", None):
                    waiting_reason = state.waiting.reason or waiting_reason
                if state and getattr(state, "terminated", None):
                    terminated_reason = (
                        state.terminated.reason or terminated_reason
                    )
                    exit_code = state.terminated.exit_code

                last_state = getattr(cs, "last_state", None)
                if last_state and getattr(last_state, "terminated", None):
                    terminated_reason = (
                        terminated_reason or last_state.terminated.reason
                    )
                    if exit_code is None:
                        exit_code = last_state.terminated.exit_code
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                phase = "NotFound"
                pod_error = f"Pod {namespace}/{pod} not found (may have been replaced)."
            else:
                return K8sPodContext(
                    pod_phase="Unknown",
                    error=f"Kubernetes API context unavailable: {exc}",
                )

        formatted_events: list[str] = []
        try:
            events_list = api.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod}",
                _request_timeout=self.request_timeout,
            )
            raw_items = list(events_list.items or [])
            # Prioritize Warning events before Normal events while preserving order
            warnings = [
                ev
                for ev in raw_items
                if getattr(ev, "type", "Normal") == "Warning"
            ]
            normals = [
                ev
                for ev in raw_items
                if getattr(ev, "type", "Normal") != "Warning"
            ]
            selected = (warnings[-5:] + normals[-5:])[:5]
            for ev in selected:
                ev_type = getattr(ev, "type", "Normal")
                reason = getattr(ev, "reason", "")
                message = getattr(ev, "message", "")
                formatted_events.append(f"[{ev_type}] {reason}: {message}")
        except Exception as exc:
            if not pod_error:
                pod_error = f"Failed to list pod events: {exc}"

        return K8sPodContext(
            pod_phase=phase,
            waiting_reason=waiting_reason,
            terminated_reason=terminated_reason,
            exit_code=exit_code,
            restart_count=restart_count,
            events=formatted_events,
            error=pod_error,
        )
