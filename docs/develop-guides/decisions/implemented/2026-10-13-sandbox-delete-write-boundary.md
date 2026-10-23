# Sandbox delete/adelete 收进写根边界

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/agents/backends/sandbox/backend.py

## 问题

`ProvisionerSandboxBackend` 未覆盖 `delete`，解析到上游 `BaseSandbox.delete`——无边界校验的 shell `rm -rf`，其文档自述"NOT a security boundary"；`adelete` 由 `BackendProtocol` 默认 `to_thread(self.delete)` 转发到同一实现。真实 provisioner sandbox 实测（2026-10-13）：`delete("/home/gem/skills/...")` 与 `adelete("/etc/yuxi_probe_marker")` 均返回成功且文件实际消失。DeepAgents filesystem middleware 暴露 `delete` 工具名（`FsToolName` 含 delete，且 middleware 内部会调 `backend.adelete`），当前仅因 `_AGENT_FS_TOOLS` allowlist 排除而未到模型手中；模型侧排除不是授权边界，任何直接调用或未来把工具加回 allowlist 都会得到越界删除能力。

## 决策

`ProvisionerSandboxBackend.delete` 覆盖为与 `write`/`edit` 同一口径：路径规范化失败返回 `Error: Invalid path ...`，不在写根（`_can_write_path`，即 UserWorkspace）内返回 `Error: permission denied for write on '<path>'`，`/home/gem/user-data` 本身返回 `Error: deleting the user data root is not allowed`；三项检查通过后才交给 `super().delete`（保留其存在性探测与 rm 语义）。`adelete` 由 BackendProtocol 默认 `to_thread(self.delete)` 转发到本方法，不单独覆盖。`_AGENT_FS_TOOLS` 继续排除 delete，工具开放仍需要单独的审批与审计设计。

## 替代方案

- 只靠 `_AGENT_FS_TOOLS` 排除 delete 工具：拒绝。前端/prompt/schema 省略不是授权边界；executor 必须 fail-closed，且 middleware 内部路径与未来调用方都直接落在 backend 上。
- 自己实现原生删除脚本而不走 `super().delete`：拒绝。上游实现已有存在性探测与 `rm` 语义，边界是本类缺失的部分，不重复造删除。

## 后果

- 越界 delete/adelete 从"静默成功删除"变为稳定 permission denied 错误串，无沙箱副作用。
- delete 能力仍然不对模型暴露；未来若开放，删除审批/审计设计仍需单独变更，本记录只闭合执行边界。
- 用户数据根作为整体删除对象被拒绝；根内 Project Workdir 与输出目录树仍由 `BaseSandbox.delete` 的递归语义删除，与写根权限一致。`delete_authorized_path` 对宿主侧授权文件删除另有独立根检查。

## 验证

| 验收主张 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|
| 根外 delete/adelete 不产生副作用即失败 | ProvisionerSandboxBackend.delete | integration `test_async_delete_stays_inside_write_roots_on_real_sandbox`：`/home/gem/scratch_delete` 根外文件被拒且 `test -e` 仍在；unit `delete_denies_outside_write_roots_before_shell`、`adelete_forwards_to_bounded_delete`（BaseSandbox.delete stub 为 `pytest.fail`） | 临时把边界条件置为放行后，集成用例失败于 `adelete` 返回 error=None 且文件被真删；恢复后同用例通过（原分支实测） | Passed |
| 修复前根外可删（缺陷存在性） | 上游 BaseSandbox.delete | 2026-10-13 真实 sandbox 探针：`delete(skills 文件)`、`adelete(/etc marker)` 均返回成功且删除后现场为空 | — | 已复现（决策依据） |
| 根内删除语义不回归 | delete→super().delete | integration 同用例：Workdir 内 `awrite` 后 `adelete` 成功且 `als` 为空；unit `delete_delegates_within_write_roots` 断言归一化路径恰好转发一次 | — | Passed |
| 非法路径显式失败 | _normalize_path | unit `delete_reports_invalid_path` | 上游实现会把相对路径直接拼进 rm 命令 | Passed |
| 用户数据根整体删除被拒绝 | delete | unit `delete_denies_user_data_root_before_shell`（BaseSandbox.delete stub 为 `pytest.fail`） | 去掉根检查后 `super().delete('/home/gem/user-data')` 到达上游实现，测试失败（原分支实测） | Passed |
| 全量回归 | test/unit、test/integration/services | 移植后全量 `test/unit` 2480 passed / 60 skipped；`test/integration/services/test_sandbox_async_file_tools.py` 4 passed（真实 provisioner）；`ruff check`/`ruff format --check` 干净 | — | Passed |

未验证范围：`delete` 工具对模型正式开放后的审批/审计链路（本变更不开放该工具）。
