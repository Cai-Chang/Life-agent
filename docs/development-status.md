# LifeAgent 开发进度

## 当前基线

- 2026-11-25：已读取 LifeAgent_V0.1.md；配置后台开发规则。
- 初始目录仅有需求文档，无应用代码。
- DEV-01：工程初始化已完成；本机启动、GitHub 云端 CI 与真实容器栈验收通过，API/前端多架构镜像已发布。
- DEV-02：注册、登录、退出、个人空间与用户隔离已实现并通过本机验收。
- DEV-03：日程与待办手动闭环本机、云端与容器验收完成；PR #1 待审查，未合并。
- DEV-04 至 DEV-08 尚未开始。

## 验收记录

最新本机验收：后端32项测试、桌面/手机12项E2E、前端类型检查与生产构建通过；日程待办闭环可用。DEV-03 云端结果见 `docs/verification-dev03.md`。上一阶段工程基础的 Compose 默认和 Worker profile 校验通过，容器栈已在 GitHub runner 实际构建、启动并通过认证冒烟；API/前端镜像发布成功。详见 `docs/verification-dev02.md` 与 `docs/verification-cicd.md`。

## 2026-11-25 · 首轮 DEV-01a：后端骨架与健康检查契约

- 已保留全部原有文件。目录尚无 Git 仓库，没有提交、推送或发布。
- 新增 `backend/pyproject.toml`、`backend/lifeagent/`、`backend/tests/test_health.py`、`.gitignore`、`README.md`。
- 实现 `/health/live` 返回 200；数据库尚未配置，`/health/ready` 明确返回 503。此子项仅完成 API 骨架及契约，不代表 DEV-01 整体完成。
- 查阅 FastAPI 官方安装/启动说明：https://fastapi.tiangolo.com/deployment/manually/ 。直接依赖固定为本机实测的 FastAPI 0.141.1、Uvicorn 0.52.3、pytest 9.1.1、httpx 0.28.1，Python 3.13.13。
- 实际执行 `UV_CACHE_DIR="$PWD/.uv-cache" uv lock --project backend`：失败，无法解析 pypi.org；未生成完整锁文件，未安装依赖、未改变系统环境。
- 实际执行 `python3 -m compileall -q backend`：通过。
- 实际执行 `python3 -m pytest -q backend/tests`：2 passed，使用本机已有依赖。出现 Starlette TestClient 对 httpx 的弃用警告，后续依赖整理时处理。
- 未验收：隔离环境安装与完整依赖锁定、真实监听端口冒烟、数据库就绪、迁移、前端、Compose、CI；本机未发现 docker 命令。没有浏览器或端到端测试结果。
- 下一步仍为 DEV-01：先解决依赖来源并生成完整锁文件、在隔离环境复验本子项，再推进 PostgreSQL/SQLAlchemy/Alembic 与真实就绪检查。不得跳至 DEV-02。
- 本轮通过卡片请用户选择恢复依赖访问或提供离线包；恢复后只补依赖与验证，不重建已有骨架。

## 2026-11-25 · 回答续办 DEV-01a：项目专用 Conda 环境

