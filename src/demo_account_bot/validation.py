from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

ACCOUNT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
QUOTA_PATTERN = re.compile(r"^\d+(?:\.\d{1,8})?$")


def account_error(value: str) -> str | None:
    if not ACCOUNT_PATTERN.fullmatch(value.strip()):
        return "账号仅支持 3-32 位字母、数字、下划线或短横线，请重新输入。"
    return None

def password_error(value: str) -> str | None:
    if not 6 <= len(value) <= 72:
        return "密码长度需要在 6-72 位之间，请重新输入。"
    return None


def quota_error(value: str) -> str | None:
    value = value.strip()
    if not QUOTA_PATTERN.fullmatch(value):
        return "请输入大于 0 的初始额度，最多保留 8 位小数。"
    try:
        if Decimal(value) <= 0:
            return "初始额度必须大于 0，请重新输入。"
    except InvalidOperation:
        return "请输入有效的初始额度。"
    return None
