export const WORKSPACE_UPLOAD_MAX_FILES = 50
// 与后端单文件上限一致；前端只做提前提示，最终仍由后端拒绝。
export const WORKSPACE_UPLOAD_MAX_FILE_BYTES = 100 * 1024 * 1024
// 目标批次低于 18 MiB；单个超过该值的文件独立成批，仍可能触发入口 413。
export const WORKSPACE_UPLOAD_BATCH_BYTES = 18 * 1024 * 1024

/** 收集文件夹选择结果，保留浏览器提供的相对路径。 */
export function collectFolderUploadEntries(fileList) {
  return Array.from(fileList || []).map((file) => {
    const relativePath = String(file?.webkitRelativePath || '')
    if (!relativePath) {
      throw new Error(`无法获取 ${file?.name || '文件'} 的文件夹路径`)
    }
    return { file, relativePath }
  })
}

/** 在请求前拒绝超过单文件上限的选择，避免上传到一半才失败。 */
export function validateFolderUploadEntries(entries) {
  const oversized = (entries || []).find(
    ({ file }) => Number(file?.size) > WORKSPACE_UPLOAD_MAX_FILE_BYTES
  )
  if (oversized) {
    throw new Error(`${oversized.relativePath} 超过 100 MB，未开始上传`)
  }
}

/** 按文件数量和总字节数切批，保持选择顺序且不拆分单个文件。 */
export function buildFolderUploadBatches(
  entries,
  { maxFiles = WORKSPACE_UPLOAD_MAX_FILES, maxBytes = WORKSPACE_UPLOAD_BATCH_BYTES } = {}
) {
  const batches = []
  let current = []
  let currentBytes = 0

  for (const entry of entries || []) {
    const size = Number(entry?.file?.size) || 0
    if (current.length && (current.length >= maxFiles || currentBytes + size > maxBytes)) {
      batches.push(current)
      current = []
      currentBytes = 0
    }
    current.push(entry)
    currentBytes += size
  }
  if (current.length) batches.push(current)
  return batches
}
