from __future__ import annotations

import pytest

from demo_account_bot.config import Settings
from demo_account_bot.conversation_store import MessageDeduplicator


def test_empty_allowlist_starts_in_bootstrap_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("ADMIN_API_BASE_URL", "http://admin")
    monkeypatch.setenv("ADMIN_SERVICE_TOKEN", "token")
    monkeypatch.delenv("DEMO_ACCOUNT_ALLOWED_OPEN_IDS", raising=False)
    settings = Settings.from_env()
    assert settings.allowed_open_ids == frozenset()


def test_message_deduplicator() -> None:
    deduplicator = MessageDeduplicator()
    assert deduplicator.first_seen("om_1") is True
    assert deduplicator.first_seen("om_1") is False
