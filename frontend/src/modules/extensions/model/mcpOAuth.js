export function mcpConnectionLabel(status) {
  return ({ connected: '已连接', reconnect_required: '需要重新连接', disconnected: '未连接', not_required: '无需个人授权' })[status] || '未连接'
}
