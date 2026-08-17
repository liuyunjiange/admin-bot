from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ConversationStep(StrEnum):
    WAIT_ACCOUNT = "wait_account"
    WAIT_PASSWORD = "wait_password"
    WAIT_QUOTA = "wait_quota"
    WAIT_CONFIRM = "wait_confirm"
    CREATING = "creating"


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    message_id: str
    chat_id: str
    open_id: str
    chat_type: str
    text: str


@dataclass(slots=True)
class Conversation:
    chat_id: str
    open_id: str
    step: ConversationStep
    idempotency_key: str
    updated_at: float
    account: str | None = None
    password: str | None = None
    initial_quota: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.chat_id, self.open_id


@dataclass(frozen=True, slots=True)
class FlowReply:
    text: str


@dataclass(frozen=True, slots=True)
class CreateDemoAccountCommand:
    account: str
    password: str
    initial_quota: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class CreateDemoAccountResult:
    account: str
    initial_quota: str
    available_balance: str | None = None
