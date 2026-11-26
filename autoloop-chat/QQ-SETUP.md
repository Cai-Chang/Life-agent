# QQ 官方机器人接入

本适配在现有本地工作台进程内运行，复用已有本机来源与开发队列；不修改 Agent Autoloop 内核，不需要新增中台密钥。仅接受本机确认绑定的一个 QQ 用户的单聊文本，暂不处理群聊、语音或附件。QQ 消息中的开发需求也会出现在本机网页聊天历史中。

## 创建与配置

1. 打开 https://q.qq.com/ 创建官方机器人，取得 AppID 与 AppSecret。开通单聊，并按控制台要求配置测试账号/使用范围和消息事件。
2. 打开本机 http://127.0.0.1:3366/?settings=qq ，在“QQ 接入”填写 AppID、AppSecret，选择控制台实际支持的事件接收方式，保存。
3. WebSocket 方式由这台 Mac 主动连接官方网关，不需要给 Mac 开放公网监听端口。订阅 `GROUP_AND_C2C_EVENT (1 << 25)`，只处理 `C2C_MESSAGE_CREATE`。若平台明确拒绝长连接权限，改用 Webhook，不能假定所有机器人账号拥有相同接入方式。
4. Webhook 方式会在本机启动 `127.0.0.1:3367`，只接受 `POST /qq/webhook`。需要由你控制的 HTTPS 反向代理或隧道转发这一条回调路由，将公网 HTTPS URL 填入控制台并订阅 `C2C_MESSAGE_CREATE`。QQ 支持的公网端口为 80、443、8080、8443；不要直接暴露 3366 的本机管理页或 3350 的中台接口。本项目不会自动申请域名、开公网入口或安装隧道。
5. 如果控制台要求 IP 白名单，加入实际运行这台 Mac 的公网出口 IP；网络代理或动态 IP 会影响该地址，按当前平台返回提示处理。
6. 用手机 QQ 扫控制台提供的二维码添加机器人，向它发送本机“QQ 接入”区域显示的 `绑定 八位口令`。回到本机页面，确认出现的账号是本人，再点击“确认这是我的账号”。口令匹配前、或未确认绑定的消息不会派发任务。
7. 手机向机器人发送 `帮助`、`进度`，再发送 `这是接通测试，只回复 QQ 已接通，不修改文件`，检查即时查询、后台派发和结果推送。需要真实机器人凭据和手机配合才能完成此步骤；模拟测试通过不代表真实接通。

AppSecret 仅保存到 `.local/qq-config.json`，不回显、不提交代码仓库。状态 API 只返回是否保存密钥，不返回密钥本身。停用后保留配置便于恢复；“解除绑定并停用”移除允许的用户。

## 手机指令

| 消息 | 行为 |
| --- | --- |
| `帮助` | 查看指令 |
| `进度` / `状态` | 查看当前项目轮次及待确认卡片，不调用模型 |
| `任务` / `项目进度` | 读取项目进度文件，不调用模型 |
| `回答 2 1` | 卡片 2 选择第 1 项 |
| `回答 2 先完成测试` | 卡片 2 的自定义回答 |
| `已查看 3` | 确认通知 3 |
| `停止 8` | 停止第 8 轮，保留已落盘改动 |
| `继续开发` | 无待确认卡片时，向同一队列派发继续开发需求 |
| 其他文本 | 作为 LifeAgent 项目需求交给后台 Codex，使用模型额度 |

任务结果及待处理卡片会主动推送到已绑定单聊。QQ 主动消息受账号权限、用户的主动消息开关与平台频控限制；无法推送时本机 QQ 状态会显示错误，消息和结果仍留在中台/本机页面，也可主动发 `进度` 查询。超长内容会截断并提示在本机查看全文。

## 本地验证与限制

`npm test` 包含 QQ 官方签名测试向量、签名篡改和过期、长连接认证帧、用户绑定、陌生人隔离、重复消息去重、指令转发、结果推送和 Webhook 接收测试。测试使用临时凭据与模拟 QQ 网关，不向真实 QQ 发送消息。

回调业务消息必须验证 Ed25519 签名、AppID 和时间戳；平台初始 `op:13` 验证挑战可以未签名，但只能生成挑战证明，不能派发任务。Webhook 接收后先持久化待处理消息，再 ACK，进程重启会处理保存的消息。需求使用稳定事件编号去重；QQ 主动推送本身在网络结果不明时可能重复通知，不宣称恰好送达一次。

## 官方资料

- [启动接入与 AppID/AppSecret](https://bot.q.qq.com/wiki/develop/api-v2/)
- [获取访问凭证](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/access-token.html)
- [WebSocket 接入](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/websocket.html)
- [Webhook 接入](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/webhook.html)
- [签名校验](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/sign.html)
- [单聊消息事件](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/c2c_message_create.html)
- [发送单聊消息](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_messages.post.html)
