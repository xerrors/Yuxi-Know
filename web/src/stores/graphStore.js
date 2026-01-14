import { defineStore } from 'pinia'
import { DirectedGraph } from 'graphology'

export const useGraphStore = defineStore('graph', {
  state: () => ({
    // 选中和聚焦状态
    selectedNode: null,
    focusedNode: null,
    selectedEdge: null,
    focusedEdge: null,

    // 图数据
    rawGraph: null,
    sigmaGraph: null,
    sigmaInstance: null,

    // 实体类型和颜色映射
    entityTypes: [],
    typeColorMap: new Map(),

    // 加载状态
    isFetching: false,
    graphIsEmpty: false,

    // 移动到选中节点的标志
    moveToSelectedNode: false,

    // 图统计信息
    stats: {
      displayed_nodes: 0,
      displayed_edges: 0,
      is_truncated: false
    }
  }),

  getters: {
    // 获取选中节点的详细信息
    selectedNodeData: (state) => {
      if (!state.selectedNode || !state.rawGraph) return null
      return state.rawGraph.nodes.find((node) => node.id === state.selectedNode)
    },

    // 获取选中边的详细信息
    selectedEdgeData: (state) => {
      if (!state.selectedEdge || !state.rawGraph) return null

      console.log('查找边数据，选中边ID:', state.selectedEdge)

      // 首先尝试通过dynamicId匹配（Sigma使用的ID格式）
      let foundEdge = state.rawGraph.edges.find((edge) => edge.dynamicId === state.selectedEdge)
      if (foundEdge) {
        console.log('通过dynamicId找到边:', foundEdge)
        return foundEdge
      }

      // 如果没找到，尝试通过原始ID匹配
      foundEdge = state.rawGraph.edges.find((edge) => edge.id === state.selectedEdge)
      if (foundEdge) {
        console.log('通过id找到边:', foundEdge)
        return foundEdge
      }

      // 对于格式为 source-target-index 的dynamicId，也尝试解析
      const dynamicIdPattern = /^(.+)-(.+)-(\d+)$/
      const match = state.selectedEdge.match(dynamicIdPattern)
      if (match) {
        const [, source, target, index] = match
        foundEdge = state.rawGraph.edges.find(
          (edge) => edge.source === source && edge.target === target
        )
        if (foundEdge) {
          console.log('通过解析dynamicId找到边:', foundEdge)
          return foundEdge
        }
      }

      // 最后尝试通过source->target格式匹配
      const arrowPattern = /^(.+)->(.+)$/
      const arrowMatch = state.selectedEdge.match(arrowPattern)
      if (arrowMatch) {
        const [, source, target] = arrowMatch
        foundEdge = state.rawGraph.edges.find(
          (edge) => edge.source === source.trim() && edge.target === target.trim()
        )
        if (foundEdge) {
          console.log('通过箭头格式找到边:', foundEdge)
          return foundEdge
        }
      }

      console.warn('未找到匹配的边数据，选中边ID:', state.selectedEdge)
      return null
    },

    // 检查图是否为空
    isGraphEmpty: (state) => {
      return !state.rawGraph || state.rawGraph.nodes.length === 0
    }
  },

  actions: {
    // 设置Sigma实例
    setSigmaInstance(instance) {
      this.sigmaInstance = instance
    },

    // 节点选择和聚焦
    setSelectedNode(nodeId, moveToNode = false) {
      this.selectedNode = nodeId
      this.moveToSelectedNode = moveToNode
      // 如果选中节点，清除选中的边
      if (nodeId) {
        this.selectedEdge = null
      }
    },

    setFocusedNode(nodeId) {
      this.focusedNode = nodeId
    },

    setSelectedEdge(edgeId) {
      this.selectedEdge = edgeId
      // 如果选中边，清除选中的节点
      if (edgeId) {
        this.selectedNode = null
      }
    },

    setFocusedEdge(edgeId) {
      this.focusedEdge = edgeId
    },

    // 清除所有选择
    clearSelection() {
      this.selectedNode = null
      this.focusedNode = null
      this.selectedEdge = null
      this.focusedEdge = null
    },

    // 设置加载状态
    setIsFetching(isFetching) {
      this.isFetching = isFetching
    },

    // 设置实体类型
    setEntityTypes(types) {
      this.entityTypes = types
      this.updateTypeColorMap()
    },

    // 更新类型颜色映射
    updateTypeColorMap() {
      const colorPalette = [
        '#FF6B6B', // 人物 - 红色
        '#4ECDC4', // 组织 - 青色
        '#45B7D1', // 地点 - 蓝色
        '#96CEB4', // 事件 - 绿色
        '#FFEAA7', // 分类 - 黄色
        '#DDA0DD', // 设备 - 紫色
        '#FF7675', // 运动员 - 红色
        '#FD79A8', // 记录 - 粉色
        '#FDCB6E', // 年份 - 橙色
        '#B2BEC3' // 未知 - 灰色
      ]

      const typeColorMap = new Map()
      this.entityTypes.forEach((type, index) => {
        const colorIndex = index % colorPalette.length
        typeColorMap.set(type.type, colorPalette[colorIndex])
      })

      // 为特殊类型设置固定颜色
      typeColorMap.set('person', '#FF6B6B')
      typeColorMap.set('organization', '#4ECDC4')
      typeColorMap.set('location', '#45B7D1')
      typeColorMap.set('geo', '#45B7D1')
      typeColorMap.set('event', '#96CEB4')
      typeColorMap.set('category', '#FFEAA7')
      typeColorMap.set('unknown', '#B2BEC3')

      this.typeColorMap = typeColorMap
    },

    // 获取实体类型颜色
    getEntityColor(entityType) {
      return this.typeColorMap.get(entityType) || '#B2BEC3'
    },

    // 设置原始图数据
    setRawGraph(rawGraph) {
      this.rawGraph = rawGraph
      this.graphIsEmpty = !rawGraph || rawGraph.nodes.length === 0
      this.updateStats()
    },

    // 设置Sigma图数据
    setSigmaGraph(sigmaGraph) {
      this.sigmaGraph = sigmaGraph
    },

    // 更新统计信息
    updateStats() {
      if (this.rawGraph) {
        this.stats = {
          displayed_nodes: this.rawGraph.nodes.length,
          displayed_edges: this.rawGraph.edges.length,
          is_truncated: this.rawGraph.is_truncated ?? this.stats?.is_truncated ?? false
        }
      }
    },

    // 从API数据创建图数据结构
    createGraphFromApiData(nodesData, edgesData) {
      const rawGraph = {
        nodes: [],
        edges: [],
        nodeIdMap: {},
        edgeIdMap: {},
        edgeDynamicIdMap: {}
      }

      console.log('Processing nodes data:', nodesData)

      // 处理节点数据
      nodesData.forEach((node, index) => {
        // 适配新的LightRAG API格式
        const nodeId = String(node.id)
        const labels = node.labels || [node.entity_type || 'unknown']
        const entityType = node.entity_type || labels[0] || 'unknown'

        const processedNode = {
          id: nodeId,
          labels: Array.isArray(labels) ? labels.map(String) : [String(labels)],
          entity_type: String(entityType),
          properties: {
            entity_id: String(node.properties?.entity_id || node.entity_id || nodeId),
            entity_type: String(entityType),
            description: String(node.properties?.description || node.description || ''),
            file_path: String(node.properties?.file_path || node.file_path || ''),
            ...(node.properties || {})
          },
          // Sigma.js需要的属性
          size: this.calculateNodeSize(node),
          x: Math.random() * 1000, // 随机初始位置
          y: Math.random() * 1000,
          color: this.getEntityColor(String(entityType)),
          degree: 0 // 将在处理边时计算
        }

        rawGraph.nodes.push(processedNode)
        rawGraph.nodeIdMap[nodeId] = index
      })

      // 计算节点度数
      const nodeDegrees = {}
      edgesData.forEach((edge) => {
        const sourceId = String(edge.source)
        const targetId = String(edge.target)
        nodeDegrees[sourceId] = (nodeDegrees[sourceId] || 0) + 1
        nodeDegrees[targetId] = (nodeDegrees[targetId] || 0) + 1
      })

      // 更新节点度数和大小
      rawGraph.nodes.forEach((node) => {
        node.degree = nodeDegrees[node.id] || 0
        node.size = this.calculateNodeSize({ degree: node.degree })
      })

      console.log('Processing edges data:', edgesData)

      // 处理边数据
      edgesData.forEach((edge, index) => {
        const sourceId = String(edge.source)
        const targetId = String(edge.target)
        const dynamicId = `${sourceId}-${targetId}-${index}`

        // 适配新的LightRAG API格式
        const weight = Number(edge.properties?.weight || edge.weight || 1.0)

        const processedEdge = {
          id: String(edge.id),
          source: sourceId,
          target: targetId,
          type: edge.type || 'DIRECTED',
          properties: {
            weight: weight,
            keywords: String(edge.properties?.keywords || edge.keywords || ''),
            description: String(edge.properties?.description || edge.description || ''),
            file_path: String(edge.properties?.file_path || edge.file_path || ''),
            ...(edge.properties || {})
          },
          dynamicId: dynamicId,
          // Sigma.js需要的属性
          size: this.calculateEdgeSize(weight),
          color: '#666',
          originalWeight: weight
        }

        rawGraph.edges.push(processedEdge)
        rawGraph.edgeIdMap[edge.id] = index
        rawGraph.edgeDynamicIdMap[dynamicId] = index
      })

      return rawGraph
    },

    // 计算节点大小
    calculateNodeSize(node) {
      const baseSizeM = 15
      const degree = node.degree || 0
      return Math.min(baseSizeM + degree * 3, 40)
    },

    // 计算边大小
    calculateEdgeSize(weight) {
      const minSize = 3 // 与Sigma配置中的minEdgeThickness保持一致
      const maxSize = 8 // 与Sigma配置中的maxEdgeThickness保持一致
      const normalizedWeight = Math.max(0, Math.min(1, (weight - 1) / 9)) // 假设权重范围1-10
      return minSize + normalizedWeight * (maxSize - minSize)
    },

    // 创建Sigma图实例
    createSigmaGraph(rawGraph) {
      console.log(
        '开始创建Sigma图，节点数量:',
        rawGraph.nodes.length,
        '边数量:',
        rawGraph.edges.length
      )
      const sigmaGraph = new DirectedGraph()

      // 添加节点
      rawGraph.nodes.forEach((node) => {
        // 确保所有属性都是正确的类型
        const nodeAttributes = {
          label: String(node.properties?.entity_id || node.id),
          size: Number(node.size) || 15,
          color: String(node.color) || '#B2BEC3',
          x: Number(node.x) || Math.random() * 1000,
          y: Number(node.y) || Math.random() * 1000,
          // 保存原始数据引用
          originalData: node
        }

        sigmaGraph.addNode(String(node.id), nodeAttributes)
      })

      console.log('节点添加完成，开始添加边...')

      // 添加边
      let edgeAddedCount = 0
      let edgeSkippedCount = 0
      rawGraph.edges.forEach((edge, index) => {
        // 添加调试信息
        if (index < 3) {
          console.log('处理边 #' + index + ':', {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            dynamicId: edge.dynamicId,
            edgeObject: edge
          })
        }

        if (sigmaGraph.hasNode(String(edge.source)) && sigmaGraph.hasNode(String(edge.target))) {
          // 确保所有属性都是正确的类型
          const edgeAttributes = {
            size: Number(edge.size) || 1,
            color: String(edge.color) || '#666',
            label: String(edge.properties?.keywords || edge.properties?.description || ''),
            originalWeight: Number(edge.originalWeight) || 1,
            // 保存原始数据引用
            originalData: edge
          }

          // 使用标准的 addEdge 方法：addEdge(edgeId, source, target, attributes)
          try {
            // 使用动态ID作为Sigma边ID，避免重复
            const sigmaEdgeId = edge.dynamicId || `${edge.source}->${edge.target}`

            // 检查是否已存在相同的边
            if (!sigmaGraph.hasEdge(sigmaEdgeId)) {
              sigmaGraph.addEdgeWithKey(
                sigmaEdgeId,
                String(edge.source),
                String(edge.target),
                edgeAttributes
              )
              edgeAddedCount++
            } else {
              edgeSkippedCount++
            }
          } catch (err) {
            console.warn('添加边失败:', {
              source: edge.source,
              target: edge.target,
              attributes: edgeAttributes,
              error: err.message
            })
          }
        } else {
          console.warn('节点不存在，跳过边:', {
            source: edge.source,
            target: edge.target,
            hasSource: sigmaGraph.hasNode(String(edge.source)),
            hasTarget: sigmaGraph.hasNode(String(edge.target))
          })
        }
      })

      console.log(`边添加完成: 成功 ${edgeAddedCount}, 跳过 ${edgeSkippedCount}`)

      return sigmaGraph
    },

    // 重置所有状态
    reset() {
      this.selectedNode = null
      this.focusedNode = null
      this.selectedEdge = null
      this.focusedEdge = null
      this.rawGraph = null
      this.sigmaGraph = null
      this.moveToSelectedNode = false
      this.graphIsEmpty = false
      this.stats = {
        displayed_nodes: 0,
        displayed_edges: 0,
        is_truncated: false
      }
    }
  }
})
