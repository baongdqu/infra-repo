from fastapi import FastAPI
from app.config import Settings
from app.cooldown import CooldownCache
from app.gemini_client import GeminiAnalyzer
from app.k8s_client import K8sClient
from app.loki_client import LokiClient
from app.models import AlertmanagerPayload, WebhookResponse
from app.notifier import Notifier


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()
    cooldown_cache = CooldownCache(ttl_seconds=cfg.cooldown_seconds)
    loki_client = LokiClient(base_url=cfg.loki_url)
    k8s_client = K8sClient(enabled=cfg.k8s_enabled)
    gemini_analyzer = GeminiAnalyzer(
        api_key=cfg.gemini_api_key,
        model=cfg.gemini_model,
    )
    notifier = Notifier(
        telegram_token=cfg.telegram_bot_token,
        telegram_chat_id=cfg.telegram_chat_id,
        discord_webhook_url=cfg.discord_webhook_url,
    )

    api = FastAPI(
        title="DevSecOps AIOps RCA Bot",
        version="1.0.0",
        description="Alertmanager Webhook -> Cooldown -> Loki + K8s Events -> Gemini 2.5 Flash RCA -> Telegram/Discord",
    )

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/ready")
    async def ready() -> dict[str, str]:
        return {
            "status": "ok",
            "model": cfg.gemini_model,
            "loki_url": cfg.loki_url,
        }

    @api.post("/webhook", response_model=WebhookResponse)
    async def alertmanager_webhook(
        payload: AlertmanagerPayload,
    ) -> WebhookResponse:
        response = WebhookResponse()

        for alert in payload.alerts:
            if payload.status == "resolved" or alert.status == "resolved":
                response.skipped_resolved += 1
                response.results.append(
                    {
                        "alertname": alert.alertname,
                        "namespace": alert.namespace,
                        "pod": alert.pod,
                        "action": "ignored_resolved",
                    }
                )
                continue

            if not cooldown_cache.should_process(
                alert.alertname, alert.namespace, alert.pod
            ):
                response.skipped_cooldown += 1
                response.results.append(
                    {
                        "alertname": alert.alertname,
                        "namespace": alert.namespace,
                        "pod": alert.pod,
                        "action": "cooldown_active",
                    }
                )
                continue

            logs = await loki_client.fetch_pod_logs(
                namespace=alert.namespace,
                pod=alert.pod,
            )
            k8s_ctx = k8s_client.fetch_pod_context(
                namespace=alert.namespace,
                pod=alert.pod,
            )
            rca = await gemini_analyzer.analyze_root_cause(
                alert=alert,
                k8s_ctx=k8s_ctx,
                logs=logs,
            )
            delivered = await notifier.send_report(
                alert=alert,
                k8s_ctx=k8s_ctx,
                logs=logs,
                rca=rca,
            )

            response.processed += 1
            response.results.append(
                {
                    "alertname": alert.alertname,
                    "namespace": alert.namespace,
                    "pod": alert.pod,
                    "action": "processed",
                    "delivered": delivered,
                    "k8s_phase": k8s_ctx.pod_phase,
                    "rca": rca,
                }
            )

        return response

    return api


app = create_app()
