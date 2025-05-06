/**
 * API模块索引文件
 * 导出所有API模块，方便统一引入
 */

// 导出公共API模块
export * from './public_api'

// 导出需要用户认证的API模块
export * from './auth_api'

// 导出需要管理员权限的API模块
export * from './admin_api'

// 导出基础工具函数
export { apiRequest, apiGet, apiPost, apiPut, apiDelete } from './base'

/**
 * 权限说明:
 *
 * 1. public_api.js: 不需要认证就可以访问的API
 *    - 登录、初始化管理员、获取公共配置等
 *
 * 2. auth_api.js: 需要用户认证才能访问的API
 *    - 权限要求: 任何已登录用户（普通用户、管理员、超级管理员）
 *    - 聊天功能、个人设置等
 *
 * 3. admin_api.js: 需要管理员权限才能访问的API
 *    - 权限要求: admin 或 superadmin
 *    - 用户管理、知识库管理、系统配置等
 *
 * 注意：本模块已处理权限验证和请求头，使用时无需再手动添加认证头
 */