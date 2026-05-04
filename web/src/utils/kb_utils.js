import { Database, Waypoints, DatabaseZap } from 'lucide-vue-next'

export const getKbTypeLabel = (type) => {
  const labels = {
    lightrag: 'LightRAG',
    milvus: 'CommonRAG',
    dify: 'Dify'
  }
  return labels[type] || type
}

export const getKbTypeIcon = (type) => {
  const icons = {
    lightrag: Waypoints,
    milvus: DatabaseZap,
    dify: Database
  }
  return icons[type] || Database
}

export const getKbTypeColor = (type) => {
  const colors = {
    lightrag: 'purple',
    milvus: 'red',
    dify: 'gold'
  }
  return colors[type] || 'blue'
}

// 解析模型 spec 为 { model_spec, provider, model_name }
// V2 格式: provider_id:model_id（冒号分隔）
// V1 格式: provider/model_name（斜杠分隔，model_name 可包含冒号）
export const parseModelSpec = (spec) => {
  if (typeof spec !== 'string' || !spec) return null
  const slashIndex = spec.indexOf('/')
  const colonIndex = spec.indexOf(':')
  const index = slashIndex !== -1 ? slashIndex : colonIndex
  return {
    model_spec: spec,
    provider: index !== -1 ? spec.slice(0, index) : '',
    model_name: index !== -1 ? spec.slice(index + 1) : ''
  }
}

// 从 llm_info 构造显示用的 spec 字符串
export const buildDisplaySpec = (llmInfo) => {
  if (llmInfo?.model_spec) return llmInfo.model_spec
  const provider = llmInfo?.provider || ''
  const modelName = llmInfo?.model_name || ''
  return provider && modelName ? `${provider}/${modelName}` : ''
}

// 构造提交给后端的 llm_info，避免旧数据写入空 model_spec
export const buildLlmInfoPayload = (llmInfo) => {
  const payload = {
    provider: llmInfo?.provider || '',
    model_name: llmInfo?.model_name || ''
  }
  if (llmInfo?.model_spec) payload.model_spec = llmInfo.model_spec
  return payload
}
