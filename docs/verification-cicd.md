# 仓库与 CI/CD 验收（2026-11-26）

正式仓库：https://github.com/Cai-Chang/Life-agent

## 已核实

- 本机 GitHub CLI 已登录 Cai-Chang，使用系统 keyring；未将凭据写入源码。
- main/develop 已推送，工作流及后续分支约定已入库。
- actionlint v1.7.12 与开发/交付 Compose 静态配置检查通过。
- 修复了前端锁文件中缺少版本的可选平台依赖；独立目录真实 npm ci 通过。
- 云端完整 CI：https://github.com/Cai-Chang/Life-agent/actions/runs/45753355809 ，提交 a325cc9b9d9f2f3950c878cfedda42f40a93f0a4，结论 success。
- 上述 CI 包含真实 PostgreSQL 后端测试、迁移、Worker 依赖检查、前端构建、桌面/手机浏览器测试、完整容器栈构建启动、Nginx 就绪和认证冒烟。
- 本机没有 Docker Engine，容器验收在 GitHub runner 完成。
- 一次后续 Git HTTPS 推送发生低速超时；改用官方 Git 数据 API 上传相同 blob/tree/commit，校验提交 SHA 相同后仅快进 main/develop，未强推。

## 交付验证

最终镜像流水线：https://github.com/Cai-Chang/Life-agent/actions/runs/45753550958

最终结论 success：test、publish-api、publish-frontend 均成功。

- 后端：16 passed；桌面/手机 E2E：4 passed。
- 发布提交：`ae221a0f7a1a9723517a2a913be5febc72f19744`。
- 两个镜像均已推送 `latest` 和 `sha-ae221a0f7a1a9723517a2a913be5febc72f19744` 标签，支持 linux/amd64 与 linux/arm64。
- API：`ghcr.io/cai-chang/life-agent-api@sha256:dc0281b18d0f8d0b7a7caeb20080c578eb3dde547939b260fd81bb5209417374`。
- 前端：`ghcr.io/cai-chang/life-agent-frontend@sha256:9ca8b6fef63641454edbd113cf3952eebb493b38d9e11416a41190c59e48df5e`。
- 摘要来自成功的 registry manifest push 日志；本机未验证拉取私有镜像。
- 本次通过 workflow_dispatch 实测验收；初次 push 后未观察到自动运行记录，push/PR 触发配置已存在，后续真实开发推送仍需观察自动触发。
- 本次只补充验收文档的后续提交使用 [skip ci]，避免重复构建和发布相同应用代码。镜像版本以上述已测试提交为准。

## 边界

部署地址尚未指定，未部署服务器。GHCR 包未自动改为公开，分支保护未配置。Autoloop 保持关闭。本次只验收工程基础和账号/个人空间，不代表后续日程、AI 或任务执行已经实现。
