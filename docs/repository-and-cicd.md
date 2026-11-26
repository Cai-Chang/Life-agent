# 仓库管理与 CI/CD

正式仓库：[Cai-Chang/Life-agent](https://github.com/Cai-Chang/Life-agent)。当前本地 `origin` 使用其 HTTPS 地址；首次建库由用户授权，不覆盖任何远端历史。

## 分支与后续开发

- `main`：稳定代码；推送成功且 CI 通过后发布镜像。
- `develop`：开发集成分支；同样运行 CI，不自动发布镜像。
- `feature/<任务>`、`fix/<问题>`：正常开发分支，提交 PR 到 develop；阶段交付再通过 PR 合并 main。
- `vX.Y.Z` 标签：在确定的稳定提交上发布版本镜像；不会因为开发任务完成就擅自打版本标签。

`CODEOWNERS` 指定仓库所有者；PR 模板记录修改、真实验证与数据库影响。GitHub 的分支保护需要在仓库设置中应用，并非放入 CODEOWNERS 就自动启用。首次 Actions 检查可见后，建议为 main/develop 要求 PR 和 `test` 检查通过，禁用强制推送。

## CI

工作流：`.github/workflows/check.yml`，名称 `check`。触发：分支推送、v* 标签、PR（含转为 ready）和手动运行。

1. 使用独立 PostgreSQL 服务运行后端真实集成测试。
2. 执行迁移并验证 Worker 数据库依赖就绪。
3. npm ci、TypeScript/Vite 构建、桌面与手机 Playwright E2E。
4. 校验默认与可选 Worker 的 Compose 配置。
5. 真实构建并启动 PostgreSQL、迁移、API、Nginx 前端容器栈。
6. 通过 Nginx 验证真实就绪、前端页面、注册、会话、空间写入与退出。
7. 无论成功失败均销毁本次 CI 容器和测试卷；这是云端的独立虚构数据，不作用于用户本地数据库。

PR 只使用只读 contents 权限，不发布镜像。所有外部 Actions 固定到核实的完整提交号。

## CD 第一阶段：自动交付镜像

部署服务器尚未指定；当前配置的是持续交付镜像，不自动连接或部署到任何服务器。

同一个工作流中的 publish 作业依赖 test 成功，仅 main 推送、版本标签或在这些引用上手动运行时触发。使用 GitHub 为工作流自动提供的 GITHUB_TOKEN 发布本仓库关联的 GHCR 镜像，不需要在代码中配置个人 Token。

镜像：

```text
ghcr.io/cai-chang/life-agent-api
ghcr.io/cai-chang/life-agent-frontend
```

平台：linux/amd64、linux/arm64。标签包含 `sha-<完整提交号>`、版本标签，以及 main 对应的 `latest`。Actions 摘要另外记录 image digest 和提交 SHA；发布/回退建议选明确的提交或版本，不依赖随 main 更新的 latest。

GHCR 包的访问权限与代码仓库需要分别确认；若包尚未公开，部署机器需先具备对应包的拉取权限。不会自动把包或用户的其他资源改为公开。

## 使用已交付镜像

`compose.release.yaml` 使用预构建镜像，不要求在部署机器上安装源码构建工具：

```sh
python3 scripts/configure_env.py
export LIFEAGENT_VERSION=sha-这里替换为Actions成功发布的完整提交号
docker compose -f compose.release.yaml pull
docker compose -f compose.release.yaml up -d --wait
python3 scripts/smoke_deployment.py --url http://127.0.0.1:8080
```

默认仍为仅本机 HTTP 开发模式。真实 HTTPS 部署需配置 `.env` 中 APP_ENV/APP_ORIGIN，并设置外层 HTTPS 反向代理；数据库不发布主机端口。配置先迁移，再启动 API 和前端；不得将未经验证的旧版本镜像直接回退到已升级且不兼容的数据库上。

`--exercise-auth` 只用于可销毁的 CI 环境，会创建虚构账号；生产健康检查不要启用该选项。不要在本地或生产执行 CI 的 `down --volumes` 清理步骤。

## 连接与状态

首次推送需要有权限的 GitHub 身份。不要把 GitHub 密码、PAT、SSH 私钥、数据库凭据或 QQ AppSecret 提交到仓库或发到聊天中；使用 GitHub 连接或本机 Git 登录。

CI 配置校验、本地测试、Git 推送、云端 CI 和 GHCR 发布是不同状态。只有 GitHub 实际运行成功及 registry 返回对应镜像后，才能报告云端 CI/CD 已接通；本地文件已准备不代表远端已运行。
