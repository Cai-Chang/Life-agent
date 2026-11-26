# ADR 0004：个人日程、待办与事务一致性

日期：2026-11-26；范围：DEV-03 手动业务闭环。

- 复用既有 Cookie/CSRF 与 owned_workspace 成员/所有者校验，身份与 workspace_id 由会话推导，写入 body 不接收任意用户身份。
- calendar_events、tasks、operation_records 在 0003 显式迁移中创建；审计增加 target_id，只有动作、用户、空间、记录 ID 等元数据进入审计，不记录正文。
- 每个个人空间写入先锁定 Workspace 行；同一事务重新读取实体，检查版本/冲突，写入实体、操作结果和审计，再提交。当前 API 的所有日程/待办写入口共用这条路径，不依赖进程内锁。
- 同一用户有效日程满足 start < other.end 且 end > other.start 即冲突，端点相邻允许。日程取消为软取消，恢复/改时间须重检；不级联删除待办。
- 待办 pending/in_progress 可以完成或取消；done/cancelled 需先 pending 重新打开，才能再次进入其他状态。删除待办为确认后的硬删除；成功删除仍保留幂等响应与审计目标 ID。
- 新写接口要求 Idempotency-Key；键在个人空间内唯一，method/path/规范化 body 一起计算请求哈希。相同键与参数返回原结果，不重做写入/审计；参数不同返回409。操作记录当前保留至空间删除，后续需制定有安全重放窗口的清理策略。
- 更新/删除必须提交 version；旧版本返回409，避免静默覆盖。前端网络失败保留同页面相同请求的操作键，用户重试不会重复创建；刷新页面后的重新创建属于新的请求，不把内存重试机制当作跨页面恢复队列。
- 时间使用带偏移的输入和 PostgreSQL timestamptz，返回 UTC。前端按个人时区转换，不依赖手机/电脑系统时区；重复夏令时显式选择，不存在的时间拒绝。
- 周/月日期选择存入 URL，刷新仍保留。数据列表支持分页，界面读取后续页。首页统计来自真实业务数据。
- 此阶段没有 Agent 代写或后台提醒，手动表单提交为用户操作授权。后续 Agent 写入还须在同一业务服务外完成计划审批，不得绕过校验。

参考：需求第2.3、8、9章；SQLAlchemy ORM 查询与事务锁：https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html ；Pydantic aware datetime：https://docs.pydantic.dev/latest/api/standard_library_types/#datetimes 。
