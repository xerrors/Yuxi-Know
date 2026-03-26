import { ref } from 'vue'

/**
 * @typedef {Object} MentionFile
 * @property {string} path - 文件路径
 * @property {string} [content] - 文件内容
 * @property {string} [modified_at] - 修改时间
 * @property {number} [size] - 文件大小
 */

/**
 * @typedef {Object} MentionKnowledgeBase
 * @property {string} db_id - 知识库ID
 * @property {string} name - 知识库名称
 */

/**
 * @typedef {Object} MentionMcp
 * @property {string} name - MCP 名称
 * @property {string} [description] - 描述
 */

/**
 * @typedef {Object} MentionConfig
 * @property {MentionFile[]} [files] - 可引用的文件列表
 * @property {MentionKnowledgeBase[]} [knowledgeBases] - 可引用的知识库列表
 * @property {MentionMcp[]} [mcps] - 可引用的 MCP 服务器列表
 */

/**
 * @typedef {Object} MentionItem
 * @property {string} value - 显示和插入的值
 * @property {string} label - 显示标签
 * @property {'file'|'knowledge'|'mcp'} type - 类型
 * @property {string} [description] - 描述信息
 */

/**
 * @typedef {Object} UseMentionReturn
 * @property {import('vue').Ref<MentionConfig>} mentionConfig - 当前的 mention 配置
 * @property {Function} setMention - 设置 mention 配置
 * @property {Function} updateFiles - 更新文件列表
 * @property {Function} updateKnowledgeBases - 更新知识库列表
 * @property {Function} updateMcps - 更新 MCP 列表
 * @property {Function} getFilteredItems - 根据查询获取过滤后的候选列表
 */

/**
 * Mention @提及 功能管理
 * @returns {UseMentionReturn}
 */
export function useMention() {
  const mentionConfig = ref({
    files: [],
    knowledgeBases: [],
    mcps: []
  })

  /**
   * 设置完整的 mention 配置
   * @param {MentionConfig} config
   */
  const setMention = (config) => {
    mentionConfig.value = {
      files: config.files || [],
      knowledgeBases: config.knowledgeBases || [],
      mcps: config.mcps || []
    }
  }

  /**
   * 更新文件列表
   * @param {MentionFile[]} files
   */
  const updateFiles = (files) => {
    mentionConfig.value.files = files || []
  }

  /**
   * 更新知识库列表
   * @param {MentionKnowledgeBase[]} knowledgeBases
   */
  const updateKnowledgeBases = (knowledgeBases) => {
    mentionConfig.value.knowledgeBases = knowledgeBases || []
  }

  /**
   * 更新 MCP 服务器列表
   * @param {MentionMcp[]} mcps
   */
  const updateMcps = (mcps) => {
    mentionConfig.value.mcps = mcps || []
  }

  /**
   * 获取分类后的所有候选项
   * @returns {{ files: MentionItem[], knowledgeBases: MentionItem[], mcps: MentionItem[] }}
   */
  const getCategorizedItems = () => {
    const { files, knowledgeBases, mcps } = mentionConfig.value

    const fileItems = files.map((f) => ({
      value: f.path,
      label: f.path.split('/').pop() || f.path,
      type: 'file',
      description: f.path
    }))

    const kbItems = knowledgeBases.map((kb) => ({
      value: kb.name,
      label: kb.name,
      type: 'knowledge',
      description: kb.db_id
    }))

    const mcpItems = mcps.map((m) => ({
      value: m.name,
      label: m.name,
      type: 'mcp',
      description: m.description || ''
    }))

    return {
      files: fileItems,
      knowledgeBases: kbItems,
      mcps: mcpItems
    }
  }

  /**
   * 根据查询字符串过滤候选项
   * @param {string} query - 查询字符串（不含 @ 符号）
   * @returns {{ files: MentionItem[], knowledgeBases: MentionItem[], mcps: MentionItem[] }}
   */
  const getFilteredItems = (query = '') => {
    const lowerQuery = query.toLowerCase()
    const categorized = getCategorizedItems()

    const filterItems = (items) =>
      items.filter(
        (item) =>
          item.label.toLowerCase().includes(lowerQuery) ||
          item.value.toLowerCase().includes(lowerQuery)
      )

    return {
      files: filterItems(categorized.files),
      knowledgeBases: filterItems(categorized.knowledgeBases),
      mcps: filterItems(categorized.mcps)
    }
  }

  return {
    mentionConfig,
    setMention,
    updateFiles,
    updateKnowledgeBases,
    updateMcps,
    getFilteredItems,
    getCategorizedItems
  }
}
