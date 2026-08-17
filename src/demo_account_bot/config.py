from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"missing required environment variable: {name}")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than 0")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    feishu_app_id: str
    feishu_app_secret: str
    feishu_domain: str
    admin_api_base_url: str
    admin_service_token: str
    admin_api_timeout_seconds: int
    allowed_open_ids: frozenset[str]
    session_ttl_minutes: int
    health_host: str
    health_port: int
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        domain = os.getenv("FEISHU_DOMAIN", "feishu").strip().lower()
        if domain not in {"feishu", "lark"}:
            raise ConfigError("FEISHU_DOMAIN must be 'feishu' or 'lark'")
        allowed = frozenset(
            item.strip()
            for item in os.getenv("DEMO_ACCOUNT_ALLOWED_OPEN_IDS", "").split(",")
            if item.strip()
        )
        return cls(
            feishu_app_id=_required("FEISHU_APP_ID"),
            feishu_app_secret=_required("FEISHU_APP_SECRET"),
            feishu_domain=domain,
            admin_api_base_url=_required("ADMIN_API_BASE_URL").rstrip("/"),
            admin_service_token=_required("ADMIN_SERVICE_TOKEN"),
            admin_api_timeout_seconds=_positive_int("ADMIN_API_TIMEOUT_SECONDS", 30),
            allowed_open_ids=allowed,
            session_ttl_minutes=_positive_int("DEMO_ACCOUNT_SESSION_TTL_MINUTES", 30),
            health_host=os.getenv("HEALTH_HOST", "0.0.0.0").strip() or "0.0.0.0",
            health_port=_positive_int("HEALTH_PORT", 8080),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )
