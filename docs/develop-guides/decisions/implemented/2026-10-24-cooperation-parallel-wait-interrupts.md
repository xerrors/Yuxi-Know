# 并行协作等待按中断 ID 保存与恢复

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/execution.py

## 问题

执行器允许模型在同一轮并行调用多个等待工具（如两个 `wait_inputs`），LangGraph 会产生多个 pending interrupt。原实现只提取并保存第一个中断（`task.interrupts[0]`），waitpoint 也不含中断 ID；恢复时以单值 `Command(resume=...)` 提交，LangGraph 直接报错 `When there are multiple pending interrupts, you must specify the interrupt id when resuming.`，整轮无法恢复。

## 决策

### 实现方案

中断提取直接读取当前 `StateSnapshot.tasks` 的全部未完成任务中断（`_extract_interrupts`），不再从状态 values 猜测备用中断。全为协作等待时聚合为单个 `cooperation_waiting` 载荷，新增 `waits` 列表为每个等待保留 `{interrupt_id, 目标, deadline}`（中断 ID 来自 LangGraph interrupt 对象，缺失时显式失败）；两个及以上等待只要不全为协作等待（包括混合协作与审批/回答，以及并行重复的审批或回答）就没有统一恢复入口，显式抛错而不是静默保存其一。协作 waitpoint 改为携带 `waits`。恢复扫描只将已经就绪或超时的条目组成 `{interrupt_id: result}` 映射，经 `create_resume_run` → 消息 metadata → `Command(resume={...})` 按 ID 精确送达。尚未就绪的中断留在 PostgreSQL checkpoint，后续执行段继续保存并等待；短等待不会因其他条目的长截止时间而延迟或丢失超时结果。审批/回答等待仍为单中断单值。面板投影（`checkpoint_state`）同步读取全部中断并复用同一聚合逻辑。

协作 middleware 在每个等待工具内部使用 LangGraph `task` 保存首次等待准备结果。无参数任务闭包捕获执行 runtime，checkpoint 只序列化等待请求；重放复用原目标、游标和 deadline，再调用 `interrupt` 消费已固定的回复。重新查询数据库不能覆盖已裁决的超时回复，也不能给其他未就绪条目延长截止时间。部分恢复后，LangGraph 同批任务仍可能保留已完成工具的旧中断；执行投影按实际工具结果排除这些条目，checkpoint 只读投影按同任务的业务写入排除它们。只有 `__resume__` 写入不证明任务完成，下一次人工中断仍保留。

当前协议只消费携带 `waits` 的等待点。用户明确授权移除旧 checkpoint 兼容：服务不回读 checkpoint 来修补缺失的调度字段，工具不从 namespace 推导中断 ID，也不通过额外参数重查旧等待。需要继续执行的等待必须由当前工具准备任务和中断协议产生。

PostgreSQL checkpoint 拥有实际未决中断集合；Turn.waitpoint 是该集合的调度投影，仅保存 `{interrupt_id, 目标, deadline}`。面板与执行事件只提供完整 `waits` 列表，不再额外复制第一项的目标和截止时间；第一项不能代表整批等待。

## 替代方案

- 在工具调度边界禁止同轮多个等待：可以消除多中断恢复，但限制了执行器已允许的并行协作调用，且需要在工具派发前统一裁决。
- 等全部中断就绪后统一恢复：减少执行段，但会推迟短等待；中间扫描发现的超时结果若未持久化，还可能被后来的完成结果覆盖。
- 在 waitpoint 中缓存每个已解决条目的结果，全部解决后恢复：增加第二份结果正文及其清理责任；checkpoint 已支持按 ID 部分恢复，复用现有执行段即可。

- 保留旧等待兼容：可以恢复升级前已挂起的工具，但需要额外 namespace ID 推导、服务回读和投影修补；用户明确选择移除，不再承担这份恢复承诺。

## 后果

`cooperation_waiting` 载荷只通过 `waits` 表达等待细节（前端与 public API 不消费该细节，仅透传展示）。不同等待先后就绪时可能产生多个恢复 Run，但仍属于同一 Turn，模型在工具批次完成后继续。不能聚合的并行等待（混合类型或并行重复的审批/回答）在当前版本使 Run 显式失败，不会发布只包含部分中断的可恢复待办。升级前缺少 `waits` 或准备任务缓存的旧等待不再提供恢复承诺；部署时需要结束这些旧等待。

## 验证

旧能力不存在：协作 service 不再回读 checkpoint 修补缺失的 waits，工具不再推导 namespace 中断 ID，服务接口不再接收兼容用的 interrupt_id；对应旧到新重放测试已删除。

重新引入条件：用户明确要求保留现存旧格式等待，并提供可验证的升级承诺；不得以预防未来变化为由恢复兼容分支。

- 单元测试：多协作等待聚合保留每个中断 ID 与目标；混合等待、重复人工等待与缺失中断 ID 显式失败；`_extract_interrupts` 从多任务 state 收集全部中断。
- 真实图生产 middleware 单元测试：重建图和 middleware 后，按 ID 恢复第一项保留已经固定的超时回复，第二项的原 deadline 不变；再次恢复交付各自结果。未固定准备结果的工具实现会因迟到数据库结果覆盖超时回复而失败。连续人工中断测试区分恢复写入与业务完成，防止过滤已完成任务时丢弃下一次人工等待。
- 真实 PostgreSQL 服务集成测试：双等待 waitpoint（inputs + sessions）全部就绪后恢复，resume 消息按中断 ID 携带各自结果；部分完成或短截止时间超时时，只恢复相应 ID，未就绪条目不会阻塞它。恢复原先“全部就绪才恢复”的实现，两项断言均因没有产生恢复 Run 而失败。
- 真实 LangGraph 与 PostgreSQL checkpoint 集成测试：执行器和只读面板收集相同的两个中断，反序构造的 ID 映射仍将独立结果交给正确节点；按 ID 部分恢复后另一等待仍可读取并最终恢复，完整结果从持久 checkpoint 回读。使用单值恢复的负向案例在真实图上因多个等待未指定中断 ID 而失败。
- 确定性 worker E2E：同一模型响应产生两个 `wait_inputs`，两个子任务由独立文件 gate 阻塞；数据库与公开状态确认两个中断 ID。分次释放后，未就绪条目保留原 ID 和 deadline，两个恢复 Run 分别消费一个 ID，各 Input 返回不同的精确结果。SSE 与最终 Run 对齐，Turn waitpoint 和 checkpoint 中断均清空，历史 Run 完成运行时清理。测试显式设置两个执行名额并在结束时恢复原配置。
