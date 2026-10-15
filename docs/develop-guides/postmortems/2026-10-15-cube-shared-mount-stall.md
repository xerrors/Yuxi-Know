# 嵌套 Cube 外层共享挂载阻塞

日期：2026-10-15
Owner：docker/cube/run-vm.sh
关联决策：[共享挂载恢复与压力验证](../decisions/implemented/2026-10-15-sandbox-environment.md)

## 影响

开发嵌套 Linux/KVM 节点的共享文件请求持续阻塞，环境恢复页面显示 ReadTimeout，真实沙盒集成与 Agent 执行链路失败。节点上保留两个原用户环境；恢复没有替换实例或清除用户 Home，共享文件回读未发现丢失。影响是否覆盖此前其他节点未知。

## 事实时间线

时间使用 Asia/Shanghai，来源为容器、Guest 内核日志及实际维护记录。

- 10 月 14 日 20:28:25 起：持久 Cubelet 日志记录共享目录 bind mount 超过 3 秒。20:30:47 的历史启动日志确认三个 mount 进程阻塞超过 122 秒；20:32:49 又记录 mount 与 ls 阻塞，均进入 FUSE 元数据请求等待。20:34:08 关机同步文件系统超时。
- 10 月 14 日 23:29：开发 API/worker 因源码编辑重载；Cube 节点进程保持运行。
- 23:30:43.555：Cubelet 首次记录本轮 `prepareRequestVolumes → prepareHostDirVolume → bind mount` 的 3 秒超时，随后返回 `CreateStorageFailed`。23:33:22 起四个 mount 进程阻塞超过 122 秒，23:35:25 增至六个；内核随后抑制重复 hung-task 报告。
- 23:37：worker 维护环境出现 ReadTimeout；现场 virtiofsd 存活，Cube 控制面存活。
- 10 月 15 日 00:46 起：确认无活动任务/命令后，保存私有环境与共享文件证据；停止服务并同步根文件系统。Guest 关停未完成，节点容器等待 120 秒后退出 137。
- 00:56：离线节点磁盘备份完成，原盘和备份 `qemu-img check` 均未发现错误。
- 01:00 起：同一磁盘重新启动，原实例命令、Home、休眠与恢复通过；2547 个共享文件/链接一致。随后执行真实 integration、Agent E2E、重复 fuzz 与旧队列隔离对照。

## 因果链

共享通道有两层：外层系统 virtiofsd 通过 QEMU 将宿主目录导出为节点的 `/data/shared/yuxi`，Cubelet 再将用户子目录绑定到内层用户 VM。两次故障的内核栈都在外层路径解析阶段等待：`readlink → filename_lookup → fuse_dentry_revalidate`，或 `inode_permission → fuse_permission → fuse_do_getattr`，最终停在 `fuse_simple_request → request_wait_answer`。较早故障的 ls 经 statx 进入同一等待。现有栈定位的是 LOOKUP/GETATTR 一类元数据通道，未记录写入或 fsync 阻塞。

外层 FUSE 元数据请求等待使 Cubelet 的挂载无法完成，进而阻止用户环境恢复和命令执行。Cubelet 的 mount 子进程即使收到超时后的 SIGKILL，内核等待仍可持续；本轮关机时 Cubelet 两次被强制结束仍未退出，共享目录卸载报 busy，随后文件系统同步超时。导出进程和控制服务存活只能证明进程在线。

20:28 的同类故障早于 23:29 的 API/worker 重载，因此后者不是本次排查发现的首次故障时点；具体触发条件仍需独立证明。默认 128 队列同样只是候选相关条件。按上游示例设置 1024 并恢复节点后业务通道正常；旧 128 的隔离短时压力未复现。

### 上游缺陷与当前版本

2026 年 10 月 15 日回读执行节点：外层为 Ubuntu 24.04、QEMU `1:8.2.2+ds-0ubuntu1.18`、virtiofsd `1.10.0-1ubuntu0.1`；节点 Guest 内核为 `6.6.119-49.21.oc9.x86_64`。这里的外层 QEMU 与系统 virtiofsd 由开发节点镜像提供，与 Cube 内层用户 VM 的虚拟机进程分别管理。

