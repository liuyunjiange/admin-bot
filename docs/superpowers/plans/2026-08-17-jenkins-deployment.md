# Jenkins Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add the two Jenkins jobs and deployment runbook needed to build, publish, deploy, verify, and roll back the Admin Bot service.

**Architecture:** The build job checks out the selected branch, validates the Python project in a transient Python 3.12 container, builds an immutable Docker image, and pushes it to the existing Alibaba Cloud ACR repository. The deploy job accepts only a generated immutable image tag, connects to the existing server over SSH, starts one admin-bot-prod container using the server-local .env, verifies health, and restores the previous image if verification fails.

**Tech Stack:** Jenkins Declarative Pipeline, Docker, Alibaba Cloud ACR, SSH, Bash, Python 3.12, pytest, Ruff.

## Global Constraints

- Reuse Jenkins credentials github-ssh-key, aliyun-acr-sinapis-platform, and ali-inner-ssh-key. Never write credential values to repository files or logs.
- Publish only under sinapis-registry-vpc.cn-qingdao.cr.aliyuncs.com/sinapis-platform/sinapis-bot.
- Tags use admin-bot-prod-vX.Y.Z-<git-short>-b<build-number>. The deploy pipeline rejects latest.
- Deploy one container named admin-bot-prod from /opt/admin-bot.
- Jenkins only checks for /opt/admin-bot/.env and passes it with --env-file. It never uploads, reads, archives, or prints it.
- Bind the health endpoint to 127.0.0.1:8080 and require HEALTH_PORT=8080 in the server .env.
- On a failed startup or health check, restore the exact old image if an old container existed.

---

### Task 1: Add the build-pipeline contract test and image build Job

**Files:**

- Create: tests/test_jenkins_pipelines.py
- Create: Jenkinsfile.prod-build-ali

**Interfaces:**

- Consumes: Git SSH credential github-ssh-key and Alibaba Cloud ACR credential aliyun-acr-sinapis-platform.
- Produces: an image under sinapis-registry-vpc.cn-qingdao.cr.aliyuncs.com/sinapis-platform/sinapis-bot and archived image-info.properties containing IMAGE_REF and IMAGE_TAG.

- [ ] **Step 1: Write the failing build-pipeline contract test**

    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]

    def test_build_pipeline_uses_immutable_admin_bot_images() -> None:
        pipeline = (ROOT / "Jenkinsfile.prod-build-ali").read_text(encoding="utf-8")

        assert "string(name: 'BRANCH', defaultValue: 'main'" in pipeline
        assert "GIT_SSH_CREDENTIALS_ID = 'github-ssh-key'" in pipeline
        assert "REGISTRY_NAMESPACE = 'sinapis-platform'" in pipeline
        assert "IMAGE_NAME = 'sinapis-bot'" in pipeline
        assert 'env.IMAGE_TAG = "admin-bot-prod-${env.VERSION}-${env.GIT_SHORT}-b${env.BUILD_NUMBER}"' in pipeline
        assert 'pip install -e ".[dev]"' in pipeline
        assert "python -m pytest" in pipeline
        assert "python -m ruff check ." in pipeline
        assert 'docker push "${IMAGE_REF}"' in pipeline
        assert "archiveArtifacts artifacts: 'image-info.properties', fingerprint: true" in pipeline

- [ ] **Step 2: Run the focused test and verify it fails**

    python -m pytest tests/test_jenkins_pipelines.py -q

Expected: FileNotFoundError for Jenkinsfile.prod-build-ali.

- [ ] **Step 3: Implement Jenkinsfile.prod-build-ali**

Create a Declarative Pipeline with disableConcurrentBuilds(), skipDefaultCheckout(true), timestamps(), and a 30-minute timeout. Add a BRANCH string parameter defaulting to main.

