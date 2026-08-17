from __future__ import annotations

import logging

from .admin_client import AdminClient
from .config import ConfigError, Settings
from .conversation_store import InMemoryConversationStore, MessageDeduplicator
from .features.demo_account import DemoAccountFeature
from .feishu_adapter import FeishuBot
from .health import start_health_server
from .router import FeatureRouter


def build_bot(settings: Settings) -> tuple[FeishuBot, AdminClient]:
    admin_client = AdminClient(
        settings.admin_api_base_url,
        settings.admin_service_token,
        settings.admin_api_timeout_seconds,
    )
    store = InMemoryConversationStore(settings.session_ttl_minutes * 60)
    feature = DemoAccountFeature(store, admin_client, settings.allowed_open_ids)
    router = FeatureRouter([feature])
    bot = FeishuBot(
        settings.feishu_app_id,
        settings.feishu_app_secret,
        settings.feishu_domain,
        router,
        MessageDeduplicator(),
    )
    return bot, admin_client


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        raise SystemExit(f"configuration error: {exc}") from exc
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    health_server = start_health_server(settings.health_host, settings.health_port)
    bot, admin_client = build_bot(settings)
    try:
        bot.run()
    finally:
        bot.close()
        admin_client.close()
        health_server.shutdown()


if __name__ == "__main__":
    main()
