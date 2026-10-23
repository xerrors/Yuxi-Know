# Sandbox 文件工具异步调用委托原生 backend 实现

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/agents/backends/sandbox/backend.py

## 问题

Agent 图以 `astream`/`ainvoke` 运行，文件系统工具因此只调用 backend 的异步方法。DeepAgents 0.7 在 `BaseSandbox` 上新增了 `als`/`awrite`/`aedit`/`aglob`（0.6.7 该类没有任何异步实现），实现方式是"在沙箱执行生成的 shell/Python 命令，再解析 stdout"，从而遮蔽了 `BackendProtocol` 把异步方法转发到同步方法的默认语义。`ProvisionerSandboxBackend` 的原生文件 API 与读写根边界只写在同步方法上，于是这些异步调用落到上游脚本实现，在真实 provisioner sandbox 上暴露三类缺陷。

- 授权前产生副作用并把命令 stdout 交给模型：`BaseSandbox.awrite` 先跑 `_build_write_preflight_cmd` 的 mkdir 脚本，再经 `aupload_files` 转发到 Yuxi 原生 `upload_files`；写权限只在上传阶段判定，脚本对只读 Skill 投影路径已经先执行过，失败时工具错误直接是脚本回显加 traceback（实测得到 `python3 -c "\nimport os, base64\n... 2>&1\nTraceback ...`），这就是 `edit_file`/`write_file` 报出一堆 Python 的来源。
- 授权根之外可读：`aglob` 不做可读根收敛，`aglob("*", path="/etc")` 实测返回 481 条匹配；异步列举与 glob 因此可以读同步侧明确拒绝的路径。
- 超过阈值的编辑必然失败：`_aedit_via_upload` 要往 `/tmp/.deepagents_edit_*` 上传 old/new，被本 backend 写权限拒绝后返回 `permission_denied`（实测 old+new 超过上游 50_000 字节阈值即失败）。

委托同时要求原生实现自身对得上模型看到的契约。DeepAgents 0.6.7 的 `_WRITE_CHECK_TEMPLATE` 用 `os.path.exists` 拒绝已存在文件、`write_file` 工具描述是 "Writes to a new file"；0.7 删掉了该检查，`BaseSandbox.write` docstring 与 `WRITE_FILE_TOOL_DESCRIPTION` 一起改成"不存在则创建，已存在则整体替换"。Yuxi 原生 `write()` 保留了 0.6 的 create-only 拒绝，异步委托后模型按 0.7 描述重写修正自己写错的文件会被拒，真实 E2E 里产物因此停留在错误内容上。`edit()` 的匹配预检使用行窗口 `file.read_file`，该 API 会丢弃文件末尾换行并把 CRLF 折叠成 LF（实测 `alpha\r\nomega\r\n` 读出 `alpha\nomega`），覆盖到末行且以换行结尾的 `old_string` 因此恒报 `String not found` 并把整段 `old_string` 回显给模型。

上游此前的异步适配只覆盖了 `aread` 与 `agrep`（见 [Sandbox grep 控制字符传输修复](2026-09-24-sandbox-grep-nul-transport.md)），`als`/`awrite`/`aedit`/`aglob` 仍留在被遮蔽状态。

## 决策

- 原生 sandbox 文件 API 是本 backend 的唯一实现口径：`als`/`awrite`/`aedit`/`aglob` 显式用 `asyncio.to_thread` 委托同名同步方法，恢复 0.6.7 时代协议默认的转发语义；路径归一化、读写根边界、父目录创建与错误文案只在同步方法里各存在一份。`agrep` 保留上游已有的线程化实现，不在本次改动。
- 写入按 0.7 契约执行：`write()` 与 `awrite()` 对已存在文件整体替换，不再做 create-only 拒绝；`summary._write_tool_result` 同时去掉为 create-only 碰撞准备的 `already exists` 容忍分支。
- `edit()` 的匹配判定以原始字节为事实：用 `download_file` 取精确内容，按 LF 口径归一后计数，再把 LF 形态的 old/new 交给远端 `str_replace_editor`。远端编辑器先归一化为 LF 再字面匹配（实测传 CRLF 形态被拒、传 LF 形态成功且写回为 LF），也实测 `FIRST` 模式对多匹配静默只替换第一处，因此唯一性与缺失判定必须留在本地。
- `glob` 的 `path` 改为 `str | None = None` 并按 `/` 处理，对齐 `CompositeBackend.glob`/`aglob` 在模型省略 path 时把 `None` 传给 default backend 的契约。
- 不为脚本 stdout 的解析失败增加兼容层或重试：缺陷来自走错实现，修复点落在实现口径，stdout 解析保持上游原样。

## 替代方案

- 在 middleware 或工具层过滤错误文本里出现的 Python：症状消失，但异步路径仍在沙箱执行脚本，写权限与可读根边界继续被绕过。
- 调整或适配 `BaseSandbox` 脚本模板在该 provisioner shell 下的输出：把 Yuxi 的行为绑在上游未保证的 stdout 格式上，而原生文件 API 本来就已实现并通过同步路径验证。
- 保留 create-only 并用 `custom_tool_descriptions` 改写 `write_file` 描述：Yuxi 要长期维护一条与上游分叉的工具契约，模型"重写整个文件"这一被描述允许的用法仍会失败，真实 E2E 的期望也得随之调整。
- 像 `aread` 一样为写、编辑、列举、glob 各写一份原生异步实现（复用 `AsyncSandbox` 与 owning `httpx.AsyncClient`）：能免掉线程占用，但要把路径归一化、读写根判定与父目录创建规则复制第二份，两份规则必然漂移的风险大于单次请求走线程转发的代价；`aread` 需要流式读取与二进制上限控制才值得独立实现，这些方法没有同样的需求。
- 编辑继续用行窗口读取预检：丢末尾换行与折叠 CRLF 是该 API 的既有行为，任何在其上的字符串计数都会对末行与 CRLF 文件给出假阴性。

