import time
from typing import Any
import httpx


class LokiClient:
    """Queries Grafana Loki HTTP API for recent container logs."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _extract_lines(self, payload: dict[str, Any], max_chars: int = 1500) -> str:
        streams = payload.get("data", {}).get("result", [])
        entries: list[tuple[int, str]] = []
        for stream in streams:
            for ts_str, line in stream.get("values", []):
                try:
                    ts = int(ts_str)
                except (TypeError, ValueError):
                    ts = 0
                entries.append((ts, str(line).strip()))

        if not entries:
            return "No application logs found in Loki (pod may not have started container yet)."

        entries.sort(key=lambda item: item[0])
        joined = "\n".join(line for _, line in entries if line)
        if len(joined) > max_chars:
            return "...[truncated]\n" + joined[-max_chars:]
        return joined

    async def fetch_pod_logs(
        self,
        namespace: str,
        pod: str,
        lookback_minutes: int = 10,
        limit: int = 50,
    ) -> str:
        if not pod or pod == "unknown":
            return "No application logs found in Loki (pod name unknown)."

        end_ns = int(time.time() * 1e9)
        start_ns = end_ns - int(lookback_minutes * 60 * 1e9)
        logql = f'{{namespace="{namespace}", pod="{pod}"}}'
        params = {
            "query": logql,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": str(limit),
            "direction": "backward",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/loki/api/v1/query_range",
                    params=params,
                )
                resp.raise_for_status()
                return self._extract_lines(resp.json())
        except Exception as exc:
            return f"No application logs available (Loki query failed: {exc})."
