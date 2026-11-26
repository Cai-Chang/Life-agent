# LifeAgent 项目约定

以 `LifeAgent_V0.1.md` 为需求基线。先读 `docs/development-status.md`、`docs/decisions.md` 与 `docs/declined.md`，保留已有用户改动。每轮完成可验收子项，记录真实运行结果，未实现或未测试的功能不得声称完成。

- 后端：FastAPI、SQLAlchemy、Alembic、PostgreSQL；原生环境为 `.conda/lifeagent-dev`，不要重建或改系统 Python。
- 前端：`frontend/` React + TypeScript + Vite。`autoloop-chat/` 是独立管理工具，不是 LifeAgent 产品代码，后台开发不得修改它的服务、密钥或历史。
- 数据库：原生项目测试服务只通过 `.conda/postgresql-host/socket` 连接。后台不运行 initdb 或 `--fresh-cluster`，不擅自重装服务。测试只创建独立随机测试数据库，不能迁移或清空未授权数据库。
- 会话使用 HttpOnly Cookie，服务端仅保存会话 token 的哈希。认证写操作必须校验 Origin/JSON；登录后的写操作还必须验证绑定会话的 CSRF token。用户身份不得来自请求体或模型输出。
- 每次用户数据访问检查成员关系和所有权。MVP 仅个人空间，不提前开放邀请、家庭共享或任意成员写入。
- 新数据库结构必须写 Alembic 迁移，不允许应用启动或请求中自动 create_all/升级。账号、空间、成员与会话创建在同一事务中完成。
- 不将密码、session Cookie、数据库连接串或用户敏感正文写入日志、代码或测试报告；`.env` 与本地状态不得入库。
- 验证后端：`.conda/lifeagent-dev/bin/python -m pytest -q backend/tests`。认证集成测试使用新建的 PostgreSQL 测试库，不以 SQLite 替代。
- 验证前端：`npm --prefix frontend run build`。交互/认证流程改动还运行 `.conda/lifeagent-dev/bin/python scripts/run_e2e.py`。
- Docker/CI 仅在真实执行后才能报告通过；配置校验、镜像构建、容器启动和云端 CI 结果须分别记录。
- 不自动提交、推送、合并、部署或扩大权限。联网仅沿用用户已授权的 LifeAgent 专用入口。Autoloop 目前由用户关闭，当前对话不得为开发而擅自重启它。
