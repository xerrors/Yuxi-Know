# 沙盒审查修复：搜索预算、传输错误与清理收敛

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/agents/runtime/sandbox/cube.py

## 问题

代码审查发现三个行为缺陷：本地 Workspace 的 grep 逐文件完整读入最多 100MB 且无单文件上限，与 VM Guest 脚本跳过超过 10MB 文件的既有语义不一致；`upload_files`/`download_files` 把大小、路径校验等失败统一折叠成 `permission_denied`；Cube 取消脚本在异常路径（用户取消、超时、断流清理、残留句柄回收）创建的 `/tmp/.yuxi-cancel-<execution_id>` tombstone 只在取得真实 end 时移除，长期存活的用户 VM 上无限累积。同一审查发现 `_cleanup_command` 遇到代次不匹配的残留句柄时选择 raise，一旦可达会让该句柄永久阻塞用户 VM 休眠并让维护循环反复失败。

## 决策

本地 grep 与 Guest 脚本共用模块常量 `_SEARCH_MAX_FILE_BYTES`（10MB），经 `SEARCH_MAX_FILE_BYTES` 环境变量传入脚本，两条路径对超过预算的文件一致跳过。传输错误按类型回传：路径与大小校验的 ValueError 返回原始受控消息，缺失返回 `file_not_found`，其余保持 `permission_denied`。

取消脚本在能证明 wrapper 已启动的三种证据下——登记的 pgid 来自 start 事件、扫描到带执行标识的进程、取得真实 end——且进程组确认终止后移除 tombstone；无法证明启动时保留 tombstone 继续拦截可能迟到的 wrapper。启动证明成立后同一次执行不存在第二次启动，删除不影响竞态保护。

`_cleanup_command` 在环境行缺失或代次不匹配时移除句柄而不发送取消：重建先销毁旧 VM 再递增代次，旧句柄的 uuid 标识不可能命中新环境，"不作用于新 VM"的安全语义由不发送取消保持。

同一审查的两处对齐顺带修正：`_guest_io` 与 `_guest_search` 的内嵌脚本提取为模块常量并接受编译断言（脚本编辑引入的语法缺陷曾在测试盲区让 VM Home 文件工具整体失效）；grep 的单文件路径回退改为经 `stat_authorized_path` 取大小后按同一预算跳过；VM 侧 `ls` 结果补 `modified_at`，与本地路由的 FileInfo 形状一致。

本变更为小而完整的缺陷修复集，同一变更内生效，无待裁决的替代设计，因此未走 proposal 流程；取舍理由与负向验证在本文记录。

## 替代方案

- tombstone 引入 TTL 或由 maintain 周期清理：需要新增扫描面与时钟判断，不如按启动证据在终止确认处就地移除。
- 传输错误继续统一 `permission_denied`：模型与用户无法区分可重试与不可重试原因。
- 残留句柄保留 raise：该防御分支当前不可达（rebuild 被活跃命令阻塞、环境行无删除路径），但一旦可达即永久卡死，收敛优于卡死。

## 后果

grep 对超过 10MB 的本地文件不再返回匹配，与 VM 搜索一致。`upload_files`/`download_files` 的 error 字段开始出现受控校验消息，消费方按字符串展示，不受影响。异常路径取消的 tombstone 在大部分场景被回收；流在 start 事件前断开且取消到达时命令已结束的窄窗口仍保留 tombstone，这是启动不可证明时的刻意取舍。`_cleanup_command` 对旧代次句柄从显式失败变为收敛移除。

## 验证

- `test_embedded_guest_scripts_compile`：对两段 Guest 脚本常量做编译断言，恢复缩进缺陷时在编译层失败。
- `test_search_skips_files_over_per_file_budget`（guest/workspace 双路径，阈值收敛到 16 字节）：恢复无上限实现时两条路径均在正确原因上失败。
- `test_transfer_errors_report_actual_cause`：恢复统一折叠时在路径校验用例失败。
- `test_cancel_script_removes_tombstone_after_confirmed_group_stop`、`_for_recorded_group_that_already_ended`、`_on_confirmed_terminal`：以真实子进程执行取消脚本，恢复仅 TERMINAL 删除时前两项失败；`_keeps_tombstone_when_start_cannot_be_confirmed` 保护无法证明启动时的保留语义。
- `test_stale_generation_command_handle_is_removed_without_touching_new_environment`：恢复 raise 时失败，并断言不向新环境发送取消。
- 集成 `test_abandoned_lifecycle_can_be_rebuilt_and_stale_generation_handle_converges`（真实 PostgreSQL 与 Cube VM）改写为断言句柄收敛与新环境可用，需 Cube 节点环境运行。
