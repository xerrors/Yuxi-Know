<template>
  <div class="knowledge-graph-viewer">
    <!-- 控制面板 -->
    <div class="control-panel" v-if="!props.hideControls">
      <div class="database-section">
        <a-select
          v-if="!hideDbSelector"
          v-model:value="selectedDatabase"
          placeholder="选择数据库"
          size="small"
          style="width: 160px; margin-right: 6px"
          :loading="loadingDatabases"
          @change="onDatabaseChange"
        >
          <a-select-option
            v-for="db in availableDatabases"
            :key="db.db_id"
            :value="db.db_id"
          >
            {{ db.name }} ({{ db.row_count || 0 }} 文件)
          </a-select-option>
        </a-select>

        <a-select
          v-model:value="selectedLabel"
          placeholder="选择标签/实体类型"
          size="small"
          style="width: 140px"
          :loading="loadingLabels"
          :disabled="!selectedDatabase"
          allow-clear
          show-search
        >
          <a-select-option value="*">所有节点</a-select-option>
          <a-select-option
            v-for="label in availableLabels"
            :key="label"
            :value="label"
          >
            {{ label }}
          </a-select-option>
        </a-select>
      </div>

      <div class="search-section">
        <a-input-number
          v-model:value="searchParams.max_nodes"
          :min="10"
          :max="1000"
          :step="10"
          size="small"
          addon-before="limit"
          style="width: 140px"
        />
        <a-input-number
          v-model:value="searchParams.max_depth"
          :min="1"
          :max="5"
          :step="1"
          size="small"
          addon-before="depth"
          style="width: 120px; margin-left: 6px"
        />
        <a-button
          type="primary"
          size="small"
          :loading="loading"
          @click="loadGraphData"
          :disabled="!selectedDatabase"
          style="margin-left: 6px"
        >
          <SearchOutlined v-if="!loading" /> 加载图谱
        </a-button>
      </div>

      <div v-if="!props.hideStats" class="stats-section">
        <a-tag color="blue" size="small">节点: {{ stats.displayed_nodes || 0 }}</a-tag>
        <a-tag color="green" size="small">边: {{ stats.displayed_edges || 0 }}</a-tag>
        <!-- <a-tag v-if="stats.is_truncated" color="red" size="small">已截断</a-tag> -->
      </div>
    </div>

    <!-- Sigma.js图可视化容器 -->
    <div
      class="sigma-container"
      ref="sigmaContainer"
      :class="{ 'loading': loading }"
    ></div>

    <!-- 节点详情面板 -->
    <div
      v-if="selectedNodeData"
      class="detail-panel node-panel"
      :style="{ transform: `translate(${nodePanelPosition.x}px, ${nodePanelPosition.y}px)` }"
      @mousedown="startDragPanel('node', $event)"
    >
      <div class="detail-header">
        <div class="panel-type-indicator node-indicator"></div>
        <h4>节点: {{ getNodeDisplayName(selectedNodeData) }}</h4>
        <a-button type="text" size="small" @click="clearSelection">
          <CloseOutlined />
        </a-button>
      </div>
      <div class="detail-content">
        <div class="detail-item">
          <span class="detail-label">ID:</span>
          <span class="detail-value">{{ selectedNodeData.id }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">标签:</span>
          <span class="detail-value">{{ selectedNodeData.labels?.join(', ') || 'N/A' }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">类型:</span>
          <span class="detail-value">{{ selectedNodeData.entity_type }}</span>
        </div>
        <div v-if="selectedNodeData.properties?.description" class="detail-item">
          <span class="detail-label">描述:</span>
          <span class="detail-value">{{ selectedNodeData.properties.description }}</span>
        </div>
        <div class="detail-actions">
          <a-button
            type="primary"
            size="small"
            @click="expandNode(selectedNodeData.id)"
            :loading="expanding"
            :disabled="!selectedDatabase"
          >
            展开相邻节点
          </a-button>
        </div>
      </div>
    </div>

    <!-- 边详情面板 -->
    <div
      v-if="selectedEdgeData"
      class="detail-panel edge-panel"
      :style="{ transform: `translate(${intelligentEdgePanelPosition.x}px, ${intelligentEdgePanelPosition.y}px)` }"
      @mousedown="startDragPanel('edge', $event)"
    >
      <div class="detail-header">
        <div class="panel-type-indicator edge-indicator"></div>
        <h4>边: {{ getEdgeDisplayName(selectedEdgeData) }}</h4>
        <a-button type="text" size="small" @click="clearSelection">
          <CloseOutlined />
        </a-button>
      </div>
      <div class="detail-content">
        <div class="detail-item">
          <span class="detail-label">ID:</span>
          <span class="detail-value">{{ selectedEdgeData.id }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">源节点:</span>
          <span class="detail-value">{{ selectedEdgeData.source }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">目标节点:</span>
          <span class="detail-value">{{ selectedEdgeData.target }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">类型:</span>
          <span class="detail-value">{{ selectedEdgeData.type || 'DIRECTED' }}</span>
        </div>
        <div v-if="selectedEdgeData.properties?.weight" class="detail-item">
          <span class="detail-label">权重:</span>
          <span class="detail-value">{{ selectedEdgeData.properties.weight }}</span>
        </div>
        <div v-if="selectedEdgeData.properties?.keywords" class="detail-item">
          <span class="detail-label">关键词:</span>
          <span class="detail-value">{{ selectedEdgeData.properties.keywords }}</span>
        </div>
        <div v-if="selectedEdgeData.properties?.description" class="detail-item">
          <span class="detail-label">描述:</span>
          <span class="detail-value">{{ selectedEdgeData.properties.description }}</span>
        </div>
      </div>
    </div>

    <div class="legend" v-if="entityTypes.length > 0">
      <div class="legend-header">
        <h4>实体类型</h4>
      </div>
      <div class="legend-content">
        <div class="legend-item" v-for="type in entityTypes" :key="type.type">
          <div
            class="legend-color"
            :style="{ backgroundColor: getEntityColor(type.type) }"
          ></div>
          <span>{{ type.type }} ({{ type.count }})</span>
        </div>
      </div>
    </div>

    <!-- 控制按钮 (简化版) -->
    <div class="graph-controls">
      <div class="control-group">
        <a-button @click="zoomIn" size="small" type="text" class="control-btn">
          <PlusOutlined />
        </a-button>
        <a-button @click="zoomOut" size="small" type="text" class="control-btn">
          <MinusOutlined />
        </a-button>
        <a-button @click="resetCamera" size="small" type="text" class="control-btn" title="重置视图">
          <HomeOutlined />
        </a-button>
      </div>
    </div>

    <!-- 加载遮罩 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-content">
        <a-spin size="large" />
        <p>{{ loadingMessage }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import {
  SearchOutlined,
  ReloadOutlined,
  ClearOutlined,
  CloseOutlined,
  PlusOutlined,
  MinusOutlined,
  HomeOutlined
} from '@ant-design/icons-vue'
import Sigma from 'sigma'
import { NodeBorderProgram } from '@sigma/node-border'
import EdgeCurveProgram, { EdgeCurvedArrowProgram } from '@sigma/edge-curve'
import { EdgeArrowProgram } from 'sigma/rendering'

import { lightragApi } from '@/apis/graph_api'
import { useGraphStore } from '@/stores/graphStore'
import '@/assets/css/sigma.css'

// 定义 props
const props = defineProps({
  initialDatabaseId: {
    type: String,
    default: ''
  },
  hideDbSelector: {
    type: Boolean,
    default: false
  },
  hideStats: {
    type: Boolean,
    default: false
  },
  hideControls: {
    type: Boolean,
    default: false
  },
  initialLimit: {
    type: Number,
    default: 200
  },
  initialDepth: {
    type: Number,
    default: 2
  }
})

// 定义 emits
const emit = defineEmits(['update:stats', 'refresh-graph', 'clear-graph'])

// 状态管理
const graphStore = useGraphStore()

// 响应式引用
const loading = ref(false)
const loadingDatabases = ref(false)
const loadingLabels = ref(false)
const expanding = ref(false)
const sigmaContainer = ref(null)
const layoutRunning = ref(false)
const loadingMessage = ref('加载图数据中...')

// 面板拖拽相关
const nodePanelPosition = ref({ x: 12, y: 60 })
const edgePanelPosition = ref({ x: 12, y: 150 }) // 降低初始Y位置以适应紧凑模式
const dragging = ref({ active: false, type: '', startX: 0, startY: 0, initialX: 0, initialY: 0 })

// 数据库相关状态
const selectedDatabase = ref('')
const availableDatabases = ref([])
const selectedLabel = ref('*')
const availableLabels = ref([])

// Sigma实例
let sigmaInstance = null
let layoutWorker = null

// 搜索和筛选参数
const searchParams = reactive({
  max_nodes: props.initialLimit,
  max_depth: props.initialDepth
})

// 计算属性
const entityTypes = computed(() => graphStore.entityTypes)
const stats = computed(() => graphStore.stats)
const selectedNodeData = computed(() => graphStore.selectedNodeData)
const selectedEdgeData = computed(() => graphStore.selectedEdgeData)

// 智能边面板位置 - 确保在紧凑模式下也能正确显示
const intelligentEdgePanelPosition = computed(() => {
  if (!sigmaContainer.value) return edgePanelPosition.value
  
  const containerHeight = sigmaContainer.value.clientHeight
  const panelHeight = 200 // 估计的面板高度
  const nodePanelBottom = selectedNodeData.value ? nodePanelPosition.value.y + 200 : 0
  
  // 如果有节点面板显示，将边面板放在节点面板下方
  if (selectedNodeData.value) {
    return {
      x: edgePanelPosition.value.x + 260, // 在节点面板右侧
      y: Math.min(nodePanelPosition.value.y, containerHeight - panelHeight - 20)
    }
  }
  
  // 确保边面板在容器范围内
  return {
    x: edgePanelPosition.value.x,
    y: Math.min(edgePanelPosition.value.y, Math.max(60, containerHeight - panelHeight - 20))
  }
})

// 获取节点显示名称
const getNodeDisplayName = (node) => {
  if (node.properties?.entity_id) {
    return node.properties.entity_id
  }
  if (node.labels && node.labels.length > 0) {
    return node.labels[0]
  }
  return node.id || 'Unknown'
}

// 获取边显示名称
const getEdgeDisplayName = (edge) => {
  if (edge.properties?.keywords) {
    return edge.properties.keywords
  }
  if (edge.properties?.description) {
    return edge.properties.description.substring(0, 20) + '...'
  }
  return `${edge.source} -> ${edge.target}`
}

// 加载可用数据库
const loadAvailableDatabases = async () => {
  // 如果隐藏数据库选择器且有初始数据库ID，直接使用
  if (props.hideDbSelector && props.initialDatabaseId) {
    selectedDatabase.value = props.initialDatabaseId
    await loadGraphLabels(selectedDatabase.value)
    return
  }

  loadingDatabases.value = true
  try {
    const response = await lightragApi.getDatabases()
    if (response.success) {
      availableDatabases.value = response.data.databases || []

      // 如果有初始数据库 ID，优先选择它
      if (props.initialDatabaseId && availableDatabases.value.some(db => db.db_id === props.initialDatabaseId)) {
        selectedDatabase.value = props.initialDatabaseId
        await onDatabaseChange(selectedDatabase.value)
      } else if (availableDatabases.value.length > 0 && !selectedDatabase.value) {
        selectedDatabase.value = availableDatabases.value[0].db_id
        await onDatabaseChange(selectedDatabase.value)
      }
    }
  } catch (error) {
    console.error('加载数据库列表失败:', error)
    message.error('加载数据库列表失败: ' + error.message)
  } finally {
    loadingDatabases.value = false
  }
}

// 加载图标签
const loadGraphLabels = async (dbId) => {
  if (!dbId) return

  loadingLabels.value = true
  try {
    const response = await lightragApi.getLabels(dbId)
    if (response.success) {
      availableLabels.value = response.data.labels || []
    }
  } catch (error) {
    console.error('加载图标签失败:', error)
    availableLabels.value = []
  } finally {
    loadingLabels.value = false
  }
}

// 数据库切换处理
const onDatabaseChange = async (dbId) => {
  if (!dbId) return

  selectedDatabase.value = dbId
  selectedLabel.value = '*'

  // 清空当前图谱
  clearGraph()

  // 加载新数据库的标签
  await loadGraphLabels(dbId)

  message.info(`已切换到数据库: ${availableDatabases.value.find(db => db.db_id === dbId)?.name || dbId}`)
}

// Sigma.js配置
const sigmaSettings = {
  allowInvalidContainer: true,
  defaultNodeType: 'default',
  defaultEdgeType: 'curvedArrow',
  renderEdgeLabels: true,
  renderLabels: true,
  enableEdgeEvents: true,
  // 添加 passive event listener 配置以解决警告
  enableCameraAPI: true,
  touchActions: 'pan-y pinch-zoom',
  eventBubbling: false,
  edgeProgramClasses: {
    arrow: EdgeArrowProgram,
    curvedArrow: EdgeCurvedArrowProgram,
    curved: EdgeCurveProgram
  },
  nodeProgramClasses: {
    default: NodeBorderProgram
  },
  labelSize: 12,
  edgeLabelSize: 10,
  labelColor: {
    color: '#000'
  },
  edgeLabelColor: {
    color: '#666'
  },
  minEdgeThickness: 4, // 增加最小边厚度，提高点击性
  maxEdgeThickness: 10, // 增加最大边厚度
  // 添加边点击相关配置
  edgeClickTolerance: 15, // 增加边点击容差，增加点击检测区域
  edgeHoverTolerance: 12,  // 增加边悬停容差
  zoomToSizeRatioFunction: (x) => x, // 确保缩放时边的厚度保持合理
  eventListenerOptions: {
    wheel: { passive: true },
    touchstart: { passive: true },
  },
}

// 初始化Sigma.js
const initSigma = async () => {
  if (!sigmaContainer.value || sigmaInstance) return

  try {
    sigmaInstance = new Sigma(
      graphStore.sigmaGraph || graphStore.createSigmaGraph({ nodes: [], edges: [] }),
      sigmaContainer.value,
      sigmaSettings
    )

    // 保存实例到状态管理
    graphStore.setSigmaInstance(sigmaInstance)

    // 注册事件监听器
    registerEvents()

    console.log('Sigma.js 实例创建成功')
  } catch (error) {
    console.error('初始化Sigma.js失败:', error)
    message.error('图可视化初始化失败')
  }
}

// 拖拽状态
const isDragging = ref(false)
let draggedNode = null

// 注册事件监听器
const registerEvents = () => {
  if (!sigmaInstance) return

  // 节点点击事件
  sigmaInstance.on('clickNode', ({ node }) => {
    try {
      const graph = sigmaInstance.getGraph()
      if (graph.hasNode(node)) {
        console.log('Clicked node:', node)

        // 立即设置选中节点，显示详情面板
        graphStore.setSelectedNode(node, false) // 先不移动相机

        // 获取节点数据并确保设置成功
        const nodeData = graph.getNodeAttributes(node)
        console.log('Node data:', nodeData)

        // 延迟一点后再移动相机，确保详情面板已显示
        setTimeout(() => {
          if (graphStore.selectedNode === node) {
            graphStore.moveToSelectedNode = true
            graphStore.setSelectedNode(node, true) // 现在移动相机
          }
        }, 100)

      } else {
        console.warn('Clicked node does not exist in graph:', node)
      }
    } catch (error) {
      console.error('Error handling node click:', error)
    }
  })

  // 节点悬停事件
  sigmaInstance.on('enterNode', ({ node }) => {
    if (!isDragging.value) {
      try {
        const graph = sigmaInstance.getGraph()
        if (graph.hasNode(node)) {
          graphStore.setFocusedNode(node)
        }
      } catch (error) {
        console.error('Error handling node enter:', error)
      }
    }
  })

  sigmaInstance.on('leaveNode', () => {
    if (!isDragging.value) {
      graphStore.setFocusedNode(null)
    }
  })

  // 边点击事件
  sigmaInstance.on('clickEdge', ({ edge }) => {
    try {
      console.log('边被点击 - Sigma边ID:', edge)
      const graph = sigmaInstance.getGraph()
      if (graph.hasEdge(edge)) {
        // 获取Sigma边的属性，其中包含原始数据
        const sigmaEdgeData = graph.getEdgeAttributes(edge)
        console.log('Sigma边属性:', sigmaEdgeData)
        
        // 立即设置选中的边 - 使用Sigma边ID
        graphStore.setSelectedEdge(edge)
        
        // 确保边面板显示
        nextTick(() => {
          if (selectedEdgeData.value) {
            console.log('边面板应该显示:', selectedEdgeData.value)
            message.success(`已选中边: ${getEdgeDisplayName(selectedEdgeData.value)}`)
          } else {
            console.warn('selectedEdgeData为空，尝试使用Sigma边数据')
            // 如果无法从rawGraph中找到，直接使用Sigma边的原始数据
            const fallbackData = sigmaEdgeData.originalData || {
              id: edge,
              source: graph.source(edge),
              target: graph.target(edge),
              properties: {
                keywords: sigmaEdgeData.label || '',
                description: sigmaEdgeData.label || '',
                weight: sigmaEdgeData.originalWeight || 1
              }
            }
            console.log('使用回退边数据:', fallbackData)
            message.success(`已选中边: ${getEdgeDisplayName(fallbackData)}`)
          }
        })
      } else {
        console.warn('点击的边不存在于图中:', edge)
        message.warning('点击的边不存在于图中')
      }
    } catch (error) {
      console.error('处理边点击事件时出错:', error)
      message.error('处理边点击事件时出错')
    }
  })

  // 添加边悬停事件以提高交互体验
  sigmaInstance.on('enterEdge', ({ edge }) => {
    if (!isDragging.value) {
      try {
        const graph = sigmaInstance.getGraph()
        if (graph.hasEdge(edge)) {
          // 高亮悬停的边
          graph.setEdgeAttribute(edge, 'color', '#ff0000')
          graph.setEdgeAttribute(edge, 'size', (graph.getEdgeAttribute(edge, 'size') || 1) * 1.5)
          sigmaInstance.refresh()
          console.log('悬停在边上:', edge)
        }
      } catch (error) {
        console.error('处理边悬停事件时出错:', error)
      }
    }
  })

  sigmaInstance.on('leaveEdge', ({ edge }) => {
    if (!isDragging.value) {
      try {
        const graph = sigmaInstance.getGraph()
        if (graph.hasEdge(edge)) {
          // 恢复边的原始样式
          const originalData = graph.getEdgeAttribute(edge, 'originalData')
          graph.setEdgeAttribute(edge, 'color', originalData?.color || '#666')
          graph.setEdgeAttribute(edge, 'size', originalData?.size || 1)
          sigmaInstance.refresh()
        }
      } catch (error) {
        console.error('处理边离开事件时出错:', error)
      }
    }
  })

  // 画布点击事件
  sigmaInstance.on('clickStage', () => {
    graphStore.clearSelection()
  })

  // 拖拽支持
  sigmaInstance.on('downNode', (e) => {
    isDragging.value = true
    draggedNode = e.node

    // 高亮拖拽节点
    const graph = sigmaInstance.getGraph()
    graph.setNodeAttribute(draggedNode, 'highlighted', true)

    // 停止布局
    if (layoutWorker) {
      layoutWorker.stop()
    }
  })

  sigmaInstance.getMouseCaptor().on('mousemovebody', (e) => {
    if (!isDragging.value || !draggedNode) return

    // 获取新位置
    const pos = sigmaInstance.viewportToGraph(e)

    // 更新节点位置
    const graph = sigmaInstance.getGraph()
    graph.setNodeAttribute(draggedNode, 'x', pos.x)
    graph.setNodeAttribute(draggedNode, 'y', pos.y)

    // 阻止默认行为
    e.preventSigmaDefault()
    e.original.preventDefault()
    e.original.stopPropagation()
  })

  sigmaInstance.getMouseCaptor().on('mouseup', () => {
    if (draggedNode) {
      const graph = sigmaInstance.getGraph()
      graph.removeNodeAttribute(draggedNode, 'highlighted')
    }
    isDragging.value = false
    draggedNode = null
  })
}

// 加载图数据
const loadGraphData = async () => {
  if (!selectedDatabase.value) {
    message.warning('请先选择数据库')
    return
  }

  loading.value = true
  loadingMessage.value = '加载图数据中...'
  graphStore.setIsFetching(true)

  try {
    const [graphResponse, statsResponse] = await Promise.all([
      lightragApi.getSubgraph({
        db_id: selectedDatabase.value,
        node_label: selectedLabel.value || '*',
        max_depth: searchParams.max_depth,
        max_nodes: searchParams.max_nodes
      }),
      lightragApi.getStats(selectedDatabase.value)
    ])

    if (graphResponse.success && statsResponse.success) {
      // 设置实体类型
      graphStore.setEntityTypes(statsResponse.data.entity_types || [])

      // 创建图数据
      const rawGraph = graphStore.createGraphFromApiData(
        graphResponse.data.nodes,
        graphResponse.data.edges
      )

      // 设置图数据
      graphStore.setRawGraph(rawGraph)
      graphStore.stats = {
        displayed_nodes: graphResponse.data.nodes.length,
        displayed_edges: graphResponse.data.edges.length,
        is_truncated: graphResponse.data.is_truncated
      }

      console.log('Raw graph created:', {
        nodes: rawGraph.nodes.length,
        edges: rawGraph.edges.length,
        sampleNode: rawGraph.nodes[0],
        sampleEdge: rawGraph.edges[0]
      })

      // 创建Sigma图
      const sigmaGraph = graphStore.createSigmaGraph(rawGraph)
      graphStore.setSigmaGraph(sigmaGraph)

      // 应用布局
      await applyLayout(sigmaGraph)

      // 更新Sigma实例
      if (sigmaInstance) {
        sigmaInstance.setGraph(sigmaGraph)
        sigmaInstance.refresh()
      } else {
        await nextTick()
        await initSigma()
      }

      // message.success(`加载成功：${rawGraph.nodes.length} 个节点，${rawGraph.edges.length} 条边${graphResponse.data.is_truncated ? ' (已截断)' : ''}`)
    }
  } catch (error) {
    console.error('加载图数据失败:', error)
    message.error('加载图数据失败: ' + error.message)
  } finally {
    loading.value = false
    loadingMessage.value = '加载图数据中...'
    graphStore.setIsFetching(false)
  }
}

// 加载完整图数据
const loadFullGraph = async () => {
  selectedLabel.value = '*'
  await loadGraphData()
  emit('refresh-graph')
}

// 清空图谱
const clearGraph = () => {
  if (sigmaInstance) {
    const emptyGraph = graphStore.createSigmaGraph({ nodes: [], edges: [] })
    sigmaInstance.setGraph(emptyGraph)
    sigmaInstance.refresh()
  }
  graphStore.reset()
  emit('clear-graph')
}

// 应用布局算法
const applyLayout = async (graph) => {
  return new Promise((resolve) => {
    if (!graph || graph.order === 0) {
      resolve()
      return
    }

    loadingMessage.value = '计算布局中...'

    // 简单的力导向布局
    const nodes = graph.nodes()
    const edges = graph.edges()

    // 随机初始位置
    nodes.forEach((node) => {
      if (!graph.hasNodeAttribute(node, 'x')) {
        graph.setNodeAttribute(node, 'x', Math.random() * 1000)
      }
      if (!graph.hasNodeAttribute(node, 'y')) {
        graph.setNodeAttribute(node, 'y', Math.random() * 1000)
      }
    })

    // 简单的力导向迭代
    const iterations = 100
    for (let i = 0; i < iterations; i++) {
      // 斥力
      for (let j = 0; j < nodes.length; j++) {
        for (let k = j + 1; k < nodes.length; k++) {
          const node1 = nodes[j]
          const node2 = nodes[k]

          const x1 = graph.getNodeAttribute(node1, 'x')
          const y1 = graph.getNodeAttribute(node1, 'y')
          const x2 = graph.getNodeAttribute(node2, 'x')
          const y2 = graph.getNodeAttribute(node2, 'y')

          const dx = x2 - x1
          const dy = y2 - y1
          const distance = Math.sqrt(dx * dx + dy * dy) || 1

          const force = 1000 / (distance * distance)
          const fx = (dx / distance) * force
          const fy = (dy / distance) * force

          graph.setNodeAttribute(node1, 'x', x1 - fx)
          graph.setNodeAttribute(node1, 'y', y1 - fy)
          graph.setNodeAttribute(node2, 'x', x2 + fx)
          graph.setNodeAttribute(node2, 'y', y2 + fy)
        }
      }

      // 引力
      edges.forEach((edge) => {
        const source = graph.source(edge)
        const target = graph.target(edge)

        const x1 = graph.getNodeAttribute(source, 'x')
        const y1 = graph.getNodeAttribute(source, 'y')
        const x2 = graph.getNodeAttribute(target, 'x')
        const y2 = graph.getNodeAttribute(target, 'y')

        const dx = x2 - x1
        const dy = y2 - y1
        const distance = Math.sqrt(dx * dx + dy * dy) || 1

        const force = distance * 0.01
        const fx = (dx / distance) * force
        const fy = (dy / distance) * force

        graph.setNodeAttribute(source, 'x', x1 + fx)
        graph.setNodeAttribute(source, 'y', y1 + fy)
        graph.setNodeAttribute(target, 'x', x2 - fx)
        graph.setNodeAttribute(target, 'y', y2 - fy)
      })
    }

    resolve()
  })
}

// 展开节点
const expandNode = async (nodeId) => {
  if (!selectedDatabase.value) {
    message.warning('请先选择数据库')
    return
  }

  expanding.value = true
  try {
    const response = await lightragApi.getSubgraph({
      db_id: selectedDatabase.value,
      node_label: nodeId,
      max_depth: 1,
      max_nodes: 50
    })

    if (response.success) {
      // 合并新数据的逻辑
      const existingNodeIds = new Set(graphStore.rawGraph.nodes.map(n => n.id))
      const existingEdgeIds = new Set(graphStore.rawGraph.edges.map(e => e.id))

      const newNodes = response.data.nodes.filter(node => !existingNodeIds.has(node.id))
      const newEdges = response.data.edges.filter(edge => !existingEdgeIds.has(edge.id))

      if (newNodes.length > 0 || newEdges.length > 0) {
        // 重新创建图数据
        const allNodes = [...graphStore.rawGraph.nodes, ...newNodes]
        const allEdges = [...graphStore.rawGraph.edges, ...newEdges]

        const rawGraph = graphStore.createGraphFromApiData(allNodes, allEdges)
        graphStore.setRawGraph(rawGraph)

        const sigmaGraph = graphStore.createSigmaGraph(rawGraph)
        graphStore.setSigmaGraph(sigmaGraph)

        if (sigmaInstance) {
          sigmaInstance.setGraph(sigmaGraph)
          sigmaInstance.refresh()
        }

        message.success(`展开成功：新增 ${newNodes.length} 个节点，${newEdges.length} 条边`)
      } else {
        message.info('没有新的相邻节点')
      }
    }
  } catch (error) {
    console.error('展开节点失败:', error)
    message.error('展开节点失败: ' + error.message)
  } finally {
    expanding.value = false
  }
}

// 控制方法
const zoomIn = () => {
  if (sigmaInstance) {
    const camera = sigmaInstance.getCamera()
    camera.animatedZoom({ duration: 200 })
  }
}

const zoomOut = () => {
  if (sigmaInstance) {
    const camera = sigmaInstance.getCamera()
    camera.animatedUnzoom({ duration: 200 })
  }
}

const resetCamera = () => {
  if (sigmaInstance) {
    try {
      const camera = sigmaInstance.getCamera()
      const graph = sigmaInstance.getGraph()

      // 如果图为空，直接重置
      if (graph.order === 0) {
        camera.animatedReset({ duration: 500 })
        return
      }

      // 计算图的边界以确保所有节点都可见
      const nodes = graph.nodes()
      if (nodes.length > 0) {
        const bounds = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity }

        nodes.forEach(node => {
          const attrs = graph.getNodeAttributes(node)
          if (typeof attrs.x === 'number' && typeof attrs.y === 'number') {
            bounds.minX = Math.min(bounds.minX, attrs.x)
            bounds.maxX = Math.max(bounds.maxX, attrs.x)
            bounds.minY = Math.min(bounds.minY, attrs.y)
            bounds.maxY = Math.max(bounds.maxY, attrs.y)
          }
        })

        // 只有在边界有效时才使用fitBounds
        if (isFinite(bounds.minX) && isFinite(bounds.maxX) && isFinite(bounds.minY) && isFinite(bounds.maxY)) {
          const centerX = (bounds.minX + bounds.maxX) / 2
          const centerY = (bounds.minY + bounds.maxY) / 2
          const padding = 50

          camera.animate({
            x: centerX,
            y: centerY,
            ratio: Math.max(
              (bounds.maxX - bounds.minX + padding) / window.innerWidth,
              (bounds.maxY - bounds.minY + padding) / window.innerHeight
            ) || 1.0
          }, { duration: 500 })
        } else {
          // 回退到默认重置
          camera.animatedReset({ duration: 500 })
        }
      } else {
        camera.animatedReset({ duration: 500 })
      }

      console.log('Camera reset completed')
      message.success('视图已重置')
    } catch (error) {
      console.error('Error resetting camera:', error)
      // 强制重置
      if (sigmaInstance) {
        const camera = sigmaInstance.getCamera()
        camera.setState({ x: 0, y: 0, ratio: 1.0 })
        sigmaInstance.refresh()
      }
      message.info('视图已强制重置')
    }
  }
}

const toggleLayout = () => {
  // 简单的布局切换
  layoutRunning.value = !layoutRunning.value
  if (layoutRunning.value && sigmaInstance) {
    applyLayout(sigmaInstance.getGraph())
  }
}

const clearSelection = () => {
  graphStore.clearSelection()
}

const getEntityColor = (entityType) => {
  return graphStore.getEntityColor(entityType)
}

// 面板拖拽功能
const startDragPanel = (type, event) => {
  event.preventDefault()

  if (!sigmaContainer.value) return

  const currentPosition = type === 'node' ? nodePanelPosition.value : edgePanelPosition.value

  // 获取容器位置，计算相对于容器的鼠标位置
  const containerRect = sigmaContainer.value.getBoundingClientRect()
  const relativeX = event.clientX - containerRect.left
  const relativeY = event.clientY - containerRect.top

  dragging.value = {
    active: true,
    type: type,
    startX: relativeX,
    startY: relativeY,
    initialX: currentPosition.x,
    initialY: currentPosition.y
  }

  document.addEventListener('mousemove', onDragPanel)
  document.addEventListener('mouseup', stopDragPanel)
}

const onDragPanel = (event) => {
  if (!dragging.value.active || !sigmaContainer.value) return

  // 获取容器位置和尺寸
  const containerRect = sigmaContainer.value.getBoundingClientRect()

  // 计算当前鼠标相对于容器的位置
  const currentRelativeX = event.clientX - containerRect.left
  const currentRelativeY = event.clientY - containerRect.top

  // 计算拖拽偏移
  const deltaX = currentRelativeX - dragging.value.startX
  const deltaY = currentRelativeY - dragging.value.startY

  const maxX = containerRect.width - 260  // 面板宽度为240px + 一些边距
  const maxY = containerRect.height - 200 // 面板高度约为200px

  const newPosition = {
    x: Math.max(0, Math.min(maxX, dragging.value.initialX + deltaX)),
    y: Math.max(0, Math.min(maxY, dragging.value.initialY + deltaY))
  }

  if (dragging.value.type === 'node') {
    nodePanelPosition.value = newPosition
  } else {
    edgePanelPosition.value = newPosition
  }
}

const stopDragPanel = () => {
  dragging.value.active = false
  document.removeEventListener('mousemove', onDragPanel)
  document.removeEventListener('mouseup', stopDragPanel)
}

// 生命周期
onMounted(async () => {
  await nextTick()
  await loadAvailableDatabases()
})

onUnmounted(() => {
  // 清理拖拽事件监听器
  document.removeEventListener('mousemove', onDragPanel)
  document.removeEventListener('mouseup', stopDragPanel)

  if (sigmaInstance) {
    sigmaInstance.kill()
    sigmaInstance = null
  }
  if (layoutWorker) {
    layoutWorker.stop()
  }
  graphStore.reset()
})

// 监听选中节点数据变化，用于调试
watch(() => graphStore.selectedNodeData, (nodeData) => {
  console.log('Selected node data changed:', nodeData)
})

// 监听选中边数据变化，用于调试和确保面板显示
watch(() => graphStore.selectedEdgeData, (edgeData) => {
  console.log('Selected edge data changed:', edgeData)
  if (edgeData) {
    console.log('边面板应该显示，当前位置:', intelligentEdgePanelPosition.value)
  }
})

// 监听选中节点变化，移动相机
watch(() => graphStore.selectedNode, (nodeId) => {
  if (nodeId && graphStore.moveToSelectedNode && sigmaInstance) {
    try {
      const graph = sigmaInstance.getGraph()

      // 检查节点是否存在
      if (!graph.hasNode(nodeId)) {
        console.warn('Selected node does not exist in graph:', nodeId)
        graphStore.moveToSelectedNode = false
        return
      }

      const nodeAttributes = graph.getNodeAttributes(nodeId)

      // 检查节点属性是否有效
      if (!nodeAttributes || typeof nodeAttributes.x !== 'number' || typeof nodeAttributes.y !== 'number') {
        console.warn('Invalid node attributes for node:', nodeId, nodeAttributes)
        graphStore.moveToSelectedNode = false
        return
      }

      const camera = sigmaInstance.getCamera()
      const currentState = camera.getState()

      console.log('Moving camera to node:', nodeId, {
        x: nodeAttributes.x,
        y: nodeAttributes.y,
        currentRatio: currentState.ratio
      })

      // 计算合适的缩放比例，避免过度缩放
      const currentRatio = currentState.ratio || 1.0
      const targetRatio = Math.max(0.1, Math.min(currentRatio * 0.7, 0.6))

      // 验证节点位置是否有效
      const isValidPosition = (
        typeof nodeAttributes.x === 'number' &&
        typeof nodeAttributes.y === 'number' &&
        !isNaN(nodeAttributes.x) &&
        !isNaN(nodeAttributes.y) &&
        isFinite(nodeAttributes.x) &&
        isFinite(nodeAttributes.y)
      )

      if (!isValidPosition) {
        console.warn('Invalid node position, skipping camera movement:', nodeAttributes)
        return
      }

      // 移动相机到节点位置，使用安全的缩放比例
      camera.animate(
        {
          x: nodeAttributes.x,
          y: nodeAttributes.y,
          ratio: targetRatio  // 使用计算出的安全缩放比例
        },
        {
          duration: 600  // 适中的动画时间
        }
      )
    } catch (error) {
      console.error('Error moving camera to selected node:', error)
      // 如果相机移动失败，至少确保显示节点详情
      if (nodeId) {
        const graph = sigmaInstance.getGraph()
        if (graph.hasNode(nodeId)) {
          const nodeData = graph.getNodeAttributes(nodeId)
          console.log('Fallback: showing node details without camera movement', nodeData)
        }
      }
    } finally {
      // 确保重置标志
      graphStore.moveToSelectedNode = false
    }
      }
  })

// 监听统计数据变化，通知父组件
watch(stats, (newStats) => {
  emit('update:stats', newStats)
}, { deep: true, immediate: true })

// 暴露给父组件的方法
defineExpose({
  loadFullGraph,
  clearGraph
})
</script>

<style lang="less" scoped>
.knowledge-graph-viewer {
  position: relative;
  width: 100%;
  // height: 100vh;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

.control-panel {
  background: white;
  padding: 8px 0; /* Reduced from 16px */
  border-bottom: none;
  display: flex;
  gap: 12px; /* Reduced from 16px */
  align-items: center;
  flex-wrap: wrap;
  z-index: 1000;
}

.database-section,
.search-section,
.filter-section,
.stats-section {
  display: flex;
  align-items: center;
  gap: 6px; /* Reduced from 8px */
}

.stats-section {
  margin-left: auto;
}

.sigma-container {
  flex: 1;
  background: white;
  position: relative; /* 确保子元素可以相对于此容器定位 */
  border: 1px solid var(--main-20);
  border-radius: 8px;
  overflow: hidden;

  &.loading {
    pointer-events: none;
  }
}

.detail-panel {
  position: absolute;
  width: 240px; /* Reduced from 300px */
  background: white;
  border: 1px solid #e8e8e8;
  border-radius: 6px; /* Reduced from 8px */
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.08); /* Reduced shadow */
  transition: box-shadow 0.2s ease;
  cursor: move;
  z-index: 1000;

  &:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12); /* Reduced shadow */
  }

  &.node-panel {
    border-left: 4px solid #52c41a; // 绿色边框标识节点面板
  }

  &.edge-panel {
    border-left: 4px solid #1890ff; // 蓝色边框标识边面板
  }
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 6px; /* Reduced from 8px */
  padding: 8px 12px; /* Reduced from 12px 16px */
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
  border-radius: 6px 6px 0 0; /* Reduced from 8px */

  h4 {
    margin: 0;
    font-size: 12px; /* Reduced from 14px */
    font-weight: 600;
    flex: 1;
    color: #262626;
  }
}

.panel-type-indicator {
  width: 6px; /* Reduced from 8px */
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;

  &.node-indicator {
    background: #52c41a;
  }

  &.edge-indicator {
    background: #1890ff;
  }
}

.detail-content {
  padding: 10px; /* Reduced from 16px */
  max-height: 300px; /* Reduced from 400px */
  overflow-y: auto;
}

.detail-item {
  display: flex;
  margin-bottom: 8px; /* Reduced from 12px */

  &:last-child {
    margin-bottom: 0;
  }
}

.detail-label {
  min-width: 50px; /* Reduced from 60px */
  font-weight: 600;
  color: #595959;
  font-size: 11px; /* Reduced from 12px */
  flex-shrink: 0;
}

.detail-value {
  color: #262626;
  font-size: 11px; /* Reduced from 12px */
  word-break: break-word;
  line-height: 1.3; /* Reduced from 1.4 */
}

.detail-actions {
  margin-top: 12px; /* Reduced from 16px */
  padding-top: 8px; /* Reduced from 12px */
  border-top: 1px solid #f0f0f0;
}

.graph-controls {
  position: absolute;
  bottom: 16px; /* Reduced from 20px */
  right: 16px;
  z-index: 1000;
}

.control-group {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(8px);
  border: 2px solid white;
  border-radius: 16px; /* Reduced from 20px */
  padding: 2px; /* Reduced from 4px */
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); /* Reduced shadow */
  display: flex;
  gap: 1px; /* Reduced from 2px */
}

.control-btn {
  width: 28px; /* Reduced from 32px */
  height: 28px;
  border-radius: 14px; /* Reduced from 16px */
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #595959;
  transition: all 0.2s ease;

  &:hover {
    background: color-mix(in srgb, var(--main-color) 10%, transparent);
    color: var(--main-color);
  }
}

.legend {
  position: absolute;
  right: 12px; /* Reduced from 16px */
  top: 60px; /* Reduced from 80px */
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(8px);
  border: 2px solid white;
  border-radius: 6px; /* Reduced from 8px */
  width: 150px; /* Reduced from 180px */
  max-height: 250px; /* Reduced from 300px */
  z-index: 1000;
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.08); /* Reduced shadow */
  overflow: hidden;
}

.legend-header {
  background: #fafafa;
  padding: 6px 10px; /* Reduced from 8px 12px */
  border-bottom: 1px solid #f0f0f0;

  h4 {
    margin: 0;
    font-size: 12px; /* Reduced from 13px */
    font-weight: 600;
    color: #262626;
  }
}

.legend-content {
  padding: 6px 10px; /* Reduced from 8px 12px */
  max-height: 200px; /* Reduced from 240px */
  overflow-y: auto;
  overflow-x: hidden;

  /* 自定义滚动条样式 */
  &::-webkit-scrollbar {
    width: 3px; /* Reduced from 4px */
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: #d9d9d9;
    border-radius: 2px;

    &:hover {
      background: #bfbfbf;
    }
  }
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px; /* Reduced from 8px */
  padding: 2px 4px; /* Reduced from 4px 6px */
  margin: 1px 0; /* Reduced from 2px */
  border-radius: 3px; /* Reduced from 4px */
  font-size: 11px; /* Reduced from 12px */
  min-width: 0;
  transition: background-color 0.2s ease;

  span {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
    color: #595959;
  }

  &:hover {
    background-color: #f5f5f5;
  }
}

.legend-color {
  width: 8px; /* Reduced from 10px */
  height: 8px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.1);
  flex-shrink: 0;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.loading-content {
  text-align: center;

  p {
    margin-top: 12px; /* Reduced from 16px */
    color: #666;
    font-size: 12px; /* Added smaller font size */
  }
}
</style>