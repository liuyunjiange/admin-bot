from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .domain import CreateDemoAccountCommand, CreateDemoAccountResult


@dataclass(frozen=True, slots=True)
class AdminApiError(Exception):
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class AdminClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        timeout_seconds: int = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._service_token = service_token
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def create_demo_account(
        self, command: CreateDemoAccountCommand
    ) -> CreateDemoAccountResult:
        try:
            response = self._client.post(
                "/api/v1/admin/accounts/demo",
                headers={
                    "X-Service-Token": self._service_token,
                    "Idempotency-Key": command.idempotency_key,
                },
                json={
                    "account": command.account,
                    "password": command.password,
                    "initialQuota": command.initial_quota,
                },
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AdminApiError("Admin 接口暂时不可用，请稍后回复“确认创建”重试。", True) from exc

        body = self._json_object(response)
        if response.is_error or body.get("code") != 0:
            message = self._error_message(response.status_code, body)
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable:
                message = f"{message}，请稍后回复“确认创建”重试。"
            raise AdminApiError(message, retryable)

        data = body.get("data")
        if not isinstance(data, dict):
            raise AdminApiError("Admin 接口返回格式不正确，请联系系统负责人。", True)
        return CreateDemoAccountResult(
            account=str(data.get("account") or command.account),
            initial_quota=str(data.get("initialQuota") or command.initial_quota),
            available_balance=(
                str(data["availableBalance"]) if data.get("availableBalance") is not None else None
            ),
        )

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _error_message(status: int, body: dict[str, Any]) -> str:
        message = body.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        return f"Admin 接口请求失败（HTTP {status}）"
