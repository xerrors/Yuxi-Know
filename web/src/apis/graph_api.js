import { apiGet } from './base'

/**
 * 图数据API调用 - 基于LightRAG的新接口
 */

/**
 * 获取所有可用的数据库
 * @returns {Promise} - 数据库列表
 */
export const getAvailableDatabases = async () => {
  return await apiGet('/api/graph/databases', {}, true)
}

/**
 * 获取图标签列表
 * @param {string} dbId - 数据库ID
 * @returns {Promise} - 标签列表
 */
export const getGraphLabels = async (dbId) => {
  if (!dbId) {
    throw new Error('db_id is required')
  }

  const queryParams = new URLSearchParams({
    db_id: dbId
  })

  return await apiGet(`/api/graph/labels?${queryParams.toString()}`, {}, true)
}

/**
 * 获取子图数据 - 主要接口
 * @param {Object} params - 查询参数
 * @param {string} params.db_id - 数据库ID
 * @param {string} params.node_label - 节点标签 (使用 "*" 获取全图)
 * @param {number} params.max_depth - 最大深度
 * @param {number} params.max_nodes - 最大节点数
 * @returns {Promise} - 子图数据
 */
export const getSubgraph = async (params) => {
  const { db_id, node_label = "*", max_depth = 2, max_nodes = 100 } = params

  if (!db_id) {
    throw new Error('db_id is required')
  }

  const queryParams = new URLSearchParams({
    db_id: db_id,
    node_label: node_label,
    max_depth: max_depth.toString(),
    max_nodes: max_nodes.toString()
  })

  return await apiGet(`/api/graph/subgraph?${queryParams.toString()}`, {}, true)
}

/**
 * 获取图统计信息
 * @param {string} dbId - 数据库ID
 * @returns {Promise} - 统计数据
 */
export const getGraphStats = async (dbId) => {
  if (!dbId) {
    throw new Error('db_id is required')
  }

  const queryParams = new URLSearchParams({
    db_id: dbId
  })

  return await apiGet(`/api/graph/stats?${queryParams.toString()}`, {}, true)
}

/**
 * 获取完整图数据 - 使用新的子图接口
 * @param {Object} params - 查询参数
 * @param {string} params.db_id - 数据库ID
 * @param {string} params.node_label - 节点标签筛选
 * @param {number} params.max_nodes - 最大节点数
 * @param {number} params.max_depth - 最大深度
 * @returns {Promise} - 完整图数据
 */
export const getFullGraph = async (params = {}) => {
  const { db_id, node_label = "*", max_nodes = 200, max_depth = 2 } = params

  if (!db_id) {
    throw new Error('db_id is required for graph operations')
  }

  try {
    // 使用子图接口获取数据
    const response = await getSubgraph({
      db_id,
      node_label,
      max_nodes,
      max_depth
    })

    if (!response.success) {
      throw new Error('获取图数据失败')
    }

    return {
      success: true,
      data: {
        nodes: response.data.nodes,
        edges: response.data.edges,
        is_truncated: response.data.is_truncated,
        stats: {
          total_nodes: response.data.total_nodes,
          total_edges: response.data.total_edges,
          displayed_nodes: response.data.nodes.length,
          displayed_edges: response.data.edges.length
        }
      }
    }
  } catch (error) {
    console.error('获取完整图数据失败:', error)
    throw error
  }
}

/**
 * 根据特定标签获取子图
 * @param {Object} params - 查询参数
 * @param {string} params.db_id - 数据库ID
 * @param {string} params.entity_type - 实体类型 
 * @param {number} params.max_nodes - 最大节点数
 * @param {number} params.max_depth - 最大深度
 * @returns {Promise} - 子图数据
 */
export const getGraphByEntityType = async (params = {}) => {
  const { db_id, entity_type, max_nodes = 100, max_depth = 2 } = params

  if (!db_id) {
    throw new Error('db_id is required')
  }

  return await getSubgraph({
    db_id,
    node_label: entity_type || "*",
    max_nodes,
    max_depth
  })
}

/**
 * 展开指定节点的邻居
 * @param {Object} params - 查询参数  
 * @param {string} params.db_id - 数据库ID
 * @param {string} params.node_label - 节点标签
 * @param {number} params.max_depth - 最大深度
 * @param {number} params.max_nodes - 最大节点数
 * @returns {Promise} - 邻居节点数据
 */
export const expandNodeNeighbors = async (params) => {
  const { db_id, node_label, max_depth = 1, max_nodes = 50 } = params

  if (!db_id || !node_label) {
    throw new Error('db_id and node_label are required')
  }

  return await getSubgraph({
    db_id,
    node_label,
    max_depth,
    max_nodes
  })
}

// ==================== 兼容性方法 ====================

/**
 * 获取图节点数据 (已弃用，建议使用 getSubgraph)
 * @deprecated 请使用 getSubgraph 替代
 */
export const getGraphNodes = async (params = {}) => {
  console.warn('getGraphNodes is deprecated, please use getSubgraph instead')
  const { db_id } = params
  if (!db_id) {
    throw new Error('db_id is required. Please provide db_id parameter.')
  }
  return await getSubgraph({ ...params, node_label: "*" })
}

/**
 * 获取图边数据 (已弃用，建议使用 getSubgraph)  
 * @deprecated 请使用 getSubgraph 替代
 */
export const getGraphEdges = async (params = {}) => {
  console.warn('getGraphEdges is deprecated, please use getSubgraph instead')
  const { db_id } = params
  if (!db_id) {
    throw new Error('db_id is required. Please provide db_id parameter.')
  }
  return await getSubgraph({ ...params, node_label: "*" })
}

// ==================== 工具函数 ====================

/**
 * 根据实体类型获取颜色
 * @param {string} entityType - 实体类型
 * @returns {string} - 颜色值
 */
export const getEntityTypeColor = (entityType) => {
  const colorMap = {
    'person': '#FF6B6B',      // 红色 - 人物
    'organization': '#4ECDC4', // 青色 - 组织
    'location': '#45B7D1',    // 蓝色 - 地点
    'geo': '#45B7D1',         // 蓝色 - 地理位置
    'event': '#96CEB4',       // 绿色 - 事件
    'category': '#FFEAA7',    // 黄色 - 分类
    'equipment': '#DDA0DD',   // 紫色 - 设备
    'athlete': '#FF7675',     // 红色 - 运动员
    'record': '#FD79A8',      // 粉色 - 记录
    'year': '#FDCB6E',        // 橙色 - 年份
    'UNKNOWN': '#B2BEC3',     // 灰色 - 未知
    'unknown': '#B2BEC3'      // 灰色 - 未知
  }

  return colorMap[entityType] || colorMap['unknown']
}

/**
 * 根据权重计算边的粗细
 * @param {number} weight - 权重值
 * @param {number} minWeight - 最小权重
 * @param {number} maxWeight - 最大权重  
 * @returns {number} - 边的粗细
 */
export const calculateEdgeWidth = (weight, minWeight = 1, maxWeight = 10) => {
  const minWidth = 1
  const maxWidth = 5
  const normalizedWeight = (weight - minWeight) / (maxWeight - minWeight)
  return minWidth + normalizedWeight * (maxWidth - minWidth)
}