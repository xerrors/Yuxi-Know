---
title: refactor: remove auto attachment conversion and persist uploads in state
type: refactor
date: 2026-03-05
---

# refactor: remove auto attachment conversion and persist uploads in state

## Overview

将聊天附件链路从“上传即转换为 markdown 并写入 state.files”重构为“上传即保存原文件并写入 state.uploads 元数据”。目标是把附件处理从预处理模式改为按需读取模式，避免在 agent 未使用文件前做不必要转换，并统一线程目录下的原始文件作为唯一事实来源。

## Problem Statement / Motivation

当前实现在上传阶段存在较强耦合：
- 上传流程在 `src/services/conversation_service.py` 同时做文件保存、可选 markdown 转换、状态同步。
- state 写入依赖 `attachment.markdown -> files[path].content`（`conversation_service.py`、`chat_stream_service.py` 的 `_build_state_files`）。
- 中间件提示词依赖 `attachments` 列表，但 UI 和状态还混用了 `virtual_path/original_virtual_path/file_path/markdown/truncated` 等字段。

这导致：
- 上传阶段成本高（转换前置）。
- 状态语义混乱（`attachments` 既是展示元数据又承载转换结果）。
- 后续扩展“按需解析/按类型处理”时改动面过大。

## Proposed Solution

采用“上传原文件优先”的单一路径：

1. 上传阶段不再触发自动 markdown 转换（移除 `doc_converter` 依赖链路）。
2. 原文件统一保存到线程目录 `.../user-data/uploads`，并同步到 sandbox 同路径。
3. LangGraph state 新增并使用 `uploads` 作为附件事实来源（每个条目包含文件标识、路径、大小、类型、时间等必要元数据）。
4. `attachments` 退出状态主链路，`uploads` 成为唯一状态来源。
5. agent 读取文件内容统一通过现有文件工具（如 `read_file`）在需要时访问 `uploads` 中声明的路径。

## Key Decisions (Locked)

- 不采用双写：不同时维护 `attachments` 与 `uploads` 两套状态事实来源。
- 单次切换：本次重构同时更新后端与前端读取路径，直接切到 `uploads`。
- 不维护 `state.files` 镜像：停止由附件内容派生 `files`，避免冗余状态与同步复杂度。

## Technical Considerations

- 需要统一以下使用点的数据语义：
  - `src/services/conversation_service.py`：上传、删除、state 同步。
  - `src/services/chat_stream_service.py`：`get_agent_state_view` 的回填逻辑。
  - `src/agents/common/middlewares/attachment_middleware.py`：提示词来源从 `attachments` 迁移/对齐到 `uploads`。
  - `web/src/components/AgentChatComponent.vue` 与附件组件：字段从 `original_virtual_path/file_path` 对齐到单一上传路径。
- 兼容策略：不做运行时兼容层，不做双写；接口与前端在同一版本内完成同步切换。

## Acceptance Criteria

- [ ] 上传任意受支持大小文件后，不再触发自动 markdown 转换。
- [ ] 原文件可在线程 `uploads` 目录中稳定落盘并可下载。
- [ ] state 中存在 `uploads`，且能完整表达当前线程附件集合。
- [ ] agent 在无预转换 markdown 的前提下，仍可基于上传文件路径正常执行读取流程。
- [ ] 删除附件后，state.uploads 与线程目录保持一致。
- [ ] 前端附件列表与提及能力在新数据结构下行为一致（无回归）。

## Success Metrics

- 上传接口平均耗时下降（相对当前版本）。
- 上传失败率不高于当前基线。
- 相关会话流程无新增 P1 回归（上传、查看、下载、删除、提及）。

## Dependencies & Risks

- 风险：前端仍依赖旧字段（`markdown/truncated/original_virtual_path`）导致展示回归。
- 风险：`get_agent_state_view` 仍按旧逻辑回填 `files`，可能与 `uploads` 语义冲突。
- 风险：历史会话中仅存在旧 `attachments` 结构的数据，在切换后可能不再自动注入到模型上下文。

## SpecFlow Gaps / Edge Cases

- 同名文件覆盖策略（覆盖、重命名、拒绝）需明确。
- 无扩展名文件与非常规 MIME 文件在 UI 展示规则需明确。
- 历史会话首次读取时是否做一次性状态归一化需明确。

## References & Research

- `src/services/conversation_service.py`
- `src/services/chat_stream_service.py`
- `src/agents/common/middlewares/attachment_middleware.py`
- `src/repositories/conversation_repository.py`
- `server/routers/chat_router.py`
- `web/src/components/AgentChatComponent.vue`

## Scope Boundaries

- 本次不包含上传后自动解析（markdown/OCR）链路；若需要解析，后续按“显式触发”另开能力。
- 本次不引入运行时兼容分支（如旧字段回填、双状态同步）。
- 历史数据迁移若需要，采用一次性离线迁移，不在在线请求链路增加复杂度。