- 本轮回答（卡片 2）：用户要求已有 Conda 则使用 Conda 建立项目专用环境。此为本项目环境选择，不推定为其他项目授权。
- 核实已有 `/opt/miniconda3/bin/conda` 26.3.2，未安装或修改基础 Conda。
- 查阅 Conda 官方 create 文档：https://docs.conda.io/projects/conda/en/stable/commands/create.html 。
- 实际执行离线创建，首次因用户级环境登记表不可写而回滚；原 `.conda/lifeagent` 残留保留，不可用。最初缓存路径分隔符误用冒号，随后修正为逗号。
- 成功命令：`CONDA_REGISTER_ENVS=false CONDA_PKGS_DIRS="$PWD/.conda-pkgs,/opt/miniconda3/pkgs" conda create --prefix "$PWD/.conda/lifeagent-dev" --offline --copy --no-default-packages python=3.13.13 pip -y`。仅不登记用户环境列表，未修改权限或安全检查。
- 实际执行 `.conda/lifeagent-dev/bin/python --version`：Python 3.13.13；检查 sys.executable 与 sys.prefix 均在项目内。此环境没有 FastAPI，确认与基础环境隔离。
- 实际执行该 Python 的 `pip install --cache-dir "$PWD/.pip-cache" fastapi==0.141.1 uvicorn==0.52.3 pytest==9.1.1 httpx==0.28.1`：重试后失败，pypi.org 域名解析失败。不是版本不存在的证据。
- 新增 `environment.yml`，更新 README 与忽略规则。环境说明仅固定直接版本，不是完整锁文件。
- 本轮完成专用 Python 环境；没有在专用环境运行接口测试、没有监听端口验证，没有完成完整依赖锁定，DEV-01 仍未完成。
- 下一步：用户恢复软件包访问或提供离线依赖后，只向 `.conda/lifeagent-dev` 补装应用依赖、锁定传递依赖并复验已有骨架；不重建环境、不重复开发接口。其后才推进数据库与迁移等剩余子项。

## 2026-11-25 · 阻塞说明与现状复核（回答卡片 4）

- 用户询问“具体遇到了什么问题？”，未授权修改网络或权限，本轮仅核实与说明，不视为网络已恢复。
- 专用环境 Python 3.13.13 正常，sys.prefix 位于 `.conda/lifeagent-dev`；FastAPI 尚未安装。
- 实际执行专用 Python 的 `socket.getaddrinfo('pypi.org', 443)`：`gaierror(8, 'nodename nor servname provided, or not known')`，说明后台执行环境无法解析该域名。
- 实际执行 `.conda/lifeagent-dev/bin/python -m pip download --no-deps --retries 0 --timeout 5 --dest /tmp/lifeagent-dependency-probe fastapi==0.141.1`：退出 1，未下载到包。pip 的“没有匹配版本”不能证明包版本不存在，因为前置域名解析已失败。另有默认缓存目录不可写警告，缓存被禁用，不是本次下载受阻的直接依据。
- 当前证据无法区分主机网络故障与后台沙箱网络限制；不声称整台电脑断网，不修改 DNS、代理、权限或安全检查。
- 本轮无应用代码改动，无新增测试通过记录；仍待用户在普通终端核实软件包站点能否访问，或提供离线包。恢复后仅补装依赖、锁定及复验已有后端，不重建环境。

## 2026-11-25 · 软件包网络阻塞根因核验

- 在当前聊天中对同一个 `.conda/lifeagent-dev/bin/python` 进行了沙箱内与普通主机网络的对照检查。
- 沙箱内：`pypi.org` 与 `files.pythonhosted.org` 的 `socket.getaddrinfo` 均报 gaierror，PyPI HTTPS 请求因解析失败而失败。
- 普通主机网络：两个域名均解析成功，`https://pypi.org/simple/fastapi/` 返回 HTTP 200。因此当前阻塞来源是后台网络限制，不能归因为整台电脑断网。
- 已检查中台 Codex 插件：`edit` 对应 `workspace-write`，且设置 `approval_policy="never"`；默认不允许 shell 联网，后台也不能弹命令审批，所以重复尝试安装不会解决。
- 已准备只开启该入口 shell 联网的启动脚本 `autoloop-chat/scripts/codex-lifeagent-network.sh`，尚未接入或激活。待用户明确确认后，为 LifeAgent 使用专用 Agent 配置，保持 workspace-write 文件写入范围，再真实补装依赖及复验；不把“网络检查通过”当成“依赖已安装”。

## 2026-11-25 · 用户授权联网、锁定依赖与隔离复验

