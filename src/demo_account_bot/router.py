from __future__ import annotations

from collections.abc import Sequence

from .domain import FlowReply, IncomingMessage
from .features.base import BotFeature


class FeatureRouter:
    def __init__(self, features: Sequence[BotFeature]) -> None:
        self._features = tuple(features)

    def dispatch(self, message: IncomingMessage) -> FlowReply:
        for feature in self._features:
            if feature.has_active_conversation(message):
                return feature.handle(message)
        for feature in self._features:
            if feature.matches(message):
                return feature.handle(message)
        return FlowReply(
            "当前支持的功能：\n"
            "- 创建演示账号\n\n"
            "请输入“创建演示账号”开始。"
        )
