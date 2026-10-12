# 运行读取与事务边界的局部简化

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/checkpoint_messages.py

## 问题

运行快照已经声明类型，但消费者仍按任意字典重复兜底；沙盒环境与路径迁移留下透明转发。普通 Skill 权限读取因顶层导入而牵入 MCP 运行链。模型前事务提交隐藏在可选追踪 helper 中，checkpoint 服务通过 SessionRepository 传递整个事务，终态服务又重复查询调用方已经锁定的 Thread/Turn 和 steer 就绪状态。

## 决策

### 实现方案

按当前类型直接读取完整 Skill 快照，在各消费入口明确区分尚未准备的 None；保留授权缺装配拒绝与有效/激活 Skill 交集。删除无消费者的环境规整及仅转发的环境/路径包装，消费者直接使用 owning repository 或路径边界。MCP service 仅在实际校验依赖时加载。

模型执行主流程准备追踪记录后拥有唯一提交点，关闭追踪也在同一位置结束读取事务。追踪 helper 只准备写入；主流程提交失败或取消时回滚并关闭 observation，再进入既有失败/取消收敛。

checkpoint 用例直接接收 AsyncSession，并在局部复用仓储。终态结算消费同一事务中已经锁定的 Session/Turn 和已经裁决的 steer；就绪查询由共同的 lock_ready_steer 拥有，取消/失联仍保留取得 Input 行锁的既有位置。保留 Session→Turn→Input→Run 锁序、current Run 与 lease guards、消息对账、事务内接管和提交后投递/发布，不添加状态机或仓储装配容器。

本决定局部取代[事务与生命周期决定](2026-10-12-agent-transaction-lifecycle.md)中追踪准备的事务归属及终态重复读取策略，其他幂等、消息和治理契约继续由原决定及对应源码拥有。

## 替代方案

重新合并权限/内容/同步、Message/Memory 或协作命令/通知会恢复原职责混合。通用 snapshot accessor、事务回调和 repository bundle 增加间接层，本轮直接表达已有事实与参数。全部终态入口重新查询保证不了比调用方锁更强的隔离，反而重复裁决；明确已锁对象的契约仍由持久守卫和独立负向场景证明。

## 后果

原快照是同进程准备后的完整契约，普通消费者直接读取字段；授权执行边界对替代 Context 的缺失字段继续拒绝。预加载正文由 owning reader 完整构造。已有的文件错误翻译、Input 批次锁、当前 Run 与 lease 守卫、失败输出及消息审计继续拥有各自职责。模型前提交在主入口可见，终态裁决仅复用同一事务的锁定事实。

## 验证

完整 non-slow unit 2713 passed / 60 skipped；新增六项准备、提交失败与取消用独立图输入、未提交事务内容及实际 observation 结束状态证明清理。真实 PG 113 项覆盖竞争、锁等待、附件就绪、FIFO、steer、撤权、恢复与环境同步读取。相关真实 HTTP/PG 23 项及 worker/SSE、Docker 沙盒 E2E 34 项通过，协作 7 项串行复验通过，具体结果由[审计报告](../../audits/modules-structure-audit-2026-10-11.md)记录。生产行为由源码与持久事实拥有，报告只是结果索引。

旧能力不存在：删除环境与路径透明包装、快照消费者的字典兜底、追踪 helper 的提交和终态服务的重复读取；符号搜索与完整 diff 核对。

重新引入条件：出现当前类型无法表达的合法协议版本或新的独立事务消费者时，由真实 Owner 定义新的边界并以负向案例证明需求，不为猜测中的调用方恢复包装。

生产部署、真实外部模型与 Kubernetes 未运行。隔离测试使用本地 HTTP replay；宿主 Docker 被多个任务共用，ignored 测试 provisioner 的 inventory 仅枚举本环境 prefix，业务执行与持久 oracle 保持候选源码。完整 unit、相关 PG/HTTP/E2E、工程契约、Ruff、链接/build 和独立 Review 随最终候选执行；skip 不计通过。

## 边界

减少重复查询不能省略持久锁或将已裁决 steer 跨事务复用。仅迁移生产接口接线，原测试业务 oracle 保留；真实外部模型和生产部署不作为本轮新增承诺。身份阶段 Step 7 保持待处理。
