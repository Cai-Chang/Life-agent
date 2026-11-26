# Agent Autoloop 本地聊天工作台

打开 <http://127.0.0.1:3366>。本工具独立于 LifeAgent 应用，为本机 Agent Autoloop 提供中文聊天、需求派发、轮次状态、审批回答和项目进度查看。

QQ 手机接入：页面右上角“QQ 接入”可填写官方机器人凭据、连接并确认绑定本人；具体步骤见 [QQ-SETUP.md](QQ-SETUP.md)。WebSocket 与 Webhook 均已实现，真实接通需要平台账号权限和手机验证。

## 使用

- 在聊天框提出问题或开发需求，点击“发送消息”。消息交给后台 Codex，会使用已登录账号的额度。
- “需要你决定”区域可点选选项或填写具体回答；通知卡片点“已查看”结案。
- “继续开发”按项目既有进度启动下一轮；有任务执行中或有待确认问题时该按钮不可用。
- 刷新或关闭网页不影响后台任务；重新打开仍可看到消息。状态每 4 秒刷新。
- 对话采用同一 LifeAgent 会话续接；同组开发任务并发上限为 1。连续消息可能由中台合并处理，不保证每条消息对应独立一轮。
- 显示后台最终回复和真实轮次状态，不显示虚构百分比或模型内部推理；暂不支持逐字流式回复、多项目切换或附件。

## 启动与维护

需要 Node.js 24+ 和本机已安装运行的 Agent Autoloop，无 npm 运行时依赖。

```sh
cd /Users/cai/code/AI_agent_project/autoloop-chat
npm start
```

默认仅监听 `127.0.0.1:3366`。用 `AUTOLOOP_CHAT_PORT` 可修改端口。中台配置只由服务端读取 `~/.agent-autoloop/config.json`，不向浏览器传递中台密钥。消息历史位于忽略入库的 `.local/messages.json`（文件 0600、目录 0700）；不要把 `.local` 加入代码仓库。

已安装登录启动项时，本工具随当前用户登录启动，与 Codex 聊天窗口无关。服务标签：`local.agent-autoloop.chat`；日志位于 `.local/server.log`、`.local/server-error.log`。

停止或恢复本地聊天服务：

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/local.agent-autoloop.chat.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.agent-autoloop.chat.plist
```

仅停止聊天服务不会停止中台或已经接单的 Codex。要停止一个开发轮次，请点击页面任务上的“停止此任务”。

## 验证

`npm test` 使用临时中台验证 HTTP 接入、消息幂等、重启历史、卡片回答、CSRF 和请求来源检查，不使用真实模型额度、不回答真实业务卡片。真实接通还应从界面发送一个只读问题，确认最终回复出现。
