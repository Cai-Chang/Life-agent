# ADR-03：浏览器认证与个人空间

日期：2026-11-26。适用阶段：DEV-02。需求对应：FR-01、个人空间数据隔离及基础审计。

## 决定

- React + TypeScript SPA 经 Vite（开发）或 Nginx（容器）同源代理访问 FastAPI，不给浏览器配置跨域凭据访问。
- 密码使用 Argon2id。会话为随机 256 位不透明 token，服务端只存 SHA-256 摘要、用户、CSRF nonce 与到期时间；浏览器通过 HttpOnly、SameSite=Lax、Path=/ Cookie 携带 token，不放 localStorage。有效期七天；退出撤销当前会话，重新登录轮换当前浏览器会话。
- 生产模式要求 HTTPS APP_ORIGIN 并设置 Secure Cookie；本机 HTTP 开发使用独立的开发模式。注册/登录也检查 Origin、Fetch Metadata 与 JSON 类型，避免登录 CSRF；已登录写操作另外验证会话绑定的 CSRF nonce。
- 注册在同一数据库事务中创建用户、个人空间、所有者成员关系、会话和审计记录。邮箱归一化为小写并受唯一约束保护，个人空间 owner_id 唯一。并发注册不能生成重复空间。
- 读取或修改空间时同时检查当前会话身份、成员关系与 owner_id；无权访问返回 404。用户身份、角色和空间归属不接受请求体赋值。
- 昵称、IANA 时区和空间名称可修改；时区数据库作为显式依赖锁定。审计只写动作和标识，不记录密码、会话 token、资料正文或连接串。
- 模型/API 密钥仍为后续服务端配置；本次注册登录不调用模型，不涉及 Autoloop。

## 当前边界

仅实现个人空间，不开放家庭邀请或角色分配。限流是每个 API 进程内的基本节流，不是多副本共享限流。本次未实现邮箱验证、密码找回、账号删除和所有设备会话管理；这些不能冒充已验收功能。

## 验证

真实 PostgreSQL 测试覆盖注册原子性、并发重复注册、密码哈希、会话轮换/撤销/过期、Cookie 属性、Origin/CSRF、请求脱敏及跨账号读写；Playwright 覆盖桌面和手机注册、资料持久化、退出重登录及会话丢失的 UI 行为。

参考：[FastAPI 密码哈希](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)（采用其中 Argon2 原则，本项目不使用 JWT）、[OWASP CSRF 防护](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。