- 用户已明确批准 LifeAgent 后台联网。新增 `lifeagent-codex` 专用 Agent：仍为 `access: edit`，仅通过专用启动入口设置 `sandbox_workspace_write.network_access=true`；LifeAgent 两条规则改用此 Agent。试跑和其他 Agent 不受此授权扩展。
- `agent-autoloop check` 通过，`rules explain` 显示两条 LifeAgent 规则使用专用联网 Agent，保持 `lifeagent-work` 单并发组。
- 实际执行 `UV_CACHE_DIR="$PWD/.uv-cache" uv lock --project backend`：成功解析 23 个包并生成 `backend/uv.lock`。
- 实际执行 `uv export --project backend --locked --all-groups --no-emit-project --format requirements-txt --output-file backend/requirements.lock`：生成带哈希、固定传递依赖的安装清单。
- 实际执行 `.conda/lifeagent-dev/bin/python -m pip install --cache-dir "$PWD/.pip-cache" --require-hashes -r backend/requirements.lock`：成功，仅安装到既有项目环境。
- 实际执行 `.conda/lifeagent-dev/bin/python -m pip check`：No broken requirements found。
- 实际执行 `.conda/lifeagent-dev/bin/python -m pytest -q backend/tests`：2 passed。存在 Starlette TestClient 的 httpx 弃用警告，不影响本次通过，后续再处理兼容迁移。
- 使用该 Conda Python 临时启动 Uvicorn，真实 HTTP `/health/live` 返回 200/alive，`/health/ready` 返回预期的 503/dependencies_not_configured；完成后已停止本次测试进程。
- DEV-01a 的依赖安装及隔离复验完成。数据库/迁移、前端、Compose、CI 等 DEV-01 剩余部分仍待开发。
- 已派发第 8 轮进行真实 Autoloop 后台只读联网验收，最终结果待该轮记录；不在验收轮重复安装依赖或修改应用代码。

## 2026-11-25 · 真实后台联网验收完成

- 第 8 轮由 `lifeagent-codex` 实际执行，只做只读检查，未重复安装依赖或修改应用文件。
- 后台使用项目 `.conda/lifeagent-dev/bin/python`：`pypi.org` DNS OK；`files.pythonhosted.org` DNS OK；`https://pypi.org/simple/fastapi/` HTTP 200。该轮最终回复“LifeAgent 后台网络验收通过”。
- 之前的网络检查卡片 6 和旧环境通知 5 已由本次修复记录替代；无需再让用户重复选择“普通终端能访问”。项目仍从 DEV-01 尚未完成的数据库/迁移等子项继续，不把这次修复等同于产品已完成。

## 2026-11-25 · DEV-01b：迁移骨架与数据库就绪检查（真实 PostgreSQL 待验收）

- 用户本轮要求“继续推进项目”，按最早未完成任务推进一个数据库基础子项，未推进登录或业务功能。
- 未发现项目 AGENTS.md；`git status --short` 显示当前不是 Git 仓库，未提交、推送、部署或修改中台。
- 新增 `backend/lifeagent/database.py`、`migrate.py`、`backend/migrations/env.py` 和 `versions/0001_baseline.py`；基线只建立版本跟踪，没有业务表。
- 就绪接口从固定 503 改为只读检查 PostgreSQL 连接与 Alembic heads；版本一致才返回 200；未配置、连接失败或迁移未完成均返回 503，错误不暴露连接串。请求不会自动升级数据库。
- 更新 README、健康检查测试，新增数据库测试。参考 SQLAlchemy 引擎配置和 Alembic runtime 官方文档（README 链接）。
- 实际执行 `UV_CACHE_DIR="$PWD/.uv-cache" uv add --project backend 'sqlalchemy==2.0.58' 'alembic==1.20.1' 'psycopg[binary]>=3.2,<4' --no-sync`、`uv export --project backend --locked --all-groups --no-emit-project --format requirements-txt --output-file backend/requirements.lock` 成功；完整锁定到 psycopg 3.3.9。
- 实际执行项目 Python 的 `pip install --cache-dir "$PWD/.pip-cache" --require-hashes -r backend/requirements.lock` 成功；`pip check` 无依赖冲突（默认缓存不可写警告不影响检查）。
- 实际执行 `.conda/lifeagent-dev/bin/python -m pytest -q backend/tests`：7 passed，1 条既有 Starlette/httpx 弃用警告。包含原健康检查、未配置、连接失败、配置错误脱敏、就绪响应、SQLite 上真实版本查询、PostgreSQL 离线基线 SQL 生成。
- SQLite 仅验证版本判断；就绪成功响应测试使用替身，不是 PostgreSQL 实测。`command -v postgres` 和 `command -v docker` 均未找到命令，未启动或更改系统服务、未访问用户数据库。
- 未验收：真实 PostgreSQL 空测试库升级、真实连接成功且版本匹配返回 200、真实迁移落后检查；DEV-01b 尚未完整验收，DEV-01 整体仍未完成。
- 下一步只补以上真实数据库验收。通过卡片确认测试数据库来源；不重建 Python 环境、不重复已有后端开发。

