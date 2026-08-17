from __future__ import annotations

from dataclasses import dataclass, field

from demo_account_bot.admin_client import AdminApiError
from demo_account_bot.conversation_store import InMemoryConversationStore
from demo_account_bot.domain import (
    CreateDemoAccountCommand,
    CreateDemoAccountResult,
    IncomingMessage,
)
from demo_account_bot.features.demo_account import DemoAccountFeature


@dataclass
class FakeAdminClient:
    commands: list[CreateDemoAccountCommand] = field(default_factory=list)
    error: AdminApiError | None = None

    def create_demo_account(self, command: CreateDemoAccountCommand) -> CreateDemoAccountResult:
        self.commands.append(command)
        if self.error:
            raise self.error
        return CreateDemoAccountResult(command.account, "100.00000000", "100.00000000")


def message(text: str, *, open_id: str = "ou_allowed", chat_type: str = "p2p") -> IncomingMessage:
    return IncomingMessage("om_1", "oc_1", open_id, chat_type, text)


def build_feature(
    admin: FakeAdminClient | None = None,
) -> tuple[DemoAccountFeature, FakeAdminClient]:
    client = admin or FakeAdminClient()
    feature = DemoAccountFeature(
        InMemoryConversationStore(1800),
        client,  # type: ignore[arg-type]
        frozenset({"ou_allowed"}),
    )
    return feature, client


def test_complete_flow_hides_password_and_calls_admin_after_confirmation() -> None:
    feature, admin = build_feature()

    assert feature.handle(message("创建演示账号")).text == "请输入演示账号。"
    assert feature.handle(message("demo_001")).text == "请输入密码。"
    assert feature.handle(message("Demo@123")).text == "请输入初始额度。"
    preview = feature.handle(message("100")).text
    assert "demo_001" in preview
    assert "100" in preview
    assert "Demo@123" not in preview
    assert admin.commands == []

    result = feature.handle(message("确认创建")).text
    assert "创建成功" in result
    assert "Demo@123" not in result
    assert len(admin.commands) == 1
    assert admin.commands[0].password == "Demo@123"


def test_retryable_failure_reuses_idempotency_key() -> None:
    admin = FakeAdminClient(error=AdminApiError("timeout", retryable=True))
    feature, _ = build_feature(admin)
    for text in ("创建演示账号", "demo_001", "Demo@123", "100"):
        feature.handle(message(text))

    assert "失败" in feature.handle(message("确认创建")).text
    first_key = admin.commands[0].idempotency_key
    assert "失败" in feature.handle(message("确认创建")).text
    assert admin.commands[1].idempotency_key == first_key


def test_cancel_clears_password_and_never_calls_admin() -> None:
    feature, admin = build_feature()
    for text in ("创建演示账号", "demo_001", "Demo@123"):
        feature.handle(message(text))
    assert feature.handle(message("取消")).text == "已取消演示账号创建流程。"
    assert admin.commands == []


def test_rejects_unauthorized_user_and_group_chat() -> None:
    feature, _ = build_feature()
    assert "暂无" in feature.handle(message("创建演示账号", open_id="ou_other")).text
    assert "单聊" in feature.handle(message("创建演示账号", chat_type="group")).text


def test_empty_allowlist_reveals_sender_open_id_without_creating() -> None:
    admin = FakeAdminClient()
    feature = DemoAccountFeature(
        InMemoryConversationStore(1800),
        admin,  # type: ignore[arg-type]
        frozenset(),
    )
    reply = feature.handle(message("创建演示账号", open_id="ou_bootstrap")).text
    assert "ou_bootstrap" in reply
    assert "不会执行创建操作" in reply
    assert admin.commands == []


def test_validation_does_not_advance_state() -> None:
    feature, _ = build_feature()
    feature.handle(message("创建演示账号"))
    assert "3-32" in feature.handle(message("x")).text
    assert feature.handle(message("demo_001")).text == "请输入密码。"
    assert "6-72" in feature.handle(message("123")).text
