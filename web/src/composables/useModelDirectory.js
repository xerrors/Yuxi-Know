import { ref } from 'vue'
import { modelProviderApi } from '@/apis/system_api'
import { createSingleFlight } from '@/utils/singleFlight'

// 模型目录是跨组件共享的只读投影：按 modelType 缓存，别名变更时显式失效。
const directories = ref({})
const loaders = new Map()

const loaderFor = (modelType) => {
  if (!loaders.has(modelType)) {
    loaders.set(
      modelType,
      createSingleFlight(async () => {
        const response = await modelProviderApi.getV2Models(modelType)
        if (!response?.success) throw new Error('模型目录请求失败')
        return response.data || {}
      })
    )
  }
  return loaders.get(modelType)
}

/** 使指定类型的模型目录缓存失效，下一次加载重新请求后端。 */
export const invalidateModelDirectory = (modelType = 'chat') => {
  const next = { ...directories.value }
  delete next[modelType]
  directories.value = next
  loaders.get(modelType)?.reset()
}

/** 共享模型目录 composable，供模型选择器与消息引用栏按别名展示模型名称。 */
export function useModelDirectory(modelType = 'chat') {
  const load = async () => {
    if (directories.value[modelType]) return directories.value[modelType]
    const data = await loaderFor(modelType)()
    directories.value = { ...directories.value, [modelType]: data }
    return data
  }

  // 先按 spec 精确匹配；退而匹配唯一 model_id，避免跨供应商误用别名。
  const resolveDisplayName = ({ spec, modelId } = {}) => {
    const directory = directories.value[modelType]
    if (!directory) return ''
    const models = Object.values(directory).flatMap((provider) => provider.models || [])
    if (spec) {
      const hit = models.find((model) => model.spec === spec)
      if (hit?.display_name) return hit.display_name
    }
    if (modelId) {
      const hits = models.filter((model) => model.model_id === modelId)
      if (hits.length === 1 && hits[0].display_name) return hits[0].display_name
    }
    return ''
  }

  return { load, resolveDisplayName }
}
