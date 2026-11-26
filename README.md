# LifeAgent

个人与家庭智能管家的开发项目。正式仓库：[Cai-Chang/Life-agent](https://github.com/Cai-Chang/Life-agent)。需求基线为 [LifeAgent_V0.1.md](LifeAgent_V0.1.md)。

当前已可使用：注册、登录、退出、个人空间、空间改名、昵称和 IANA 时区设置，以及日程与待办管理。账号使用 Argon2id 密码哈希、可撤销的服务端会话和 HttpOnly Cookie；个人空间按用户归属隔离。日程支持周/月查看、新建、编辑、取消、恢复及重叠检查；待办支持优先级、截止时间、四种状态、关联日程、筛选和删除。AI 对话已提供模型配置、会话历史、失败重试和清除入口，需要你先配置真实模型服务；MCP、审批和 Agent 任务执行属于后续阶段。

`frontend/` 是 LifeAgent 产品界面；`autoloop-chat/` 是独立的开发任务管理工具。运行 LifeAgent 不需要启动 Autoloop。

## 本机启动（当前 Mac）

需要 Node.js 24+、项目专用 Conda Python 和已安装的项目 PostgreSQL 服务。首次设置命令见后文。

在项目根目录执行：

```sh
.conda/lifeagent-dev/bin/python scripts/dev.py
```

打开 **http://127.0.0.1:5173**，点击“创建账号”。注册时账号、个人空间和成员关系在同一事务中创建；没有默认账号或内置密码。

开发脚本先检查端口，启动已经安装但尚未运行的项目 PostgreSQL 服务，只连接本项目的 Unix socket，准备 `lifeagent_dev` 数据库并显式执行迁移，然后启动 API 和前端，待数据库就绪检查通过才显示访问地址。已有数据保留。后端开发模式自动重载业务代码；新增迁移后仍需完整重启启动器执行迁移。按 Ctrl+C 停止本次前端/API，数据库服务仍保持运行，Autoloop 不会启动。

如果页面提示接口未更新，或刚更新代码后日程/待办不可用，请在原启动终端按 Ctrl+C，再运行上面的启动命令并刷新浏览器。不要在旧服务运行时再开一套启动器；数据库未迁移或旧后端未重启时，前端热更新成功不代表整套应用已更新。

## 模型对话（DEV-04）

登录后点击 **AI 对话 → 模型设置**，选择 DeepSeek 或通义千问的对应地域，填写模型名称及 API Key，勾选允许发送对话内容，再点“保存模型配置”和“测试连接”。成功后可发送消息，刷新可恢复历史；失败的最后一轮可以手动重试。密钥不要发到聊天、写进源码或放入 VITE_* 变量。

默认模型名称来自当前官方文档，仍需对应服务的有效 API Key、可用模型权限与额度。通义可选填业务空间 ID，密钥须与地域一致。API 未配置时明确提示，不使用模拟回复替代真实模型。

每次请求只发送当前会话最近最多12轮完整对话及新消息，历史正文总量有上限；不会自动读取其他会话、日程或待办。聊天不执行写入；计划、审批及工具执行后续实现。清除会话删除其消息，不影响日程、待办或模型配置。

本机凭据按账号保存在 `.local/model-settings/` 的0600私有文件，已同时加入Git与Docker忽略规则，Vite禁止提供`.local`目录；不会通过接口读回密钥。Docker使用独立的`model-settings`数据卷；`LIFEAGENT_MODEL_CONFIG_DIR`可由服务端指定私有配置目录，不应置于公开静态目录。当前依赖主机文件权限，不声称磁盘加密或跨服务器密钥管理已经实现。

已实现与真实模型验收状态见 [DEV-04报告](docs/verification-dev04.md)；自动化测试中的模拟模型不代表真实外部服务已接通。

## 新环境安装

```sh
conda create --prefix "$PWD/.conda/lifeagent-dev" python=3.13.13 pip -y
.conda/lifeagent-dev/bin/python -m pip install --require-hashes -r backend/requirements.lock
npm --prefix frontend ci
```

Apple Silicon macOS 的项目 PostgreSQL 可从已锁定包清单安装：

```sh
conda create --prefix "$PWD/.conda/postgresql-test" --file postgresql-test-osx-arm64.lock -y
.conda/lifeagent-dev/bin/python autoloop-chat/scripts/install-postgresql-service.py
```

服务安装脚本需在普通主机终端执行，只建立当前用户的 LifeAgent 测试数据库服务；后台 Codex 不要在沙箱中运行 initdb 或使用 `--fresh-cluster`。其他平台推荐使用下方 Docker 环境。

## Docker Compose

需要已安装并运行的 Docker Engine / Docker Desktop：

```sh
python3 scripts/configure_env.py
docker compose up --build -d
```

打开 **http://localhost:8080**。配置生成器仅在不存在时创建权限为 0600 的 `.env`，生成随机本地数据库密码，不打印或覆盖已有凭据。数据库不发布主机端口，只有前端绑定 `127.0.0.1:8080`。

启动顺序：PostgreSQL 健康 → 一次性迁移成功 → API 就绪 → 前端。停止使用 `docker compose down`；此命令保留数据卷。不要加 `-v`，除非明确要删除本地数据。

`worker` 是可选的基础入口，通过 `--profile worker` 启用，目前只检查数据库和待机，不消费任务，不代表 DEV-07 的执行功能已完成。

本地 Compose 默认开发模式，HTTP Cookie 不设置 Secure。真正 HTTPS 部署时必须配置 `APP_ENV=production` 与 `APP_ORIGIN=https://你的域名`，并通过 HTTPS 反向代理提供服务。生产配置会强制 HTTPS origin 和 Secure Cookie。邮件验证、找回密码、共享限流、运营备份等仍待后续完善，不将本次本地验收等同于公开上线验收。

## 数据库与迁移

- PostgreSQL + SQLAlchemy，显式 Alembic 升级：在 `backend/` 执行 `../.conda/lifeagent-dev/bin/python -m lifeagent.migrate`，环境中需有 `DATABASE_URL`。
- `0001_baseline` 建立版本跟踪；`0002_auth_personal` 建立用户、个人空间、成员、会话和审计表；`0003_calendar_tasks` 增加日程、待办、幂等操作记录及审计目标 ID；`0004_conversations` 增加会话和消息。
- 请求和应用启动不会自行 `create_all` 或迁移；开发启动器和 Compose 的迁移步骤会显式升级。
- `/health/live` 仅验证进程；`/health/ready` 验证真实连接和迁移版本，未就绪返回 503，就绪返回 200，不暴露连接串。
- 原生开发库为 `lifeagent_dev`。pytest 和浏览器测试会另外创建随机测试库，只清理自己创建的测试库，不清空开发库。
- 项目 PostgreSQL 服务：`local.lifeagent.postgresql-test`，数据在 `.conda/postgresql-host/data`，socket 在 `.conda/postgresql-host/socket`，仅当前用户访问，未开放 TCP。

停止/恢复原生数据库服务：

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/local.lifeagent.postgresql-test.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.lifeagent.postgresql-test.plist
```

## 验证

```sh
.conda/lifeagent-dev/bin/python -m pip check
.conda/lifeagent-dev/bin/python -m pytest -q backend/tests
npm --prefix frontend run build
.conda/lifeagent-dev/bin/python scripts/run_e2e.py
.conda/lifeagent-dev/bin/python scripts/verify_postgresql.py
```

浏览器测试默认使用本机 Chrome。Linux/CI 使用 `npx playwright install --with-deps chromium` 准备浏览器，并设置 `CI=1`。通过 `LIFEAGENT_TEST_DATABASE_URL` 指定测试 PostgreSQL 的管理连接时，测试仍会创建独立随机数据库，不修改该连接指向的已有业务库。

CI 配置位于 `.github/workflows/check.yml`：固定官方 Actions 提交，运行后端真实 PostgreSQL 测试、前端类型检查与构建、桌面/手机 E2E、Compose 校验、真实容器启动与认证冒烟。main 或版本标签通过后自动发布 API/前端的 amd64、arm64 镜像到 GHCR，部署地址稍后确定；部署说明见 [仓库与 CI/CD](docs/repository-and-cicd.md)。云端 CI 是否通过必须以实际工作流结果为准。

首次云端测试和镜像发布均已通过：[CI/CD 验收报告](docs/verification-cicd.md)（本次手动触发验收）。

最新本机测试结果及未验收项见 [验收报告](docs/verification-dev02.md) 和 [开发进度](docs/development-status.md)。

## 接口

前缀 `/api/v1`。开发环境 API 文档在 http://127.0.0.1:8000/docs。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/auth/register` | 注册并创建个人空间、建立会话 |
| POST | `/auth/login` | 登录并轮换当前浏览器会话 |
| POST | `/auth/logout` | 撤销当前会话并清除 Cookie |
| GET / PATCH | `/me` | 获取资料、修改昵称和时区 |
| GET | `/workspaces` | 获取本人的个人空间 |
| GET / PATCH | `/workspaces/{id}` | 读取空间或修改空间名，仅允许本人 |
| GET / POST | `/events` | 按 start/end 时间范围查询、创建日程 |
| GET / PATCH / DELETE | `/events/{id}` | 读取、修改、取消日程（保留关联待办） |
| GET / POST | `/tasks` | 查询、创建待办，支持状态/截止时间筛选 |
| GET / PATCH / DELETE | `/tasks/{id}` | 读取、修改、永久删除待办 |
| GET / PUT / DELETE | `/model-settings` | 读取配置状态、保存或删除本人模型配置，密钥不读回 |
| POST | `/model-settings/test` | 用最小测试消息检查真实模型连接 |
| GET / POST | `/conversations` | 分页列出或创建本人会话 |
| GET / DELETE | `/conversations/{id}` | 分页读取历史、按版本清除会话 |
| POST | `/conversations/{id}/messages` | 发送消息并等待模型回复 |
| POST | `/conversations/{id}/messages/{message_id}/retry` | 手动重试最新失败回复 |

写请求使用 JSON。浏览器会话由 HttpOnly Cookie 携带；已登录写请求需从注册、登录或 `/me` 的响应取得 `csrf_token` 并在 `X-CSRF-Token` 头中提交。前端仅在内存保存该 CSRF token，不将密码或会话凭据写入 localStorage。

日程和待办写接口还要求 `Idempotency-Key`（8–128 位 ASCII 字母、数字、点、横线、下划线），同一操作重试须保持相同键和参数。创建成功返回 201；修改/删除返回 200；同键不同参数、重叠日程、旧版本更新或非法状态转换返回 409。PATCH 和 DELETE 的 JSON 中必须包含当前 `version`。DELETE 日程表示取消，PATCH `status=active` 可恢复，恢复时重新检查冲突；DELETE 待办为永久删除，界面会先确认。

时间参数须包含 UTC 偏移或 Z；服务端按 UTC 存储/返回，界面按个人 IANA 时区输入和展示。相邻日程不冲突，重叠则拒绝保存；跨日事件在经过的每一天显示。夏令时重复时间需在界面选择具体时刻，不存在的时刻不能保存。日程列表要求范围，最长一年；日程/待办列表支持 `limit`、`offset`，响应含 `has_more`，界面自动加载后续页。

聊天创建、发送、清除和重试也需 `Idempotency-Key`。同键消息重试不重复保存用户消息或调用模型；正文不同返回409。每个会话同一时间只生成一条回复，状态持久化，可刷新查看；每个账号最多两条同时生成，新消息每分钟20条，每条回复最多初次调用加两次手动重试。外部调用不占用数据库事务，迟到回复不能覆盖新重试或恢复已清除历史。历史用`before`序号分页；POST消息响应中`items`仅含本轮用户与助理消息。失败的模型调用会以`status=failed`消息保存，不当作已经成功回复；尚未保存的非法输入或配置缺失直接返回错误。

## 目录与阶段

```text
backend/lifeagent/     API、认证、业务基础、Worker 入口
backend/migrations/    显式数据库迁移
backend/tests/         单元与真实 PostgreSQL 集成测试
frontend/              React 产品界面及 Playwright E2E
deploy/                Dockerfile 和同源反向代理
scripts/               原生启动、配置、测试与验收工具
docs/                  决策、架构与真实开发记录
autoloop-chat/         独立的 Autoloop 管理工具
```

当前完成 DEV-03 的日程与待办手动闭环，本轮验收见 [DEV-03 报告](docs/verification-dev03.md)。DEV-04 已实现模型对话与会话基础，本机已完成真实外部模型连通和两轮上下文验收；新环境仍需自行配置模型。后续 DEV-05 为 MCP 工具及适配 PoC，DEV-06 才加入规划审批；当前不包含自动规划执行或主动提醒。代码通过正式 GitHub 仓库管理；main 用于稳定镜像交付，develop 用于后续开发集成。
