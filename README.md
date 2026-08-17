# Demo Account Bot

独立的 Python 飞书机器人中间服务。它不使用 Pi、Agent、Skill 或大模型，通过固定状态机收集账号、密码和初始额度，用户确认后调用模型平台 Admin 接口创建演示账号。

## 架构

```text
用户 → 飞书机器人 ⇄ WebSocket ⇄ 本服务 → HTTP → models-layer-backend
```

本服务采用可插拔 Feature Router。以后新增业务功能或 Agent 意图识别时，可增加新的 Feature，不需要修改飞书适配层和 Admin 客户端。

详细的模块边界、扩展新功能和后续接入 Agent 的方式见
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 本地启动

```powershell
Copy-Item .env.example .env
# 填写 .env
docker compose up -d --build
docker compose logs -f demo-account-bot
```

如果部署环境不能直接访问 Docker Hub，可在 `.env` 中把
`PYTHON_BASE_IMAGE` 改为可访问的 Python 3.12 企业镜像地址后重新构建。

健康检查：

```text
http://127.0.0.1:8080/healthz
```

## 必要配置

- `FEISHU_APP_ID`、`FEISHU_APP_SECRET`：飞书企业自建应用凭证。
- `ADMIN_API_BASE_URL`：模型平台后端地址。
- `ADMIN_SERVICE_TOKEN`：后端服务 Token 原文。
- `DEMO_ACCOUNT_ALLOWED_OPEN_IDS`：允许创建账号的飞书用户白名单。首次可留空；此时
  服务只向单聊用户返回其 `open_id`，不会执行创建操作。取得 `open_id` 后必须填写并重启。

## 飞书配置

1. 开启机器人能力。
2. 事件订阅选择“使用长连接接收事件”。
3. 订阅 `im.message.receive_v1`。
4. 申请接收单聊消息和以机器人身份发送消息权限。
5. 发布应用，并设置可用范围。

第一版只允许单聊创建，群聊会提示用户转到单聊。

## 生产部署

只需部署本服务，不需要公网回调网关、Agent 或数据库。服务主动与飞书建立
WebSocket 长连接，并通过内网 HTTP 访问 `models-layer-backend`。

- 使用容器平台 Secret 或主机环境变量注入所有敏感配置，不提交 `.env`。
- `ADMIN_SERVICE_TOKEN` 填原始 Token；后端 Nacos 中保存对应 SHA-256 值。
- 健康探针使用 `GET /healthz`。
- 第一版运行 1 个副本；多副本前把内存会话和消息去重实现替换为 Redis。
- 日志不得提升到可能输出飞书原始事件内容的 SDK 调试级别。

## 对话

输入 `创建演示账号` 或 `/demo-account`，然后依次输入：

1. 账号。
2. 密码。
3. 初始额度。
4. `确认创建`。

输入 `取消` 可随时终止。密码只在当前进程内存中暂存，不会写入日志或展示在预览和结果中。

## 开发验证

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```
