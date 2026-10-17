# 当前项目文档的职责与阅读路径

状态：implemented
类型：process
Owner：docs/develop-guides/documentation-guidelines.md

## 问题

当前指南混有旧运行模型、已完成计划和互相冲突的能力说明。部分入口重复专题细节，用户难以快速判断项目能做什么、如何启动及应查看哪份参考。

## 决策

### 实现方案

根 README、中英文介绍与入门页表达项目定位、当前能力及最短操作路径；advanced 拥有配置、部署和外部接口；agents 与 mechanisms 分别拥有使用方法和内部边界。事实按源码、Compose、Schema 和当前测试核对，跨页保留必要摘要及相对链接。完整供应商模板与字段清单由源码和 OpenAPI 维护，教程保留执行任务所需的真实示例。

已完成的 Agents API 对齐计划保留原 URL，内容收敛为维护索引；原计划独有的历史交付证据保存为归档记录，相关当前决策分别指向契约 Owner 和历史证据。日期审计、版本记录、事故与原有冻结 archived 保留历史语义。容量页区分当前 Cube 用户 VM 与旧 Docker 实测，当前部署预算不引用旧容器内存数值。

## 替代方案

逐页只缩短文字不能解决事实冲突；重建整套目录会引入大量链接迁移。保留既有目录，在真实职责内修正事实、合并重复说明并补齐索引。

## 后果

入口以任务组织，重复能力介绍与过时完整清单减少。接收与消费时序、回执归属、初始化、协作、Skill 动态刷新、附件、CLI、网络工具及连接器的当前说明指向真实 Owner。历史验收数量保留原日期与适用范围，当前质量由实际执行的检查与结果证明。

## 验证

- Inspected：根与包入口、当前教程、advanced、agents、mechanisms 和开发指南分区核对源码；相关决策检查 Owner 路径与当前 Schema/初始化交叉引用。未发现冲突的页面保持原文。
- Passed：全仓相对文件链接目标检查、`python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`、`docs` 目录下 `pnpm run build` 和 `git diff --check`。
- 独立语义审阅检查完整需求、文档 diff、源码与验证范围，发现的 API 入门回执空值表述已修正。
- 本轮文档整理未重新执行产品端到端链路、真实供应商探针或容量测试；构建成功不作为这些行为的通过证据。
