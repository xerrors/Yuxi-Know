import { h } from 'vue'
import { Database, DatabaseZap } from '@lucide/vue'

const ICON_BASE = 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons'

const createBrandIcon = (url) => {
  const Icon = ({ size = 20 }) =>
    h('img', { src: url, style: { width: size + 'px', height: size + 'px' } })
  Icon.inheritAttrs = false
  return Icon
}

export const brandIcons = {
  feishu: createBrandIcon('/icons/feishu.png'),
  dify: createBrandIcon(`${ICON_BASE}/dify-color.svg`),
  notion: createBrandIcon(`${ICON_BASE}/notion.svg`)
}

export const getKbTypeLabel = (type) => {
  const normalized = String(type || '').toLowerCase()
  const labels = {
    milvus: 'Yuxi',
    dify: 'Dify',
    notion: 'Notion',
    feishu: '飞书'
  }
  return labels[normalized] || type
}

export const getKbTypeIcon = (type) => {
  const icons = {
    milvus: DatabaseZap,
    feishu: brandIcons.feishu,
    dify: brandIcons.dify,
    notion: brandIcons.notion
  }
  return icons[type] || Database
}

export const getKbTypeColor = (type) => {
  const colors = {
    milvus: 'blue',
    dify: 'gold',
    notion: 'purple'
  }
  return colors[type] || 'blue'
}

const READ_ONLY_KB_TYPES = new Set(['dify', 'notion', 'feishu'])

export const isReadOnlyKnowledgeBase = (knowledgeBase, kbTypes = {}) => {
  const kbType = (
    typeof knowledgeBase === 'string' ? knowledgeBase : knowledgeBase?.kb_type || 'milvus'
  ).toLowerCase()

  if (knowledgeBase?.supports_documents !== undefined) {
    return knowledgeBase.supports_documents === false
  }
  if (kbTypes[kbType]?.supports_documents !== undefined) {
    return kbTypes[kbType].supports_documents === false
  }
  return READ_ONLY_KB_TYPES.has(kbType)
}

/** 在线阅读连接器可进入详情，文档管理能力保持独立。 */
export const supportsKnowledgeBaseDetail = (knowledgeBase) =>
  !isReadOnlyKnowledgeBase(knowledgeBase) || knowledgeBase?.kb_type === 'feishu'

export const kbUtils = {
  getKbTypeLabel,
  getKbTypeIcon,
  getKbTypeColor,
  isReadOnlyKnowledgeBase,
  supportsKnowledgeBaseDetail
}
