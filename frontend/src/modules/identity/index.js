// 模块公开模型与用例入口；UI 组件见 ./ui/**/*.vue。
export { clearAutoStartAttempt, sanitizeRedirect, tryAutoStartOIDC } from './model/oidcAutoStart'
export { MIN_PASSWORD_LENGTH, isPasswordLongEnough } from './model/passwordValidation'
export { checkSuperAdminPermission, useUserStore } from './model/user'