## 后果

`edit_file`/`write_file`/`ls`/`glob` 的同步与异步调用得到同一实现、同一权限边界和同一错误文案，工具结果不再回显 Python 源码或 traceback，`/etc` 之类授权根之外的内容也不再经异步路径读出。`write_file` 现在可以覆盖已存在文件，与模型看到的 0.7 描述一致；约束写能力的仍然是写根边界与工具审批（Project Workdir 内自动放行、之外需要确认），create-only 不再是防误写的屏障，`uploads/` 目录也在可写根内，把附件原件排除出可写根需要单独的变更。编辑 CRLF 文件会把该文件整体行尾改成 LF（sandbox 编辑器自身行为）；编辑含 NUL 但 UTF-8 合法的字节序列仍按文本处理，与非 UTF-8 内容给出的 `is not a text file` 提示不同。代价还包括异步文件操作占用 `asyncio.to_thread` 工作线程、取消不能中止已在飞的同步 HTTP（与 0.6.7 及协议默认一致），实际等待由 sandbox 客户端与命令超时约束。`delete`/`adelete` 在写根边界内委托 `BaseSandbox.delete` 执行，授权边界由本类闭合；详细口径见 [Sandbox delete/adelete 收进写根边界](2026-10-13-sandbox-delete-write-boundary.md)。远端编辑器失败时工具错误文本仍包含该服务的 HTTP 错误体，文件工具不再于沙箱执行生成的 shell/Python 命令。后续升级 DeepAgents 时，`BaseSandbox` 是否新增遮蔽协议的方法必须由这组负向测试给出结论，不能靠升级摘要判断。

## 验证

| 验收主张 | 语义 Owner | 直接证据 | 负向案例 | 结果 |
|---|---|---|---|---|
| 异步编辑经 `CompositeBackend.aedit` 命中原生 `str_replace_editor`，错误文本不含脚本回显 | `ProvisionerSandboxBackend.aedit` | `test/unit/backends/test_sandbox_backends.py::test_provisioner_aedit_replaces_through_native_editor` | 删除异步委托后失败信息为 `Error editing file ...: unexpected server response: python3 -c "`（原分支实测，口径与本次移植一致） | Passed |
| 异步写入/列举/glob 走原生 `write_file`/`list_path`/`find_files`，不执行沙箱命令 | `awrite` / `als` / `aglob` | 同文件 `test_provisioner_awrite_creates_through_native_write_file`、`test_provisioner_als_lists_through_native_list_path`、`test_provisioner_aglob_searches_readable_roots_through_native_find_files` | 去掉委托后 `awrite` 落上传通道（content 变 base64）、`als` 返回空、`aglob` 报 `glob helper emitted unexpected output: python3 -c "`（原分支实测） | Passed |
| `write_file` 重复写同一路径整体替换，不再报 create-only | `write` / `awrite` | 同文件 `test_provisioner_awrite_replaces_existing_file_by_contract`；真实 sandbox `test/integration/services/test_sandbox_async_file_tools.py::test_async_write_and_edit_use_native_sandbox_semantics` 回读第二次写入内容 | 恢复 create-only 预检后第二次写入得到 `Error: File '.../notes.md' already exists` 且原生 `write_file` 只被调用一次（原分支实测） | Passed |
| 末行以换行结尾与 CRLF 文件的编辑都能命中，非 UTF-8 内容给出稳定提示 | `edit` 的 LF 归一口径 | 同文件 `test_provisioner_aedit_matches_old_string_ending_at_file_eof`、`test_provisioner_aedit_normalizes_crlf_file_to_lf`、`test_provisioner_aedit_reports_non_utf8_file_without_reaching_editor` | 预检退回行窗口读取时 EOF 用例得到 `Error: String not found in file: '    return 1\n'`；把 CRLF 变体下发给编辑器时真实 sandbox 返回 `No replacement was performed, old_str \`alpha\r\nomega\` did not appear verbatim`（原分支实测） | Passed |
| 真实 Sandbox 上越界异步调用只给出权限提示，不泄漏 Skill 投影与 `/etc` 内容，大 payload 编辑成功 | `ProvisionerSandboxBackend` 的异步委托 | `test/integration/services/test_sandbox_async_file_tools.py` 4 个用例在真实 provisioner sandbox 全部通过；全量 `test/unit` 2480 passed / 60 skipped | 回退委托后分别失败于"`python3 -c \"...skills/probe...` 代替 `permission denied for write`"与"`already exists` 断言得到 `None`"；实测越界 `aglob("*", path="/etc")` 返回 481 条匹配、超过 50_000 字节的异步编辑返回 `permission_denied`（原分支实测） | Passed |

未覆盖范围：真实 Run 链路（E2E 回放）未在本次复跑；异步委托口径在真实 provisioner sandbox 上的行为以集成用例为准。
