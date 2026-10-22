/** 汇总已完成上传文件的路径、哈希、大小和相对来源路径。 */
export function collectUploadMetadata(files) {
  const items = []
  const content_hashes = {}
  const file_sizes = {}
  const source_paths = {}
  for (const file of files || []) {
    if (file.status !== 'done') continue
    const file_path = file.response?.file_path
    if (!file_path) continue
    items.push(file_path)
    if (file.response?.content_hash) content_hashes[file_path] = file.response.content_hash
    if (Number.isFinite(file.response?.size)) file_sizes[file_path] = file.response.size
    const relativePath = file.webkitRelativePath || file.originFileObj?.webkitRelativePath
    if (relativePath) source_paths[file_path] = relativePath
  }
  return { items, content_hashes, file_sizes, source_paths }
}

/** 隐藏文件或隐藏目录中的文件不进入上传队列。 */
export function isHiddenUploadPath(name, relativePath) {
  if (name && name.startsWith('.')) return true
  if (relativePath) {
    const parts = relativePath.split('/')
    if (parts.some((part) => part.startsWith('.'))) return true
  }
  return false
}

/** 上传前的文件准入：隐藏路径和不受支持的扩展名都不进入队列。 */
export function shouldAcceptUploadFile(file, isSupportedExtension) {
  if (!file) return false
  const name = file.name || ''
  const relativePath = file.webkitRelativePath || file.originFileObj?.webkitRelativePath || ''
  if (isHiddenUploadPath(name, relativePath)) return false
  return isSupportedExtension(name)
}

/** 组装添加文档参数；没有相对来源路径时不发送空 source_paths。 */
export function buildUploadParams(processingParams, metadata) {
  const params = {
    ...processingParams,
    content_hashes: metadata.content_hashes,
    file_sizes: metadata.file_sizes
  }
  if (Object.keys(metadata.source_paths).length > 0) {
    params.source_paths = metadata.source_paths
  }
  return params
}
