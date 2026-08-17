from __future__ import annotations

import re
import time
import uuid

from ..admin_client import AdminApiError, AdminClient
from ..conversation_store import InMemoryConversationStore
from ..domain import (
    Conversation,
    ConversationStep,
    CreateDemoAccountCommand,
    FlowReply,
    IncomingMessage,
)
from ..validation import account_error, password_error, quota_error

START_PATTERN = re.compile(
    r"^(?:/demo-account|(?:创建|新增|开通|申请|建一个|办一个)(?:模型平台)?(?:admin)?(?:演示|测试)(?:账号|账户))$",
    re.IGNORECASE,
)
CANCEL_WORDS = {"取消", "取消创建", "退出", "退出流程"}
CONFIRM_WORDS = {"确认创建", "确认创建账号", "确认提交", "确认执行"}


def normalize(text: str) -> str:
    return re.sub(r"[\s，,。！!？?、“”'\"：:；;]", "", text).lower()


class DemoAccountFeature:
    def __init__(
        self,
        store: InMemoryConversationStore,
        admin_client: AdminClient,
        allowed_open_ids: frozenset[str],
    ) -> None:
        self._store = store
        self._admin = admin_client
        self._allowed_open_ids = allowed_open_ids

    def has_active_conversation(self, message: IncomingMessage) -> bool:
        return self._store.get(message.chat_id, message.open_id) is not None

    def matches(self, message: IncomingMessage) -> bool:
        return bool(START_PATTERN.fullmatch(normalize(message.text)))

    def handle(self, message: IncomingMessage) -> FlowReply:
        if message.chat_type != "p2p":
            return FlowReply("为保护密码安全，请在机器人单聊中创建演示账号。")
        if not self._allowed_open_ids:
            return FlowReply(
                "当前尚未配置演示账号创建白名单，因此不会执行创建操作。\n"
                f"你的 open_id：{message.open_id}\n\n"
                "请将它填写到服务的 DEMO_ACCOUNT_ALLOWED_OPEN_IDS，重启服务后再试。"
            )
        if message.open_id not in self._allowed_open_ids:
            return FlowReply("你暂无创建演示账号的权限。")

        conversation = self._store.get(message.chat_id, message.open_id)
        text = message.text.strip()
        normalized = normalize(text)

        if conversation is None:
            conversation = Conversation(
                chat_id=message.chat_id,
                open_id=message.open_id,
                step=ConversationStep.WAIT_ACCOUNT,
                idempotency_key=f"feishu-demo-{uuid.uuid4()}",
                updated_at=time.time(),
            )
            self._store.put(conversation)
            return FlowReply("请输入演示账号。")

        if normalized in CANCEL_WORDS:
            self._store.delete(message.chat_id, message.open_id)
            return FlowReply("已取消演示账号创建流程。")

        if conversation.step == ConversationStep.WAIT_ACCOUNT:
            return self._handle_account(conversation, text)
        if conversation.step == ConversationStep.WAIT_PASSWORD:
            return self._handle_password(conversation, text)
        if conversation.step == ConversationStep.WAIT_QUOTA:
            return self._handle_quota(conversation, text)
        if conversation.step == ConversationStep.WAIT_CONFIRM:
            return self._handle_confirmation(conversation, normalized)
        return FlowReply("创建请求正在处理中，请勿重复提交。")

    def _handle_account(self, conversation: Conversation, text: str) -> FlowReply:
        error = account_error(text)
        if error:
            return FlowReply(error)
        conversation.account = text.strip()
        conversation.step = ConversationStep.WAIT_PASSWORD
        self._store.put(conversation)
        return FlowReply("请输入密码。")

    def _handle_password(self, conversation: Conversation, text: str) -> FlowReply:
        error = password_error(text)
        if error:
            return FlowReply(error)
        conversation.password = text
        conversation.step = ConversationStep.WAIT_QUOTA
        self._store.put(conversation)
        return FlowReply("请输入初始额度。")

    def _handle_quota(self, conversation: Conversation, text: str) -> FlowReply:
        error = quota_error(text)
        if error:
            return FlowReply(error)
        conversation.initial_quota = text.strip()
        conversation.step = ConversationStep.WAIT_CONFIRM
        self._store.put(conversation)
        return FlowReply(
            "即将创建演示账号：\n"
            f"账号：{conversation.account}\n"
            f"初始额度：{conversation.initial_quota}\n\n"
            "密码已填写，不予展示。\n"
            "请回复“确认创建”继续，回复“取消”终止。"
        )

    def _handle_confirmation(self, conversation: Conversation, normalized: str) -> FlowReply:
        if normalized not in CONFIRM_WORDS:
            return FlowReply("请回复“确认创建”继续，回复“取消”终止。")
        if not conversation.account or not conversation.password or not conversation.initial_quota:
            self._store.delete(conversation.chat_id, conversation.open_id)
            return FlowReply("创建信息已失效，请重新发起创建演示账号。")

        conversation.step = ConversationStep.CREATING
        self._store.put(conversation)
        command = CreateDemoAccountCommand(
            account=conversation.account,
            password=conversation.password,
            initial_quota=conversation.initial_quota,
            idempotency_key=conversation.idempotency_key,
        )
        try:
            result = self._admin.create_demo_account(command)
        except AdminApiError as exc:
            if exc.retryable:
                conversation.step = ConversationStep.WAIT_CONFIRM
                self._store.put(conversation)
            else:
                self._store.delete(conversation.chat_id, conversation.open_id)
            return FlowReply(f"创建演示账号失败：{exc}")

        self._store.delete(conversation.chat_id, conversation.open_id)
        return FlowReply(
            "演示账号创建成功。\n"
            f"账号：{result.account}\n"
            f"初始额度：{result.initial_quota}"
        )
