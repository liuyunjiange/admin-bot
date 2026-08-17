from __future__ import annotations

from typing import Protocol

from ..domain import FlowReply, IncomingMessage


class BotFeature(Protocol):
    def has_active_conversation(self, message: IncomingMessage) -> bool: ...

    def matches(self, message: IncomingMessage) -> bool: ...

    def handle(self, message: IncomingMessage) -> FlowReply: ...
