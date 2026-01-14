<template>
  <div class="graph-canvas-container" ref="rootEl">
    <div v-show="graphData.nodes.length > 0" class="graph-canvas" ref="container"></div>
    <div class="slots">
      <div v-if="$slots.top" class="overlay top">
        <slot name="top" />
      </div>
      <div class="canvas-content">
        <slot name="content" />
      </div>
      <!-- Statistical Info Panel -->
      <div class="graph-stats-panel" v-if="graphData.nodes.length > 0">
        <div class="stat-item">
          <span class="stat-label">节点</span>
          <span class="stat-value">{{ graphData.nodes.length }}</span>
          <span v-if="graphInfo?.node_count" class="stat-total">/ {{ graphInfo.node_count }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">边</span>
          <span class="stat-value">{{ graphData.edges.length }}</span>
          <span v-if="graphInfo?.edge_count" class="stat-total">/ {{ graphInfo.edge_count }}</span>
        </div>
      </div>
      <div v-if="$slots.bottom" class="overlay bottom">
        <slot name="bottom" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { Graph } from '@antv/g6'
import { onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import { useThemeStore } from '@/stores/theme'

const props = defineProps({
  graphData: {
    type: Object,
    required: true,
    default: () => ({ nodes: [], edges: [] })
  },
  graphInfo: {
    type: Object,
    default: () => ({})
  },
  labelField: { type: String, default: 'name' },
  autoFit: { type: Boolean, default: true },
  autoResize: { type: Boolean, default: true },
  layoutOptions: { type: Object, default: () => ({}) },
  nodeStyleOptions: { type: Object, default: () => ({}) },
  edgeStyleOptions: { type: Object, default: () => ({}) },
  enableFocusNeighbor: { type: Boolean, default: true },
  sizeByDegree: { type: Boolean, default: true },
  highlightKeywords: { type: Array, default: () => [] }
})

const emit = defineEmits(['ready', 'data-rendered', 'node-click', 'edge-click', 'canvas-click'])

const container = ref(null)
const rootEl = ref(null)
const themeStore = useThemeStore()
let graphInstance = null
let resizeObserver = null
let renderTimeout = null
let retryCount = 0
const MAX_RETRIES = 5

const defaultLayout = {
  type: 'd3-force',
  preventOverlap: true,
  alphaDecay: 0.1,
  alphaMin: 0.01,
  velocityDecay: 0.6,
  iterations: 150,
  force: {
    center: { x: 0.5, y: 0.5, strength: 0.1 },
    charge: { strength: -400, distanceMax: 600 },
    link: { distance: 100, strength: 0.8 }
  },
  collide: { radius: 40, strength: 0.8, iterations: 3 }
}

// CSS 变量解析工具函数
function getCSSVariable(variableName, element = document.documentElement) {
  return getComputedStyle(element).getPropertyValue(variableName).trim()
}

function formatData() {
  const data = props.graphData || { nodes: [], edges: [] }
  const degrees = new Map()

  for (const n of data.nodes) {
    degrees.set(String(n.id), 0)
  }
  for (const e of data.edges) {
    const s = String(e.source_id)
    const t = String(e.target_id)
    degrees.set(s, (degrees.get(s) || 0) + 1)
    degrees.set(t, (degrees.get(t) || 0) + 1)
  }

  const nodes = (data.nodes || []).map((n) => ({
    id: String(n.id),
    data: {
      label: n[props.labelField] ?? n.name ?? String(n.id),
      degree: degrees.get(String(n.id)) || 0,
      original: n // 保存原始数据
    }
  }))

  const edges = (data.edges || []).map((e, idx) => ({
    id: e.id ? String(e.id) : `edge-${idx}`,
    source: String(e.source_id),
    target: String(e.target_id),
    data: {
      label: e.type ?? '',
      original: e // 保存原始数据
    }
  }))

  return { nodes, edges }
}

function initGraph() {
  if (!container.value) return

  const width = container.value.offsetWidth
  const height = container.value.offsetHeight

  if (width === 0 && height === 0) {
    if (retryCount < MAX_RETRIES) {
      retryCount++
      clearTimeout(renderTimeout)
      renderTimeout = setTimeout(initGraph, 200)
    }
    return
  }

  retryCount = 0
  container.value.innerHTML = ''

  if (graphInstance) {
    try {
      graphInstance.destroy()
    } catch (e) {}
    graphInstance = null
  }

  graphInstance = new Graph({
    container: container.value,
    width,
    height,
    autoFit: props.autoFit,
    autoResize: props.autoResize,
    layout: { ...defaultLayout, ...props.layoutOptions },
    node: {
      type: 'circle',
      style: {
        labelText: (d) => d.data.label,
        labelFill: getCSSVariable('--gray-700'),
        labelWordWrap: true, // enable label ellipsis
        labelMaxWidth: '300%',
        size: (d) => {
          if (!props.sizeByDegree) return 24
          const deg = d.data.degree || 0
          return Math.min(15 + deg * 5, 50)
        },
        opacity: 0.9,
        stroke: getCSSVariable('--color-bg-container'),
        lineWidth: 1.5,
        shadowColor: getCSSVariable('--gray-400'),
        shadowBlur: 4,
        ...(props.nodeStyleOptions.style || {})
      },
      palette: props.nodeStyleOptions.palette || {
        field: 'label',
        color: [
          '#60a5fa',
          '#34d399',
          '#f59e0b',
          '#f472b6',
          '#22d3ee',
          '#a78bfa',
          '#f97316',
          '#4ade80',
          '#f43f5e',
          '#2dd4bf'
        ]
      }
    },
    edge: {
      type: 'quadratic',
      style: {
        labelText: (d) => d.data.label,
        labelFill: getCSSVariable('--gray-800'),
        labelBackground: true,
        labelBackgroundFill: getCSSVariable('--gray-100'),
        stroke: getCSSVariable('--gray-400'),
        opacity: 0.8,
        lineWidth: 1.2,
        endArrow: true,
        ...(props.edgeStyleOptions.style || {})
      }
    },
    behaviors: [
      'drag-element',
      'zoom-canvas',
      'drag-canvas',
      'hover-activate',
      {
        type: 'click-select',
        degree: 1,
        state: 'selected', // 选中的状态
        neighborState: 'active', // 相邻节点附着状态
        unselectedState: 'inactive', // 未选中节点状态
        multiple: true,
        trigger: ['shift'],
        // 禁用默认的选中效果，避免与自定义事件冲突
        disableDefault: false
      }
    ]
  })

  // 绑定事件
  graphInstance.on('node:click', (evt) => {
    const { target } = evt
    // 获取节点ID
    const nodeId = target.id
    const nodeData = graphInstance.getNodeData(nodeId)
    emit('node-click', nodeData)
  })

  graphInstance.on('edge:click', (evt) => {
    const { target } = evt
    const edgeId = target.id
    const edgeData = graphInstance.getEdgeData(edgeId)
    emit('edge-click', edgeData)
  })

  graphInstance.on('canvas:click', (evt) => {
    // 只有点击画布空白处才触发
    if (!evt.target) {
      emit('canvas-click')
    }
  })

  emit('ready', graphInstance)
}

function setGraphData() {
  if (!graphInstance) initGraph()
  if (!graphInstance) return
  const data = formatData()

  console.log('开始设置图谱数据:', {
    nodes: data.nodes.length,
    edges: data.edges.length
  })

  graphInstance.setData(data)
  graphInstance.render()

  // 手动触发布局重新计算，确保节点分布
  setTimeout(() => {
    try {
      if (graphInstance && graphInstance.layout) {
        graphInstance.layout()
        console.log('触发布局重新计算')
      }
    } catch (error) {
      console.warn('布局重新计算失败:', error)
    }

    // 等待力导向布局稳定后再应用高亮
    setTimeout(() => {
      applyHighlightKeywords()
      emit('data-rendered')
      console.log('图谱渲染完成，布局已稳定')
    }, 1500)
  }, 10) // 等待 10ms 确保布局完成
}

// 关键词高亮功能
function applyHighlightKeywords() {
  if (!graphInstance || !props.highlightKeywords || props.highlightKeywords.length === 0) return

  const { nodes } = graphInstance.getData()
  const updates = {}

  nodes.forEach((node) => {
    const nodeLabel = node.data.label || node.data[props.labelField] || String(node.id)
    const shouldHighlight = props.highlightKeywords.some(
      (keyword) => keyword.trim() !== '' && nodeLabel.toLowerCase().includes(keyword.toLowerCase())
    )

    if (shouldHighlight) {
      updates[node.id] = ['highlighted']
    }
  })

  if (Object.keys(updates).length > 0) {
    graphInstance.setElementState(updates)
    graphInstance.draw()
  }
}

// 清除高亮
function clearHighlights() {
  if (!graphInstance) return

  const { nodes } = graphInstance.getData()
  const updates = {}

  nodes.forEach((node) => {
    updates[node.id] = []
  })

  if (Object.keys(updates).length > 0) {
    graphInstance.setElementState(updates)
    graphInstance.draw()
  }
}

function renderGraph() {
  if (!graphInstance) initGraph()
  setGraphData()
}

function refreshGraph() {
  if (graphInstance) {
    try {
      graphInstance.destroy()
    } catch (e) {}
    graphInstance = null
  }
  if (container.value) container.value.innerHTML = ''
  retryCount = 0
  clearTimeout(renderTimeout)
  renderTimeout = setTimeout(() => {
    renderGraph()
  }, 300)
}

function fitView() {
  if (graphInstance)
    try {
      graphInstance.fitView()
    } catch (_) {}
}
function fitCenter() {
  if (graphInstance)
    try {
      graphInstance.fitCenter()
    } catch (_) {}
}
function getInstance() {
  return graphInstance
}

async function focusNode(id) {
  if (!graphInstance || !props.enableFocusNeighbor) return
  const { nodes, edges } = graphInstance.getData()
  const nodeIds = nodes.map((n) => n.id)
  const edgeIds = edges.map((e) => e.id)
  const updates = {}
  nodeIds.forEach((nid) => (updates[nid] = ['hidden']))
  edgeIds.forEach((eid) => (updates[eid] = ['hidden']))
  const neighborSet = new Set()
  const related = []
  edges.forEach((e) => {
    if (e.source === id) {
      neighborSet.add(e.target)
      related.push(e.id)
    } else if (e.target === id) {
      neighborSet.add(e.source)
      related.push(e.id)
    }
  })
  updates[id] = ['focus']
  Array.from(neighborSet).forEach((nid) => (updates[nid] = ['focus']))
  related.forEach((eid) => (updates[eid] = ['focus']))
  await graphInstance.setElementState(updates)
  await graphInstance.draw()
}

async function clearFocus() {
  if (!graphInstance) return
  const { nodes, edges } = graphInstance.getData()
  const nodeIds = nodes.map((n) => n.id)
  const edgeIds = edges.map((e) => e.id)
  const updates = {}
  nodeIds.forEach((nid) => (updates[nid] = []))
  edgeIds.forEach((eid) => (updates[eid] = []))
  await graphInstance.setElementState(updates)
  await graphInstance.draw()
}

watch(
  () => props.graphData,
  () => {
    clearTimeout(renderTimeout)
    renderTimeout = setTimeout(() => setGraphData(), 50)
  },
  { deep: true }
)

// 监听关键词变化
watch(
  () => props.highlightKeywords,
  () => {
    if (graphInstance) {
      clearHighlights()
      setTimeout(() => applyHighlightKeywords(), 50)
    }
  },
  { deep: true }
)

// 监听主题切换，重新加载图形
watch(
  () => themeStore.isDark,
  () => {
    if (graphInstance) {
      refreshGraph()
    }
  }
)

onMounted(() => {
  // ResizeObserver 监听容器尺寸，自动重渲染
  if (window.ResizeObserver) {
    resizeObserver = new ResizeObserver(() => {
      if (!container.value || !graphInstance) return
      const width = container.value.offsetWidth
      const height = container.value.offsetHeight
      graphInstance.changeSize(width, height)
    })
    if (container.value) resizeObserver.observe(container.value)
  }

  clearTimeout(renderTimeout)
  renderTimeout = setTimeout(() => {
    renderGraph()
  }, 300)

  window.addEventListener('resize', refreshGraph)
})

onUnmounted(() => {
  window.removeEventListener('resize', refreshGraph)
  if (resizeObserver && container.value) resizeObserver.unobserve(container.value)
  clearTimeout(renderTimeout)
  try {
    graphInstance?.destroy()
  } catch (e) {}
  graphInstance = null
})

// 暴露方法
defineExpose({
  refreshGraph,
  fitView,
  fitCenter,
  getInstance,
  focusNode,
  clearFocus,
  setData: setGraphData,
  applyHighlightKeywords,
  clearHighlights
})
</script>

<style lang="less">
.graph-canvas-container {
  position: relative;
  width: 100%;
  height: 100%;
  // background-color: var(--gray-0);

  .graph-canvas {
    width: 100%;
    height: 100%;
  }

  .graph-stats-panel {
    position: absolute;
    bottom: 20px;
    left: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 6px 12px;
    background: var(--color-trans-light);
    border: 1px solid var(--color-border-secondary);
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    pointer-events: auto;
    z-index: 10;
    font-size: 13px;
    backdrop-filter: blur(4px);

    .stat-item {
      display: flex;
      align-items: center;
      gap: 4px;

      .stat-label {
        color: var(--color-text-secondary);
        font-weight: 500;
      }

      .stat-value {
        color: var(--color-text);
        font-weight: 600;
      }

      .stat-total {
        color: var(--color-text-quaternary);
        font-size: 11px;
      }
    }
  }

  .slots {
    // 让整层覆盖容器默认不接收指针事件（便于穿透到底下画布）
    pointer-events: none;
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    z-index: 999;

    .overlay {
      width: 100%;
      flex-shrink: 0;
      flex-grow: 0;
      pointer-events: auto;

      &.top {
        top: 0;
      }
      &.bottom {
        bottom: 0;
      }
    }
    .canvas-content {
      // 中间内容层及其子元素全部穿透
      pointer-events: none;
      flex: 1;
      background: transparent !important;
    }
    .canvas-content * {
      pointer-events: none;
    }
  }
}

/* 高亮节点的脉冲动画效果 */
@keyframes highlightPulse {
  0% {
    filter: brightness(1);
  }
  50% {
    filter: brightness(1.3) drop-shadow(0 0 8px rgba(255, 0, 0, 0.8));
  }
  100% {
    filter: brightness(1);
  }
}

.highlight-animation {
  animation: highlightPulse 2s infinite ease-in-out;
}
</style>