## 2026-11-25 · DEV-01b 续办：项目内 PostgreSQL 已安装，初始化受后台限制

- 本轮用户选择“在项目内准备独立测试数据库”（对应 open 卡片 7），只用于本次续办，不记长期决定。
- Conda 隔离安装 PostgreSQL 17.12 至 `.conda/postgresql-test`，原 `.conda/lifeagent-dev` 未重建或变更。新增 `postgresql-test-osx-arm64.lock` 记录已安装包的显式来源。
- 首次 conda create 因条款元数据缓存位于不可写用户目录失败；第二次仅将 conda_anaconda_tos.path.CACHE_DIR 定向到工作区 `.conda-pkgs/tos-cache`，保留插件和条款检查，使用 conda.cli.main.main 执行原 create 参数成功。无权限扩大、无系统配置更改。过程中另有 sysctl/通知缓存/用户环境登记不可写警告，安装最终退出 0。
- 新增 `scripts/verify_postgresql.py`：独立新测试目录、peer 本机身份认证、仅 Unix socket；自动检查迁移前503、升级后200及重复升级，结束清理本轮进程但保留数据。README 新增普通终端执行入口。
- 两次实际运行 `.conda/lifeagent-dev/bin/python scripts/verify_postgresql.py` 均在 initdb bootstrap 失败：shmget(size=56) Operation not permitted；第二次显式 mmap 配置仍失败。首次 initdb 默认清理自身创建的失败数据目录（无既有数据）；第二次使用 --no-clean 保留失败目录 `.conda/pg-check-iavtxwqz/data`。
- PostgreSQL 服务和测试 API 均未启动，未执行迁移或HTTP断言；不能声称真实数据库验收通过。未修改已有用户数据库、系统服务或中台。
- 实际回归 `.conda/lifeagent-dev/bin/python -m pytest -q backend/tests`：7 passed、1 条既有弃用警告；脚本 py_compile 成功。`conda list --prefix ... --explicit` 成功生成平台包清单。
- 当前需本人在普通终端运行 README 中脚本并返回输出；恢复后只核实脚本的真实数据库结果，必要时修复，更新进度，不重装环境或重复开发。DEV-01b 和 DEV-01 整体仍未完整验收。

## 2026-11-25 · 用户要求“帮我验证”：后台实测复核

- 实际执行 `.conda/lifeagent-dev/bin/python scripts/verify_postgresql.py`，退出 1；仍在 initdb bootstrap 的 shmget(size=56) 被系统拒绝，失败目录 `.conda/pg-check-zl0dmlrc/data` 已保留。
- 数据库和测试 API 未启动，迁移前503、迁移后200及重复升级断言均未执行，真实数据库验收仍未完成。
- 实际执行 `.conda/lifeagent-dev/bin/python -m pytest -q backend/tests`：7 passed、1 条既有弃用警告。未修改应用代码、环境或权限。
- 原卡片 8 仍等待本人在普通终端运行验证脚本并返回输出，本轮不重复建卡、不安排定时重试；收到结果后只核实剩余数据库验收。

## 2026-11-26 · 数据库共享内存阻塞修复与主机实测

