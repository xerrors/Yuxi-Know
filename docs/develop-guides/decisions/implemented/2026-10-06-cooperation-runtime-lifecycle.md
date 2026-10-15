# 协作树的维护沙盒与空闲收敛

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/agents/services/leases.py

## 问题

主动上下文压缩没有 Run lease；复用会话沙盒后直接释放，会破坏其他协作成员仍在使用的临时文件和进程。子会话压缩的 context 与 provisioner 使用不同 scope，也会创建无关沙盒并清理错误对象。

树内最后一个执行者结束时，pending Run 阻止空闲计时；这些 pending Run 随后被取消时，没有执行清理负责补齐计时。继续整树与删除项目或 Agent 使用不同的批量 Session 锁顺序，还存在反向等待。

嵌入的成员标签由 `v-show` 隐藏，KeepAlive 激活状态不能证明用户正在查看该成员。仅按 KeepAlive 状态处理完成事件，会提前消除未读状态。

## 决策

维护沙盒 UUID scope 与协作树空闲回收部分由[工作区路径清理](./2026-10-15-workspace-path-cleanup.md)取代；用户 VM 生命周期由[Cube 用户环境](./2026-10-15-sandbox-environment.md)拥有。本记录继续拥有成员可见性与批量 Session 锁序决定。

主动压缩只使用已授权 Project Workdir 和原 Session checkpoint，不拥有独立环境或回收状态。继续整树按 `thread_id` 顺序锁定成员，与批量删除保持一致。

成员工作区接收父级实际可见性，并与 KeepAlive 激活状态共同约束已读和滚动。隐藏成员继续接收运行事件，重新显示时恢复观察并标记已读。

### 实现方案

`compression` 拥有 checkpoint 压缩，用户环境 provider 拥有空闲休眠，`cooperation` 遵循既有 Session 锁顺序。`SessionWorkspace` 把侧栏打开状态、选中标签与父工作区状态传递给嵌入成员。生产入口和测试删除无 consumer 的旧 subagent 附件传递、来源过滤、后代取消返回值、旧 replay 分支及测试选择器；旧接口拒绝测试、外部协议 fixture 和历史记录继续保留其必要名称。

## 替代方案

- 压缩全程持有树锁：会阻塞持有 Run 行锁的终态通知，进而阻塞 heartbeat，长压缩可能造成租约过期。
- 新增可续租的维护执行类型：需要增加持久状态与恢复机制；现有一次性压缩生命周期已能隔离副作用。
- 仅在取消入口设置空闲时间：增加多个状态转换入口的回收责任，恢复扫描仍可能漏掉其他未执行的终态路径。

## 后果

主动压缩访问持久 Workdir，不改变同用户 VM 的身份、临时文件与进程。用户空闲休眠由 provider 根据所有 Run 和命令占用判定。

## 验证

维护 scope、`idle_since` 与回收标记的历史验证只证明已被取代的实现。当前证据由工作区路径清理决定拥有；根与成员压缩后同用户 VM 及临时文件保持，成员实际可见性与 Session 锁序继续由对应回归覆盖。

具体入口为 `test_context_compression_service.py`、`test_session_cooperation.py`、`test_session_cooperation_e2e.py` 与 `sessionWorkspaceVisibility.test.js`。实际运行结果及环境限制随交付报告记录；模型提供方初始化权限不足时，E2E 记为未完成验证。批量 Session 锁序由独立 Reviewer 对照继续与删除的真实查询复核。
