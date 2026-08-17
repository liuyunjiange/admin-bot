# Admin Bot Jenkins 部署设计

## 目标

为 `admin-bot` 建立与 `invest-agent` 一致的生产发布链路：构建 Job 生成并推送不可变镜像，部署 Job 按镜像标签发布到既有服务器；发布失败时恢复上一镜像。

本次不引入 Agent、数据库、公网回调、Jenkins 中的业务密钥或多副本部署。

## 采用方案

复用现有 Jenkins、阿里云 ACR 与 SSH 凭据，采用两个独立 Job。

| 项目 | 固定约定 |
| --- | --- |
| Git 仓库 | `git@github.com:SinapisAI/admin-bot.git` |
| 构建分支 | `main`，可由构建参数覆盖 |
| 阿里云 ACR 仓库 | `sinapis-registry-vpc.cn-qingdao.cr.aliyuncs.com/sinapis-platform/sinapis-bot` |
| 镜像标签 | `admin-bot-prod-vX.Y.Z-<git-short>-b<build-number>` |
| 部署目录 | `/opt/admin-bot` |
| 容器名 | `admin-bot-prod` |
| 服务副本 | 1 |

不使用 `latest` 标签，不在部署机拉取 Git 代码，不在 Jenkins 日志或构建产物中输出敏感配置。

## Job 一：构建与推送

文件名为 `Jenkinsfile.prod-build-ali`。Job 接收 `BRANCH` 参数，默认 `main`。

1. 使用既有 Git SSH 凭据 `github-ssh-key` 检出代码。
2. 解析当前提交短 SHA 与最近 Git tag；没有 tag 时使用 `v0.0.0`。
3. 使用 Python 3.12 Docker 临时容器执行 `pip install -e ".[dev]"`、Ruff、pytest 和 Python 编译检查，不依赖 Jenkins Agent 预装 Python 环境。
4. 构建 Docker 镜像，并使用不可变标签标记。
5. 使用既有阿里云 ACR 凭据 `aliyun-acr-sinapis-platform` 登录，推送镜像。
6. 归档仅包含 `IMAGE_REF` 和 `IMAGE_TAG` 的 `image-info.properties`。

构建失败时不触发部署，也不产生可被部署 Job 使用的镜像标签。

## Job 二：部署与回滚

文件名为 `Jenkinsfile.prod-deploy-ali`。Job 强制要求传入 `IMAGE_TAG`；空值、`latest` 或不以 `admin-bot-prod-` 开头的标签直接失败。

1. 组合得到目标镜像地址，并显示镜像引用，不显示任何密钥。
2. 使用既有 SSH 凭据 `ali-inner-ssh-key` 连接现有部署服务器。
3. 使用既有阿里云 ACR 凭据登录服务器 Docker，拉取目标镜像。
4. 校验 `/opt/admin-bot/.env` 存在；该文件由运维一次性手工创建并保留在部署机，Jenkins 不上传、不读取、不归档。
5. 记录当前 `admin-bot-prod` 容器所用镜像为回滚目标。
6. 停止并删除旧容器，使用 `--env-file /opt/admin-bot/.env`、`--restart always` 与 `-p 127.0.0.1:8080:8080` 启动目标镜像。
7. 等待 Docker `healthy` 状态，并请求 `http://127.0.0.1:8080/healthz`。
8. 验证失败则删除新容器；若存在旧镜像则按相同参数重新启动旧镜像，并输出有限数量的容器日志辅助排障。

部署 Job 禁止并发执行，避免两个发布任务互相替换容器。

## 敏感配置与网络

部署机 `/opt/admin-bot/.env` 至少包含：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `ADMIN_API_BASE_URL`
- `ADMIN_SERVICE_TOKEN`
- `DEMO_ACCOUNT_ALLOWED_OPEN_IDS`
- `HEALTH_PORT=8080`

`.env` 文件权限设为 `600`。`ADMIN_API_BASE_URL` 必须为容器能够访问的后端内网地址或内部域名，不能使用开发机专用的 `host.docker.internal`。

Jenkins 和部署机需要具备到阿里云 ACR 的网络连通性；部署机还需要具备到飞书和模型平台后端的网络连通性。Bot 通过出站 WebSocket 与飞书通信，无需公网入站回调或 Nginx。

构建 Agent 还需要能够拉取 Python 基础镜像并安装 Python 依赖；若不能访问公网，应使用企业镜像与 Python 包镜像源。

## 验证与限制

构建阶段覆盖静态检查、单元测试和镜像构建；部署阶段覆盖镜像拉取、容器健康状态和本机健康端点。

`/healthz` 当前表示进程存活，不表示飞书 WebSocket 已建立或后端接口鉴权成功。因此每次首次发布或飞书配置变更后，仍需在飞书单聊进行一次“创建演示账号”的人工验收。

当前会话和消息去重为进程内存实现，部署后只能运行一个副本；扩容前必须替换为共享存储实现。
