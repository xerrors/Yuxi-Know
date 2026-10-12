"""协作树与沙盒回收共同使用的持久锁键；已部署键字节不可变。"""


def cooperation_lock_key(runtime_scope_id: str) -> str:
    """树写入与运行释放共用同一根；获取位置遵循各 owning 仓储的锁序。"""
    return f"cooperation:{runtime_scope_id}"


def sandbox_release_lock_key(runtime_scope_id: str) -> str:
    """回收持独占锁，执行持共享尝试锁，均先于树写入锁。"""
    return f"sandbox-release:{runtime_scope_id}"
