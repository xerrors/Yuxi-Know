export function mcpConnectionLabel(status) {
  return ({ connected: '已连接', reconnect_required: '需要重新连接', disconnected: '未连接', not_required: '无需个人授权' })[status] || '未连接'
}

/** 展示连接实际使用的认证方式。 */
export function mcpAuthLabel(mode) {
  return ({ headers: '共享凭据', oauth: '个人账号授权', delegation: '内部服务认证' })[mode] || '共享凭据'
}
