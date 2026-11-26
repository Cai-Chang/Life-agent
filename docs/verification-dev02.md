# DEV-01 工程基础与 DEV-02 验收

日期：2026-11-26。环境：当前 Apple Silicon Mac；Python 3.13.13、Node 24.15.0、PostgreSQL 17.12、真实 Chrome。使用虚构账号，不使用生产数据。

## 本次实现

- 本地 Git 仓库 develop 分支、项目开发约定、环境示例、完整 Python/npm 依赖锁。
- React/TypeScript 产品页面：注册、登录、概览、个人空间改名、昵称与时区设置、退出、加载/错误/会话失效状态及移动端布局。
- FastAPI 认证与空间接口、Argon2id 哈希、服务端可撤销会话、HttpOnly Cookie、Origin 与 CSRF 验证、输入脱敏、单进程基础限流。
- Alembic `0002_auth_personal`：users、workspaces、memberships、auth_sessions、audit_logs。注册账号与空间原子创建，跨用户访问服务端拦截。
- 原生开发与测试脚本、Compose（PostgreSQL→迁移→API→前端）、可选 Worker 基础入口、Nginx 同源代理、GitHub Actions。

## 实际结果

| 检查 | 结果 |
| --- | --- |
| `python -m pip check`（项目 Conda） | No broken requirements found |
| `python -m pytest -q backend/tests` | 16 passed；真实 PostgreSQL，不以 SQLite 替代账号隔离测试 |
| `npm --prefix frontend run build` | TypeScript 检查与 Vite 生产构建成功 |
| `python scripts/verify_postgresql.py` | 新空测试库迁移前503、迁移后200、重复升级成功；日志 `.conda/pg-check-fo_xhp49` |
| `python scripts/run_e2e.py` | 4 passed：桌面和390px手机分别验证完整账号/空间流程及会话失效 |
| 浏览器视觉检查 | 桌面概览、空间页、注册页及手机注册/概览布局已查看；无横向溢出或脚本异常 |
| 原生一键启动 `scripts/dev.py` | 实际创建/迁移独立 lifeagent_dev 库、启动前端5173/API8000；同源 `/health/ready` 返回200 |
| 全部服务关闭后的冷启动 | 实际由启动器恢复已安装的项目数据库服务，再启动 UI/API，前端代理就绪返回200 |
| Worker `--check` | 已迁移数据库检查通过；明确没有任务执行队列，未冒充 DEV-07 |
| Compose 默认配置 | Docker 官方 Compose v5.8.0 `config --quiet` 成功 |
| Compose Worker profile | `--profile worker config --quiet` 成功 |
| 基础镜像 | 已从 Docker Hub 核对 Python、Node、PostgreSQL、Nginx 官方镜像标签存在 |
| Git 与私密文件 | 已初始化 develop；未提交或推送。Conda数据、QQ配置、测试报告与环境文件均被忽略 |

Compose CLI 下载自 Docker 官方 Release，SHA256 与官方发布文件一致，放在临时目录，仅用于本次配置校验，不安装系统服务。

## 测试覆盖的关键业务行为

- 未登录访问401；登录后返回本人资料和空间。
- 数据库只保存 Argon2id 密码哈希和会话 token 摘要，接口错误不回显密码。
- 相同邮箱大小写注册冲突；并发两次注册仅一次成功，只有一组账号、空间和成员记录。
- 登录轮换旧 token；退出和过期后旧 Cookie 失效。
- B 无法查询或改名 A 的空间，不能通过请求体伪造用户身份，不能复用其他会话的 CSRF token。
- 无效时区、无 CSRF 或跨站请求拒绝；生产要求 HTTPS 并设置 Secure Cookie。
- 昵称、时区和空间改名刷新后保留，重新登录仍回到原来的空间。

## 尚未执行与剩余边界

- 当前 Mac 没有 Docker Engine/Desktop，**没有实际构建镜像或启动容器栈**；Compose 配置校验不等同于容器运行通过。
- 未配置远端仓库，**GitHub 云端 CI 未运行**。工作流已包含真实数据库测试、构建、E2E 和镜像构建，需推送后验收。
- 保留一条 Starlette TestClient 对 httpx 的已有弃用警告；测试通过，后续版本需迁移。
- 注册登录和个人空间本地闭环已验收。日历、待办、AI 对话、MCP、任务执行、家庭共享与公开生产部署均未实现。
- Autoloop 未重启。完成验收后，本次临时 UI/API 与项目数据库均已停止，开发库与用户已有资料保留；下次执行 `scripts/dev.py` 会恢复已安装的项目数据库服务。测试用数据库由测试工具创建并清理。
