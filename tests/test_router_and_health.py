from __future__ import annotations

import json
import urllib.request

from demo_account_bot.domain import FlowReply, IncomingMessage
from demo_account_bot.health import start_health_server
from demo_account_bot.router import FeatureRouter


class StubFeature:
    def __init__(self, *, active: bool = False, matches: bool = False) -> None:
        self.active = active
        self.matched = matches

    def has_active_conversation(self, _message: IncomingMessage) -> bool:
        return self.active

    def matches(self, _message: IncomingMessage) -> bool:
        return self.matched

    def handle(self, _message: IncomingMessage) -> FlowReply:
        return FlowReply("handled")


def message() -> IncomingMessage:
    return IncomingMessage("om_1", "oc_1", "ou_1", "p2p", "hello")


def test_router_prefers_active_feature() -> None:
    router = FeatureRouter([StubFeature(active=True), StubFeature(matches=True)])
    assert router.dispatch(message()).text == "handled"


def test_router_returns_help_for_unknown_message() -> None:
    router = FeatureRouter([StubFeature()])
    assert "创建演示账号" in router.dispatch(message()).text


def test_health_endpoint() -> None:
    server = start_health_server("127.0.0.1", 0)
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz") as response:
            assert response.status == 200
            assert json.load(response) == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()
