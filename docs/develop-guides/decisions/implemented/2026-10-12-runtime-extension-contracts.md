# 运行与扩展边界收敛

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/agents/runtime/context.py

## 问题

Context 的 Skill 与工具来源由跨模块动态属性组成，装配缺失时工具策略可放行未知来源。工具目录与供应商注册直接共享可变列表，Skill 的内容、权限、内置同步与安装职责混合。路径、摘要和沙盒环境读取又存在平行规则，使同一运行链路的授权与失败语义难以保持一致。

## 决策

### 实现方案

Context 声明非用户配置的运行字段，Skill 快照使用明确类型。工具装配记录本地、middleware 与 MCP 来源，模型及工具边界按完整注册与当前授权判断；未知来源或缺失必要装配拒绝执行。tools/runtime 拥有依赖工具注册，Skill 运行解析消费已授权数据，消除反向注册依赖。registry 拥有注册，catalog 从当前注册派生独立读结果，外部读取不能修改注册容器。正式注册对象仍用于执行。H1/H2 的输入准备、实际请求和返回身份复查时序保持有效。

runtime 和 UserWorkspace 分别拥有路径规则，产物发布与读取消费同一 runtime 校验，文件工具身份只读执行者注入的 Context。Workdir 转发为操作附加已绑定根；Workspace 与 provisioner 保留路径和返回类型差异，没有共同多态消费者，因此不新增文件协议抽象。条目共同字段和目录优先排序由 workspace service 提供，缺失目录、冲突、上传回滚和预览错误保留各自用例策略。目录 fd 原语保留 ELOOP，普通文件和远端 wire 转换权限异常。当前契约见[沙盒机制](../../../mechanisms/sandbox.md)。

摘要正式消费者使用异步 graph 和主动维护入口，共用实际摘要请求与授权。同步入口明确拒绝；基于 asyncio.run 的桥接无法跨临时事件循环复用全局 PostgreSQL 池，不引入线程/持久循环机制。原同步工作流测试迁移至正式异步入口，保留历史、事件、消息视图和失败断言。同步沙盒环境查询归 AgentEnvRepository，连接串驱动转换归 PostgreSQL 基础设施，查询值不变。

Skill 将权限/依赖与带锁读取、内容发布、内置同步、共享用例分开，消除 shared/content 环。生产调用者直接依赖 access 或 builtin/sync；shared 的现有扩展/测试显式导出保留。安装暂存使用 install_draft 命名。个人创建型发布复用现有无覆盖目录原语，空目录竞态也保留并发目标；内置覆盖备份、不可变包数据库引用与投影撤权发布保留各自回滚语义。内置与包 content_hash 使用同一目录算法，包含可执行位；当前内置索引由启动同步刷新，历史包引用不变。

ResolvedSkill 的来源方式、可见范围、真实目录及两张卡片覆盖标记有不同消费者，保留公开字段。包、单文件与根说明修订按各接口比较对象保留。远程安装和草稿已共用 download_remote_skills，双下载管线结论不成立。投影按 uid 锁定完整授权集合及失败撤销补偿保持；依据见[Skills 管理](../../../agents/skills-management.md#运行时文件行为)。get_common_kb_tools 继续服务[正式 Python 工具扩展](../../../agents/tools-system.md#知识库工具)。

## 替代方案

只声明属性而保留空集合放行不能闭合工具边界；把框架工具当作未知工具统一拒绝会破坏合法文件和协作能力。全局权限缓存、新注册框架和没有共同消费者的统一文件协议扩大维护范围，因此使用现有 Context、registry 与 owning filesystem。同步摘要桥接需要额外循环生命周期，当前正式消费者均使用异步执行；明确拒绝能使失败发生在 I/O 之前。不同安装来源保留创建、不可变包引用、覆盖恢复和撤权发布，统一整条回滚流程会改变已有数据承诺。

## 后果

Context 派生值不进入可配置 schema、接收快照或 manifest。缺失来源装配的替代图和同步摘要调用明确失败，合法 middleware 工具及动态 Skill MCP 继续可用；正式扩展需遵循装配入口。当前 scope 不再从模型 state 或 configurable 推断。目录读取返回独立容器，动态注册立即可见。公开 Skill 字段、文件修订和数据 schema 保持有效，内置 content_hash 的当前值统一算法。

## 验证

完整后端 non-slow unit、真实 PG/HTTP integration、正式 worker 与 Docker 沙盒 E2E 验证工具、授权、Skill 字节与 Run/checkpoint 归属。个人 Skill E2E 使用本地确定性 HTTP 模型回放，只有真实 read_file 的 ToolMessage 含文件标记才返回该标记，数据库 Run 清单与宿主文件回读作为结果 oracle。缺失/替换/删除环境配置和无效存储在三种连接 URL 下由同步 provider 与独立异步 session 对照。

在隔离源码副本分别恢复未知工具放行、runtime 跳转放行、空绑定放行、注册表活引用、空目录覆盖与配置身份回退，六组测试均在目标业务断言上失败；恢复修复后 22 项通过。摘要失败/撤权、缺装配与 MCP 禁用还由相关 unit、PG 与 worker 场景验证。工程契约、其 64 项 unit、变更 Python Ruff、相对链接与文档 build、补丁检查随最终候选执行。具体数量和未验证范围由[审计报告](../../audits/modules-structure-audit-2026-10-11.md)记录。

真实外部远程 Skill 源的网络故障恢复、Kubernetes backend 和生产部署没有运行；这些范围未新增部署承诺。unit 的 skip 不记为通过。
