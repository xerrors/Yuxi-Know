"""协作树与用户环境生命周期的持久锁键。"""


def cooperation_lock_key(runtime_scope_id: str) -> str:
    """树写入与运行释放共用同一根；获取位置遵循各 owning 仓储的锁序。"""
    return f"cooperation:{runtime_scope_id}"


def user_environment_lock_key(uid: str) -> str:
    """用户环境生命周期与执行领取共同使用的锁键。"""
    return f"user-environment:{uid}"