Use GitSCM with URL git@github.com:SinapisAI/admin-bot.git and the github-ssh-key credential. Resolve GIT_SHORT with git rev-parse --short=8 HEAD. Resolve VERSION with git describe --tags --abbrev=0 2>/dev/null || echo v0.0.0. Set:

    env.IMAGE_TAG = "admin-bot-prod-${env.VERSION}-${env.GIT_SHORT}-b${env.BUILD_NUMBER}"
    env.IMAGE_REF = "${env.REGISTRY}/${env.REGISTRY_NAMESPACE}/${env.IMAGE_NAME}:${env.IMAGE_TAG}"

Run this validation in a python:3.12.10-slim container with the workspace mounted at /workspace:

    python -m pip install -e ".[dev]"
    python -m ruff check .
    python -m pytest
    python -m compileall -q src

Build Docker image ${IMAGE_REF}. Log in to Alibaba Cloud ACR with --password-stdin while shell tracing is disabled, push the image, and always log out. Archive image-info.properties containing only:

    IMAGE_REF=<resolved immutable image reference>
    IMAGE_TAG=<resolved immutable image tag>

- [ ] **Step 4: Run the focused test and verify it passes**

    python -m pytest tests/test_jenkins_pipelines.py -q

Expected: PASS.

- [ ] **Step 5: Commit the build pipeline and contract test**

    git add Jenkinsfile.prod-build-ali tests/test_jenkins_pipelines.py
    git commit -m "ci: add admin bot image build pipeline"

### Task 2: Add the deployment-pipeline contract test and SSH deployment Job

**Files:**

- Modify: tests/test_jenkins_pipelines.py
- Create: Jenkinsfile.prod-deploy-ali

**Interfaces:**

- Consumes: IMAGE_TAG, Alibaba Cloud ACR credential aliyun-acr-sinapis-platform, SSH credential ali-inner-ssh-key, and server-local /opt/admin-bot/.env.
- Produces: one running admin-bot-prod container using the selected immutable image, or restores the previous image before returning failure.

- [ ] **Step 1: Extend the contract test with deploy requirements**

    def test_deploy_pipeline_uses_server_local_configuration_and_rolls_back() -> None:
        pipeline = (ROOT / "Jenkinsfile.prod-deploy-ali").read_text(encoding="utf-8")

        assert "string(name: 'IMAGE_TAG', defaultValue: ''" in pipeline
        assert "if (!imageTag)" in pipeline
        assert "if (imageTag == 'latest')" in pipeline
        assert "admin-bot-prod-" in pipeline
        assert "ALI_SSH_CREDENTIALS_ID = 'ali-inner-ssh-key'" in pipeline
        assert 'BASE_DIR = "/opt/admin-bot"' in pipeline
        assert 'CONTAINER_NAME = "admin-bot-prod"' in pipeline
        assert 'test -f "${BASE_DIR}/.env"' in pipeline
        assert '--env-file "${BASE_DIR}/.env"' in pipeline
        assert '-p "127.0.0.1:8080:8080"' in pipeline
        assert "docker inspect --format '{{.State.Health.Status}}'" in pipeline
        assert "curl --fail --silent --show-error http://127.0.0.1:8080/healthz" in pipeline
        assert "restoring previous image" in pipeline

- [ ] **Step 2: Run the focused deployment test and verify it fails**

    python -m pytest tests/test_jenkins_pipelines.py -q

Expected: FileNotFoundError for Jenkinsfile.prod-deploy-ali.

- [ ] **Step 3: Implement Jenkinsfile.prod-deploy-ali**

Create a Declarative Pipeline with disableConcurrentBuilds(), skipDefaultCheckout(true), timestamps(), and a 20-minute timeout. Require IMAGE_TAG. Fail for an empty tag, latest, or a tag not beginning with admin-bot-prod-.

Set BASE_DIR to /opt/admin-bot and CONTAINER_NAME to admin-bot-prod. The temporary remote deployment script must:

    test -f "${BASE_DIR}/.env"
    docker pull "${IMAGE_REF}"
    OLD_IMAGE="$(docker inspect --format '{{.Config.Image}}' "${CONTAINER_NAME}" 2>/dev/null || true)"

Start a replacement using exactly:

    docker run -dit       --name "${CONTAINER_NAME}"       --restart always       --env-file "${BASE_DIR}/.env"       -p "127.0.0.1:8080:8080"       --log-opt max-size=10m       --log-opt max-file=5       "${IMAGE_REF}"

