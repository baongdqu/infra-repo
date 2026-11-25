from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    loki_url: str = "http://loki.monitoring.svc.cluster.local:3100"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    cooldown_seconds: int = 900
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    k8s_enabled: bool = True