[QEMU 修复 1ba9a522](https://github.com/qemu/qemu/commit/1ba9a5220325dd5260a0c37b6299ce38364a5120)处理通知 eventfd 切换竞态：旧实现发送 `SET_VRING_CALL` 后立即继续，后端可能仍向旧的 masked eventfd 写入完成通知；修复通过 `NEED_REPLY` 和 `REPLY_ACK` 等待后端确认切换完成。Guest 未收到通知时，EVENT_IDX 机制还可能抑制后续完成通知，形成持续等待。

Ubuntu 对应版本的[源码](https://git.launchpad.net/ubuntu/+source/qemu/plain/hw/virtio/vhost-user.c?h=ubuntu/noble-updates)和[发行补丁包](https://archive.ubuntu.com/ubuntu/pool/main/q/qemu/qemu_8.2.2+ds-0ubuntu1.18.debian.tar.xz)均未包含该修复；官方 QEMU `v10.2.0` 源码包含它。virtiofsd 的 [watchdog 提案 !272](https://gitlab.com/virtio-fs/virtiofsd/-/merge_requests/272#note_3473241102)以 QEMU 问题已修复为由关闭，提案本身未合入，不能将升级 virtiofsd 等同于修复此竞态。

该 QEMU 缺陷是当前优先验证的根因假设。历史现场没有保存 virtqueue 索引、eventfd 切换记录和 virtiofsd 线程栈，因此尚不能证明当时确实命中这一竞态。历史 journal 未记录 OOM、FD 耗尽或 ENOSPC，也不足以排除所有无日志的资源问题。

## 安全网为何漏过

原 unit 与健康检查覆盖协议、配置和进程存活，不能观察 Guest 内核的长期 FUSE 等待。既有真实 integration 覆盖单场景用户语义，缺少批量共享 I/O 与休眠后先读旧值的组合压力。当前缺少可以稳定恢复历史内核阻塞的 reproducer，无法证明既有 gate 可以提前拒绝这一准确触发条件。

## 修正与验证

恢复保留节点磁盘和原环境引用，显式队列配置由 [run-vm.sh](https://github.com/xerrors/Yuxi/blob/main/docker/cube/run-vm.sh) 拥有。恢复及压力结束后重新读取数据库身份与宿主共享字节，原环境健康且空闲，共享文件一致；故障前离线磁盘与私有文件归档保留。

[共享挂载 fuzz](https://github.com/xerrors/Yuxi/blob/main/backend/test/integration/sandbox/test_cube_shared_mount_fuzz.py) 使用固定 seed、特殊合法文件名、并发 fsync/替换、独立宿主哈希和准确退出码；恢复前值校验的负向测试在缺失文件时触发 FileNotFoundError，并确认没有生成替代文件。[配置 guard](https://github.com/xerrors/Yuxi/blob/main/backend/test/unit/config/test_cube_nested_node.py) 拒绝删除显式队列或恢复默认 128，但这个 guard 只约束配置，不构成历史阻塞 reproducer。

实际执行命令、结果及未验证范围由[关联决策的验证部分](../decisions/implemented/2026-10-15-sandbox-environment.md#验证)记录。离线旧队列副本的 1024 次 1 MiB 写入、6 个测试 VM 生命周期和 80000 次 stat 全部通过，明确保留这个未复现的反证。

### 通知丢失的隔离验证

后续调查使用离线备份链的只读挂载与新 qcow2 overlay，创建独立、无外网连接的测试节点；测试 Guest 禁用 Cubelet 和 Docker，导出全新 tmpfs 测试目录，不访问在线用户共享目录。虚拟机、内核及共享程序版本与现场一致，CPU/内存为隔离实验配置，未进行生产性能比较。

实验识别 `SET_VRING_CALL` 传递的 eventfd，仅吞掉一次完成通知的 write，不暂停 virtiofsd。源码调用顺序为先 `add_used` 再发送该通知；实验未直接读取 used-ring 索引。队列 128 和 1024 各重复三次，均出现 `mount → readlink → fuse_permission → fuse_do_getattr → request_wait_answer`，静默观察至少三秒仍未完成；向同一 eventfd 重发通知后，0.105～0.122 秒内确认挂载成功及测试文件大小为 15 字节，该时间包含轮询与 SSH 回读。两种队列各补一次 SIGKILL：挂载进程从 S 状态转为 D 状态，仍停在相同 FUSE 等待；重发通知后进程退出。

1024 队列另执行无注入的 1/2/4/8 并发对照，共 120 轮 bind/只读 remount/unmount 和 12000 对 stat/realpath，未自然复现阻塞。这些结果证明单次通知丢失足以产生现场的等待与不可立即终止现象，并证明扩大队列不能消除此机制；它们没有复现 QEMU 的具体 eventfd 切换竞态，也不能验证修复后的 QEMU 是否消除了该竞态。直接吞通知在已修复的 QEMU 上仍可能制造等待，不能把这种注入作为该补丁的通过判据。

隔离测试节点已停止并删除，在线节点和现有用户实例未执行重启、重建或销毁。私有诊断目录保留成功实验的注入源码、启动脚本及两种队列的 JSON 报告，供维护者复核；运行产物与用户备份不入库。准确切换竞态实验和修复版本对照尚未完成。

## 防复发措施

- 启动配置 Owner 固定上游示例的显式队列，宿主配置 unit 拒绝无意恢复旧启动方式。
- [system-tests workflow](https://github.com/xerrors/Yuxi/blob/main/.github/workflows/system-tests.yml) 执行整个 sandbox integration 子树；共享 I/O 超时、旧值丢失、输出/退出码不符或持久句柄未清理时，真实节点测试失败。
- [沙盒运维参考](../../advanced/sandbox-operations.md#运维与验证) 要求阻塞恢复先备份并保留原身份，再以文件、命令及休眠恢复结果验收；进程健康单独不足以声明恢复。

## 未解决风险

缺少未经人工吞通知就能稳定恢复历史故障的 reproducer；短时本机压力不能证明长期不会再次阻塞。通知丢失机制的隔离注入已验证，具体 QEMU 竞态、修复版本对照、远程专用 runner、原生节点重启恢复和数小时 soak 仍未验证。未新增自动重启/重建机制，避免在根因未闭合时改变用户环境及数据。

## 接手调查与修复验证

1. 回读实际外层 QEMU 包版本与 `vhost_set_vring_file` 实现，确认最终选用的发行包确实包含 `1ba9a522` 或等价修复；单凭版本号较新或 virtiofsd 升级不构成证据。
2. 在隔离副本尝试复现准确竞态：延迟后端安装 `SET_VRING_CALL` 的新 eventfd，同时改变 Guest 的 MSI-X/IRQ affinity 并发出元数据请求，记录旧/新 fd、通知与 ACK 的顺序。对照旧实现和含修复实现是否等待后端确认，禁止用无条件吞通知要求修复版自动恢复。
3. 通过准确对照后，在隔离拓扑验证原实例重连、Home 和共享文件回读、命令、休眠恢复及取消清理。数据先读旧值，再进行新写入，避免覆写掩盖丢失。
4. 部署外层 QEMU 修复需要重启执行节点；选择空闲窗口，保存原环境引用和文件校验、离线磁盘备份，恢复后核对原身份与代次。保持既有用户 VM 和数据，不以 rebuild、清库或自动重试创建代替修复。

原始证据入口为 Guest 的历史 journal（20:28 故障启动和 23:30 故障启动）以及 `/data/log/Cubelet/Cubelet-req.log`、`Cubelet-stat.log`。请求日志包含环境与请求内容，读取时只提取时间、错误类型及必要内核栈，不输出用户数据或凭据。现有私有离线备份包含这些日志，但禁止直接启动或写入备份盘。
