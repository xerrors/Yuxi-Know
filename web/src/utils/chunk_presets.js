export const CHUNK_PRESET_OPTIONS = [
  {
    value: 'general',
    label: 'General',
    description: '通用分块：按分隔符和长度切分，适合大多数普通文档。'
  },
  {
    value: 'qa',
    label: 'QA',
    description: '问答分块：优先抽取问题-回答结构，适合 FAQ、题库、问答手册。'
  },
  {
    value: 'book',
    label: 'Book',
    description: '书籍分块：强化章节标题识别并做层级合并，适合教材、手册、长章节文档。'
  },
  {
    value: 'laws',
    label: 'Laws',
    description: '法规分块：按法条层级组织与合并，适合法律法规、制度规范类文本。'
  },
  {
    value: 'semantic',
    label: 'Semantic',
    description: '语义分块：利用嵌入和聚类算法进行语义切分，并自动增强标题上下文。'
  }
]

export const CHUNK_PRESET_LABEL_MAP = Object.fromEntries(
  CHUNK_PRESET_OPTIONS.map((item) => [item.value, item.label])
)

export const CHUNK_PRESET_DESCRIPTION_MAP = Object.fromEntries(
  CHUNK_PRESET_OPTIONS.map((item) => [item.value, item.description])
)

export const getChunkPresetDescription = (presetId) =>
  CHUNK_PRESET_DESCRIPTION_MAP[presetId] || CHUNK_PRESET_DESCRIPTION_MAP.general
