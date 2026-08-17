# Admin Bot Jenkins 生产部署

本服务通过两个 Jenkins Job 发布，不在部署机拉取 Git 代码：

1. 构建 Job：检出代码、执行 Python 检查、构建不可变 Docker 镜像并推送阿里云 ACR。
2. 部署 Job：按镜像标签登录部署机、更新单个容器、执行健康检查，失败时恢复旧镜像。

## 固定约定

- Git 仓库：git@github.com:SinapisAI/admin-bot.git
- 阿里云 ACR 镜像：sinapis-registry-vpc.cn-qingdao.cr.aliyuncs.com/sinapis-platform/sinapis-bot
- 部署目录：/opt/admin-bot
- 容器名称：admin-bot-prod
- 健康端口：127.0.0.1:8080
- 运行副本：1 个

Jenkins 使用以下既有凭据：

- github-ssh-key：检出 Git 仓库。
- aliyun-acr-sinapis-platform：推送和拉取阿里云 ACR 镜像。
- ali-inner-ssh-key：连接现有部署服务器。

凭据值不写入代码、Jenkinsfile、构建产物或日志。

## 部署机一次性准备

在现有部署服务器执行：

    sudo mkdir -p /opt/admin-bot
    sudo touch /opt/admin-bot/.env
    sudo chmod 600 /opt/admin-bot/.env

在 /opt/admin-bot/.env 中填写生产配置：

    FEISHU_APP_ID=
    FEISHU_APP_SECRET=
    FEISHU_DOMAIN=feishu

    ADMIN_API_BASE_URL=
    ADMIN_SERVICE_TOKEN=
    ADMIN_API_TIMEOUT_SECONDS=30

    DEMO_ACCOUNT_ALLOWED_OPEN_IDS=
    DEMO_ACCOUNT_SESSION_TTL_MINUTES=30

    HEALTH_HOST=0.0.0.0
    HEALTH_PORT=8080
    LOG_LEVEL=INFO

生产环境必须填写 DEMO_ACCOUNT_ALLOWED_OPEN_IDS，多个 open_id 使用英文逗号分隔。不要把密码或 Token 提交到 Git。

后端 Nacos 配置保存 ADMIN_SERVICE_TOKEN 原文的 SHA-256 值：

    admin:
      demo-account:
        service-token-sha256: "Token 原文的 SHA-256 值"

ADMIN_API_BASE_URL 必须是容器可以访问的模型平台后端内网地址，不能填写本地开发环境的 127.0.0.1。Jenkins 和部署机需要能访问阿里云 ACR，部署机还需要能访问飞书和模型平台后端。Jenkins 凭据 aliyun-acr-sinapis-platform 需要具备 sinapis-platform/sinapis-bot 的推送和拉取权限。

## 创建 Jenkins Job

创建两个 Pipeline Job，并从 admin-bot 的 main 分支加载对应文件：

- 构建 Job：Jenkinsfile.prod-build-ali
- 部署 Job：Jenkinsfile.prod-deploy-ali

构建 Job 参数：

- BRANCH：默认 main。

构建成功后，在归档产物 image-info.properties 中获取 IMAGE_TAG。镜像标签格式为：

    admin-bot-prod-vX.Y.Z-提交短 SHA-构建号

部署 Job 参数：

- IMAGE_TAG：填入构建 Job 归档的不可变镜像标签。
- 不要填 latest。
- 不要手工修改标签中的特殊字符。

## 发布流程

1. 确认后端生产 Nacos 配置已经生效。
2. 运行构建 Job，参数 BRANCH 使用 main。
3. 确认 Python 测试、Ruff、编译检查和镜像 Smoke Test 通过。
4. 复制构建产物中的 IMAGE_TAG。
5. 运行部署 Job，填写 IMAGE_TAG。
6. 等待部署 Job 报告容器健康检查通过。
7. 在部署服务器检查：

    docker ps --filter name=admin-bot-prod
    curl --fail http://127.0.0.1:8080/healthz

8. 在飞书与机器人单聊，输入“创建演示账号”，完成一次真实创建流程。
9. 在模型平台 Admin 或数据库确认账号已经写入。

/healthz 只表示进程存活，不代表飞书 WebSocket 和后端鉴权一定正常。因此首次发布、Token 变更、飞书应用权限变更后，都必须完成飞书人工验收。

## 回滚流程

部署失败时，部署 Job 会自动使用旧容器镜像回滚。若需要手工回滚：

1. 找到上一次成功构建的 IMAGE_TAG。
2. 重新运行部署 Job。
3. 传入旧的 IMAGE_TAG。
4. 等待健康检查通过，再进行飞书人工验收。

Jenkins 不会回滚 /opt/admin-bot/.env。若故障由 Token、白名单或后端地址变更引起，需要先恢复服务器上的配置，再重新部署或回滚镜像。

## 常见问题

- 构建阶段无法下载 Python 基础镜像或依赖：为 Jenkins Docker 配置企业镜像和 Python 包镜像源。
- 部署阶段提示缺少 .env：在部署服务器创建 /opt/admin-bot/.env，并设置权限 600。
- 容器健康检查失败：先查看部署 Job 输出和服务器上的 docker logs --tail 200 admin-bot-prod，不要打印 .env。
- 飞书无响应：检查飞书应用是否已发布、机器人能力是否开启、是否订阅 im.message.receive_v1，以及部署机能否访问飞书 WebSocket。
- 后端返回鉴权失败：核对 ADMIN_SERVICE_TOKEN 原文和后端 Nacos 中的 SHA-256 值是否匹配。

当前会话和消息去重保存在进程内存中，生产环境只运行一个副本。扩容前需要先改为共享存储实现。
