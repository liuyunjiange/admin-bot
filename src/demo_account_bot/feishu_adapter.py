from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

from .conversation_store import MessageDeduplicator
from .domain import IncomingMessage
from .router import FeatureRouter

LOGGER = logging.getLogger(__name__)


class FeishuBot:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str,
        router: FeatureRouter,
        deduplicator: MessageDeduplicator,
    ) -> None:
        self._router = router
        self._deduplicator = deduplicator
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="message-worker")
        # Stripe locks keep messages from one conversation in order without
        # serializing unrelated users or retaining an unbounded lock map.
        self._conversation_locks = tuple(threading.Lock() for _ in range(64))
        sdk_domain = lark.FEISHU_DOMAIN if domain == "feishu" else lark.LARK_DOMAIN
        self._api_client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .domain(sdk_domain)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        self._ws_client = lark.ws.Client(
            app_id,
            app_secret,
            event_handler=handler,
            domain=sdk_domain,
            # User messages can contain passwords. Keep SDK payload logging off
            # at normal runtime levels.
            log_level=lark.LogLevel.WARNING,
        )

    def run(self) -> None:
        LOGGER.info("starting Feishu WebSocket client")
        self._ws_client.start()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _on_message(self, event: P2ImMessageReceiveV1) -> None:
        try:
            incoming = self._parse_message(event)
            if incoming and self._deduplicator.first_seen(incoming.message_id):
                self._executor.submit(self._process_message, incoming)
        except Exception:
            LOGGER.exception("failed to accept Feishu message event")

    def _process_message(self, message: IncomingMessage) -> None:
        lock = self._conversation_locks[hash((message.chat_id, message.open_id)) % 64]
        try:
            with lock:
                reply = self._router.dispatch(message)
                self._send_text(message.chat_id, reply.text)
        except Exception:
            LOGGER.exception(
                "failed to process message message_id=%s chat_id=%s",
                message.message_id,
                message.chat_id,
            )
            self._send_text(message.chat_id, "消息处理失败，请稍后重试。")

    def _send_text(self, chat_id: str, text: str) -> None:
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self._api_client.im.v1.message.create(request)
        if not response.success():
            LOGGER.error(
                "failed to send Feishu message chat_id=%s code=%s msg=%s log_id=%s",
                chat_id,
                response.code,
                response.msg,
                response.get_log_id(),
            )

    @staticmethod
    def _parse_message(event: P2ImMessageReceiveV1) -> IncomingMessage | None:
        data: Any = event.event
        message = getattr(data, "message", None)
        sender = getattr(data, "sender", None)
        sender_id = getattr(sender, "sender_id", None)
        if not message or not sender_id or getattr(sender, "sender_type", "") in {"bot", "app"}:
            return None
        if getattr(message, "message_type", "") != "text":
            return None
        try:
            content = json.loads(getattr(message, "content", "{}") or "{}")
        except json.JSONDecodeError:
            return None
        text = content.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        return IncomingMessage(
            message_id=str(getattr(message, "message_id", "") or ""),
            chat_id=str(getattr(message, "chat_id", "") or ""),
            open_id=str(getattr(sender_id, "open_id", "") or ""),
            chat_type=str(getattr(message, "chat_type", "") or ""),
            text=text.strip(),
        )