Poll Docker health for at most 180 seconds. It passes only when docker inspect reports healthy and curl --fail --silent --show-error http://127.0.0.1:8080/healthz succeeds.

When startup or verification fails, remove the new container. If OLD_IMAGE is nonempty, start it with the same docker run parameters, wait for it to become healthy, then exit nonzero. Always remove the remote script and log out from Alibaba Cloud ACR after the SSH deployment stage.

- [ ] **Step 4: Run the focused test and verify it passes**

    python -m pytest tests/test_jenkins_pipelines.py -q

Expected: PASS.

- [ ] **Step 5: Commit the deployment pipeline and test update**

    git add Jenkinsfile.prod-deploy-ali tests/test_jenkins_pipelines.py
    git commit -m "ci: add admin bot deployment pipeline"

### Task 3: Add the production runbook and project link

**Files:**

- Create: docs/DEPLOY.md
- Modify: README.md
- Modify: tests/test_jenkins_pipelines.py

**Interfaces:**

- Consumes: both Jenkinsfiles, deployment server Docker access, and /opt/admin-bot/.env.
- Produces: repeatable server setup, build/deploy instructions, manual Feishu acceptance steps, and immutable-tag rollback instructions.

- [ ] **Step 1: Extend the contract test for deployment documentation**

    def test_readme_links_to_jenkins_deployment_runbook() -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        runbook = (ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")

        assert "docs/DEPLOY.md" in readme
        assert "/opt/admin-bot/.env" in runbook
        assert "HEALTH_PORT=8080" in runbook
        assert "IMAGE_TAG" in runbook
        assert "创建演示账号" in runbook

- [ ] **Step 2: Run the focused documentation test and verify it fails**

    python -m pytest tests/test_jenkins_pipelines.py -q

Expected: FileNotFoundError for docs/DEPLOY.md.

- [ ] **Step 3: Write the runbook and link it from README**

Create docs/DEPLOY.md with exact one-time server setup: create /opt/admin-bot/.env, chmod 600 /opt/admin-bot/.env, set HEALTH_PORT=8080, confirm Docker access, and set ADMIN_API_BASE_URL to a container-reachable internal backend address.

Document the required Jenkins credential IDs without values. Document release: run build Job, read IMAGE_TAG from image-info.properties, run deploy Job, inspect the health result, run a Feishu single-chat flow starting with 创建演示账号, and verify the backend record. Document rollback: rerun the deploy Job with the previous immutable IMAGE_TAG.

Add a direct docs/DEPLOY.md link in the README production deployment section.

- [ ] **Step 4: Run focused and full verification**

    python -m pytest tests/test_jenkins_pipelines.py -q
    python -m pytest
    python -m ruff check .
    python -m compileall -q src

Expected: every command exits 0.

- [ ] **Step 5: Commit the runbook and README link**

    git add docs/DEPLOY.md README.md tests/test_jenkins_pipelines.py
    git commit -m "docs: add admin bot Jenkins deployment runbook"

## Final Verification

## Execution Adjustment

The static contract-test steps for Jenkinsfile text were intentionally omitted during implementation. Jenkinsfiles are deployment configuration, so source-text assertions would only detect formatting changes rather than pipeline behavior. The implementation keeps the existing Python test suite and validates the Jenkinsfiles through Jenkins Pipeline execution, image smoke testing, health checks, and the documented Feishu acceptance flow.

- [ ] Run git diff main...HEAD --check and confirm no whitespace errors.
- [ ] Run the full Python test, Ruff, and compile commands from Task 3.
- [ ] Verify .env remains ignored with git check-ignore .env.
- [ ] Verify git status --short is empty after commits.
- [ ] Configure two Jenkins Pipeline jobs loading Jenkinsfile.prod-build-ali and Jenkinsfile.prod-deploy-ali from main.
- [ ] Run the build Job once, deploy its archived immutable IMAGE_TAG, and complete the documented Feishu acceptance check.