- 当前聊天按用户“帮我解决”要求，在普通主机环境运行原验收脚本：initdb、PostgreSQL 启动、迁移前 503/migrations_pending、迁移后 200/ready、重复升级均成功；测试进程已停止，原结果保留在 `.conda/pg-check-2tkscb2l`。该对照确认原错误是 Agent 沙箱禁止共享内存系统调用，不是主机内存不足或基线迁移失败。
- 为避免每轮在后台启动数据库而重复受阻，新增普通主机一次性安装入口 `autoloop-chat/scripts/install-postgresql-service.py`，注册当前用户登录服务 `local.lifeagent.postgresql-test`。
- 数据库数据在 `.conda/postgresql-host/data`，Unix socket 位于 `.conda/postgresql-host/socket`；使用 peer 本机身份认证，目录和 socket 权限 0700。实际 SQL 检查 `listen_addresses` 为空，数据库未监听 TCP。
- 调整 `scripts/verify_postgresql.py`：检测到该项目服务时仅连接，每轮创建全新 `lifeagent_verify_<随机标识>` 空测试库；保持应用和迁移代码在 Agent 既有沙箱中执行。测试完成停止本轮 API，保留数据库与日志，不停止共享测试服务。保留 `--fresh-cluster` 供普通主机独立排查。
- 主机环境使用新入口实测成功，日志目录 `.conda/pg-check-64zj2_q7`，迁移前503、迁移后200和重复升级通过。后端回归 7 passed，1 条已有 Starlette/httpx 弃用警告。
- 第 14 轮已派给真实后台执行同一脚本，未授予 Codex full 权限；最终结果待该轮完成。当前模型连接有重试，不能将模型连接等待误报为数据库初始化失败。

## 2026-11-26 · 第14轮真实后台数据库验收通过

- Autoloop 启动的 `lifeagent-codex` 在原有 edit/workspace-write 权限下实际运行 `.conda/lifeagent-dev/bin/python scripts/verify_postgresql.py`，退出码 0。
- 成功连接项目主机 PostgreSQL 服务；使用全新空测试库 `lifeagent_verify_d36c4ddda3ba487c`；迁移前 `(503, migrations_pending)`，迁移后 `(200, ready)`，重复升级后保持就绪。
- 验收记录位于 `.conda/pg-check-rqgsjy18`。本轮 API 测试进程已停止，项目数据库登录服务保持运行。未使用其他项目数据库、未扩大 Codex 文件权限。
- 第14轮已通过 resolve 回执结案原阻塞卡片8，无需用户重复到普通终端执行相同脚本。
- DEV-01b（PostgreSQL 连接、基线迁移、真实就绪检查）验收完成；只有版本表，没有登录、日历、待办等业务表。DEV-01 仍有前端基础、Compose、CI 等待完成，不能称为整个软件开发完成。

## 2026-11-26 · 当前对话完成工程基础并推进 DEV-02

- 用户要求“补齐工程初始化，再推进注册登陆与个人空间”。当前对话直接实现，没有启动 Autoloop。
- 新增前端 React 19.3.1 + TypeScript 7.0.2 + Vite 8.3.8，依赖已安装并保存锁文件（代码尚未 Git 提交）。页面涵盖注册登录、概览、空间管理、昵称/时区、退出与会话失效；桌面和手机均已真实操作。
- 后端新增账号、个人空间、成员、会话和审计模型及 `0002_auth_personal` 迁移；Argon2id、服务端会话 token 哈希、HttpOnly Cookie、Origin/CSRF、输入脱敏与基础限流。账号/空间/成员/会话在同一事务创建，空间只允许本人访问。
- 后端测试16项通过，新增真实 PostgreSQL 账号隔离、并发注册、过期/撤销会话及安全测试；前端E2E共4项通过；生产构建与类型检查通过。
- 原生开发脚本已实测创建并迁移 lifeagent_dev 库，启动 UI5173/API8000，经前端代理查询就绪返回200；独立真实迁移验证仍通过。未删除用户已有库或资料。
- 新增 Dockerfile、Nginx、Compose、环境生成器、可选 Worker 基础入口与 CI。使用经官方 SHA256 验证的 Compose v5.8.0 校验默认及 Worker profile 成功。当前没有 Docker Engine，镜像构建及容器栈未实测；无远端，因此云端 CI 未运行。
- 本地仓库已初始化 develop 分支，未提交、推送或发布。私密配置/本地数据库不入库。ADR 与启动、验证文档已更新。
- DEV-02 本地闭环完成。下一业务任务为 DEV-03（日程/待办 CRUD 与冲突检查）；不得将 Worker 基础待机入口当作任务执行实现，不得将当前界面当作已实现 AI 规划。
- 收尾实测所有服务关闭后的原生冷启动：启动器成功恢复项目数据库、迁移开发库、启动 UI/API，就绪返回200。完成后已停止临时 UI/API 和项目数据库；Autoloop 中台与网页/QQ 服务始终保持关闭，开发数据保留。启动命令见 README。

