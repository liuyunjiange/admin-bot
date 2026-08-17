from __future__ import annotations

import httpx
import pytest

from demo_account_bot.admin_client import AdminApiError, AdminClient
from demo_account_bot.domain import CreateDemoAccountCommand


def command() -> CreateDemoAccountCommand:
    return CreateDemoAccountCommand("demo_001", "Demo@123", "100", "feishu-demo-fixed")


def test_admin_client_uses_expected_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/admin/accounts/demo"
        assert request.headers["X-Service-Token"] == "raw-token"
        assert request.headers["Idempotency-Key"] == "feishu-demo-fixed"
        assert b'"password":"Demo@123"' in request.content
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "ok",
                "data": {
                    "account": "demo_001",
                    "initialQuota": "100.00000000",
                    "availableBalance": "100.00000000",
                },
            },
        )

    client = AdminClient("http://admin", "raw-token", transport=httpx.MockTransport(handler))
    result = client.create_demo_account(command())
    client.close()
    assert result.account == "demo_001"
    assert result.initial_quota == "100.00000000"


def test_admin_client_maps_business_error() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(409, json={"code": 409140, "message": "账号已存在"})
    )
    client = AdminClient("http://admin", "raw-token", transport=transport)
    with pytest.raises(AdminApiError, match="账号已存在") as captured:
        client.create_demo_account(command())
    client.close()
    assert captured.value.retryable is False


def test_admin_client_treats_rate_limit_as_retryable() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(429, json={"code": 429000, "message": "请求过多"})
    )
    client = AdminClient("http://admin", "raw-token", transport=transport)
    with pytest.raises(AdminApiError, match="确认创建") as captured:
        client.create_demo_account(command())
    client.close()
    assert captured.value.retryable is True
