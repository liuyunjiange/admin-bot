from __future__ import annotations

import json

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from demo_account_bot.feishu_adapter import FeishuBot


def test_parse_message_uses_sdk_event_payload() -> None:
    event = P2ImMessageReceiveV1(
        {
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_test"},
                    "sender_type": "user",
                },
                "message": {
                    "message_id": "om_test",
                    "chat_id": "oc_test",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": json.dumps({"text": "创建演示账号"}),
                },
            }
        }
    )

    result = FeishuBot._parse_message(event)

    assert result is not None
    assert result.message_id == "om_test"
    assert result.chat_id == "oc_test"
    assert result.open_id == "ou_test"
    assert result.chat_type == "p2p"
    assert result.text == "创建演示账号"
