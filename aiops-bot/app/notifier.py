import logging
import httpx
from app.models import AlertItem, K8sPodContext

logger = logging.getLogger("aiops_bot.notifier")


class Notifier:
    """Delivers formatted AIOps RCA alerts to Telegram and/or Discord."""

    TELEGRAM_MAX_LEN = 3900
    DISCORD_MAX_LEN = 1900

    def __init__(
        self,
        telegram_token: str = "",
        telegram_chat_id: str = "",
        discord_webhook_url: str = "",
        timeout: float = 10.0,
    ) -> None:
        self.telegram_token = telegram_token.strip()
        self.telegram_chat_id = telegram_chat_id.strip()
        self.discord_webhook_url = discord_webhook_url.strip()
        self.timeout = timeout

    def format_message(
        self,
        alert: AlertItem,
        k8s_ctx: K8sPodContext,
        logs: str,
        rca: str,
        max_len: int = TELEGRAM_MAX_LEN,
    ) -> str:
        is_compact = max_len <= self.DISCORD_MAX_LEN
        log_budget = 350 if is_compact else 700
        rca_budget = 850 if is_compact else 1800
        max_events = 2 if is_compact else 4

        events_snippet = (
            "\n".join(f"  - {e[:160]}" for e in k8s_ctx.events[:max_events])
            if k8s_ctx.events
            else f"  - {k8s_ctx.error or 'No Warning events recorded'}"
        )
        log_snippet = logs[-log_budget:] if len(logs) > log_budget else logs
        rca_snippet = rca[:rca_budget] if len(rca) > rca_budget else rca

        report = (
            f"🚨 [ALERT] {alert.alertname} ({alert.severity.upper()})\n"
            f"• Namespace: {alert.namespace}\n"
            f"• Pod: {alert.pod}\n"
            f"• Summary: {alert.summary[:200]}\n\n"
            f"⚙️ [K8S STATUS & EVENTS]\n"
            f"• Phase: {k8s_ctx.pod_phase} | Waiting: {k8s_ctx.waiting_reason or 'None'} | "
            f"Terminated: {k8s_ctx.terminated_reason or 'None'} (exit={k8s_ctx.exit_code}, restarts={k8s_ctx.restart_count})\n"
            f"{events_snippet}\n\n"
            f"📋 [LOKI LOGS (Last 10m)]\n"
            f"{log_snippet}\n\n"
            f"🤖 [GEMINI 2.5 FLASH RCA]\n"
            f"{rca_snippet}"
        )

        if len(report) > max_len:
            return report[: max_len - 20] + "\n...[truncated]"
        return report

    async def send_report(
        self,
        alert: AlertItem,
        k8s_ctx: K8sPodContext,
        logs: str,
        rca: str,
    ) -> bool:
        delivered = False

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if self.telegram_token and self.telegram_chat_id:
                tg_msg = self.format_message(
                    alert, k8s_ctx, logs, rca, max_len=self.TELEGRAM_MAX_LEN
                )
                tg_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                try:
                    resp = await client.post(
                        tg_url,
                        json={
                            "chat_id": self.telegram_chat_id,
                            "text": tg_msg,
                        },
                    )
                    if resp.status_code < 300:
                        delivered = True
                    else:
                        logger.warning(
                            "Telegram delivery returned HTTP %s: %s",
                            resp.status_code,
                            resp.text[:200],
                        )
                except Exception as exc:
                    logger.warning(
                        "Telegram delivery failed (%s)",
                        exc.__class__.__name__,
                    )

            if self.discord_webhook_url:
                discord_msg = self.format_message(
                    alert, k8s_ctx, logs, rca, max_len=self.DISCORD_MAX_LEN
                )
                try:
                    resp = await client.post(
                        self.discord_webhook_url,
                        json={"content": discord_msg},
                    )
                    if resp.status_code < 300:
                        delivered = True
                    else:
                        logger.warning(
                            "Discord delivery returned HTTP %s: %s",
                            resp.status_code,
                            resp.text[:200],
                        )
                except Exception as exc:
                    logger.warning(
                        "Discord delivery failed (%s)",
                        exc.__class__.__name__,
                    )

        return delivered