## 2026-11-26 · 正式仓库与镜像持续交付

- 已关联用户指定的 Cai-Chang/Life-agent 仓库，建立本机首次提交。后续 main/develop/feature 分支工作流及 PR 模板、CODEOWNERS 已准备。
- CI 增加真实容器启动、Nginx 认证冒烟；通过后仅 main/版本标签发布 API 与前端多架构 GHCR 镜像。服务器部署地址尚待确定。
- actionlint v1.7.12 校验通过，开发/交付 Compose 配置校验通过；本机原生代理的注册201、个人空间修改200、退出204与退出后401已实测。Mac 未安装 Docker Engine，不声称本机容器验收通过。
- GitHub 登录已核实，下一步首次推送并以 Actions 实际运行结果记录远端验收。Autoloop 保持关闭。

- 首次推送 main/develop 成功；云端运行 45752426546 的后端测试、迁移和 Worker 检查通过，但 npm ci 因锁文件包含无版本可选依赖而失败。已在独立临时目录移除空条目并重新解析锁文件，补齐平台可选包的版本和完整性信息；保持直接依赖版本不变。后续运行继续验收容器与镜像发布。

- 最终远端运行 45753550958 全部成功：16 项后端测试、4 项桌面/手机 E2E、容器栈及认证冒烟通过，API 与前端 amd64/arm64 镜像已推送 GHCR。实测方式为手动触发工作流；初次推送未观察到自动运行，后续 push 自动触发需继续核实。详细提交、镜像 digest 与边界见 verification-cicd.md。

## 2026-11-26 · DEV-03 日程与待办手动闭环

- 新增0003迁移与个人业务服务、前端日程/待办、首页真实统计；创建、查看、编辑、取消/恢复、完成、删除与筛选已实现。
- 按空间锁定事务，重查冲突和版本；重复操作与并发请求不产生重复写入或静默覆盖。写入保留元数据审计目标 ID。
- 本机后端32项、桌面/手机12项、类型检查与构建通过；迁移升级/回退再升级保留账号。详细范围、测试与限制见 docs/verification-dev03.md。
- 当前在 feature/calendar-tasks 开发，待 PR/CI 验收，不自动合并 main 或部署。Autoloop 保持关闭。

- DEV-03 云端运行45765572578已成功：32后端、12浏览器、容器栈与日程待办冒烟均通过。PR #1目标develop，未合并；功能分支不发布镜像。自动push/PR触发未观察到，本次实测由手动触发完成，保留该工程限制记录。

## 2026-11-26 · 用户本机旧服务与迁移不同步修复

- 实际5173页面连接的是上午旧API，未提供日程/待办接口，lifeagent_dev为0002，ready503。独立测试/云端通过不能证明这套旧本机服务已更新。
- 已停止确认的旧启动器、显式升级开发库至0003并重启，账号/空间/成员/会话行数保持；现有服务ready200，新API已加载。Autoloop保持关闭。
- 启动器加入后端自动重载、端口占用提示、真实就绪后显示地址；页面为接口缺失和503显示具体提示。仍要求新增迁移后完整重启。
- 本轮32后端/12浏览器/构建通过，真实运行服务保留给用户继续测试；本轮修复随后在云端45784429153重新验收成功，受测业务提交b11cb04；详见verification-dev03末节。
