export const COOPERATION_DEPTH_KEY = 'max_cooperation_depth'

/** 只接受完整非负整数；清空或非法输入不改变已保存值。 */
export function applyCooperationDepth(value, update) {
  if (Number.isInteger(value) && value >= 0) update(value)
}
