<template>
  <div class="graph-canvas-container" ref="rootEl">
    <div v-show="graphData.nodes.length > 0" class="graph-canvas" ref="container"></div>
    <div class="slots">
      <div v-if="$slots.top" class="overlay top">
        <slot name="top" />
      </div>
      <div class="content">
        <slot name="content" />
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

const props = defineProps({
  graphData: {
    type: Object,
    required: true,
    default: () => ({ nodes: [], edges: [] })
  },
  labelField: { type: String, default: 'name' },
  autoFit: { type: Boolean, default: true },
  autoResize: { type: Boolean, default: true },
  layoutOptions: { type: Object, default: () => ({}) },
  nodeStyleOptions: { type: Object, default: () => ({}) },
  edgeStyleOptions: { type: Object, default: () => ({}) },
  enableFocusNeighbor: { type: Boolean, default: true },
  sizeByDegree: { type: Boolean, default: true }
})

const emit = defineEmits(['ready', 'node-click', 'edge-click', 'canvas-click', 'data-rendered'])

const container = ref(null)
const rootEl = ref(null)
let graphInstance = null
let resizeObserver = null
let renderTimeout = null
let retryCount = 0
const MAX_RETRIES = 5

const defaultLayout = {
  type: 'd3-force',
  preventOverlap: true,
  // 性能友好参数（参考 GraphView.vue）
  alphaDecay: 0.1,
  alphaMin: 0.01,
  velocityDecay: 0.7,
  iterations: 100,
  force: {
    center: { x: 0.5, y: 0.5, strength: 0.1 },
    charge: { strength: -400, distanceMax: 400 },
    link: { distance: 100, strength: 0.8 },
  },
  collide: { radius: 40, strength: 0.8, iterations: 3 },
}

const paletteColors = [
  '#60a5fa', '#34d399', '#f59e0b', '#f472b6', '#22d3ee',
  '#a78bfa', '#f97316', '#4ade80', '#f43f5e', '#2dd4bf',
]

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
    },
  }))

  const edges = (data.edges || []).map((e, idx) => ({
    id: e.id ? String(e.id) : `edge-${idx}`,
    source: String(e.source_id),
    target: String(e.target_id),
    data: { label: e.type ?? '' },
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
    try { graphInstance.destroy() } catch (e) {}
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
        size: (d) => {
          if (!props.sizeByDegree) return 24
          const deg = d.data.degree || 0
          return Math.min(15 + deg * 5, 50)
        },
        fillOpacity: 0.8,
        opacity: 0.8,
        stroke: '#ffffff',
        lineWidth: 1.5,
        shadowColor: '#94a3b8',
        shadowBlur: 4,
        'label-text-fill': '#334155',
        ...(props.nodeStyleOptions.style || {}),
      },
      palette: props.nodeStyleOptions.palette || {
        field: 'label',
        color: paletteColors,
      },
      state: props.nodeStyleOptions.state || {
        hidden: { opacity: 0.15, 'label-text-opacity': 0 },
        focus: { opacity: 1, stroke: '#2563eb', lineWidth: 2.5, shadowColor: '#60a5fa', shadowBlur: 16 },
      },
    },
    edge: {
      type: 'line',
      style: {
        labelText: (d) => d.data.label,
        labelBackground: '#ffffff',
        stroke: '#94a3b8',
        opacity: 0.6,
        lineWidth: 1.2,
        endArrow: true,
        'label-text-fill': '#334155',
        ...(props.edgeStyleOptions.style || {}),
      },
      state: props.edgeStyleOptions.state || {
        hidden: { opacity: 0.15, 'label-text-opacity': 0 },
        focus: { opacity: 0.95, stroke: '#2563eb', lineWidth: 2, 'label-text-opacity': 1 },
      },
    },
    behaviors: ['drag-element', 'zoom-canvas', 'drag-canvas'],
  })

  bindEvents()
  emit('ready', graphInstance)
}

function bindEvents() {
  if (!graphInstance) return

  const getIds = () => {
    const { nodes, edges } = graphInstance.getData()
    return { nodeIds: nodes.map(n => n.id), edgeIds: edges.map(e => e.id), edges }
  }

  const getClickedId = (e) => e?.id || e?.data?.id || e?.target?.id || null

  let activeNodeId = null

  const resetStyles = async () => {
    const { nodeIds, edgeIds } = getIds()
    const updates = {}
    nodeIds.forEach(id => updates[id] = [])
    edgeIds.forEach(id => updates[id] = [])
    if (nodeIds.length + edgeIds.length > 0) {
      await graphInstance.setElementState(updates)
    }
    activeNodeId = null
    await graphInstance.draw()
  }

  if (props.enableFocusNeighbor) {
    graphInstance.on('node:click', async (e) => {
      emit('node-click', e)
      const clickedNodeId = getClickedId(e)
      if (!clickedNodeId) return

      if (activeNodeId === clickedNodeId) {
        await resetStyles()
        return
      }

      activeNodeId = clickedNodeId
      const { nodeIds, edgeIds, edges } = getIds()

      const updates = {}
      nodeIds.forEach(id => updates[id] = ['hidden'])
      edgeIds.forEach(id => updates[id] = ['hidden'])

      const neighborSet = new Set()
      const relatedEdgeIds = []
      edges.forEach((edge) => {
        if (edge.source === clickedNodeId) { neighborSet.add(edge.target); relatedEdgeIds.push(edge.id) }
        else if (edge.target === clickedNodeId) { neighborSet.add(edge.source); relatedEdgeIds.push(edge.id) }
      })

      updates[clickedNodeId] = ['focus']
      Array.from(neighborSet).forEach(id => updates[id] = ['focus'])
      relatedEdgeIds.forEach(id => updates[id] = ['focus'])

      await graphInstance.setElementState(updates)
      await graphInstance.draw()
    })

    graphInstance.on('canvas:click', async () => {
      emit('canvas-click')
      await resetStyles()
    })
  } else {
    graphInstance.on('node:click', (e) => emit('node-click', e))
    graphInstance.on('edge:click', (e) => emit('edge-click', e))
    graphInstance.on('canvas:click', () => emit('canvas-click'))
  }
}

function setGraphData() {
  if (!graphInstance) initGraph()
  if (!graphInstance) return
  const data = formatData()
  graphInstance.setData(data)
  graphInstance.render()
  setTimeout(() => {
    emit('data-rendered')
  }, 100)
}

function renderGraph() {
  if (!graphInstance) initGraph()
  setGraphData()
}

function refreshGraph() {
  if (graphInstance) {
    try { graphInstance.destroy() } catch (e) {}
    graphInstance = null
  }
  if (container.value) container.value.innerHTML = ''
  retryCount = 0
  clearTimeout(renderTimeout)
  renderTimeout = setTimeout(() => { renderGraph() }, 300)
}

function fitView() { if (graphInstance) try { graphInstance.fitView() } catch (_) {} }
function fitCenter() { if (graphInstance) try { graphInstance.fitCenter() } catch (_) {} }
function getInstance() { return graphInstance }

async function focusNode(id) {
  if (!graphInstance || !props.enableFocusNeighbor) return
  const { nodes, edges } = graphInstance.getData()
  const nodeIds = nodes.map(n => n.id)
  const edgeIds = edges.map(e => e.id)
  const updates = {}
  nodeIds.forEach(nid => updates[nid] = ['hidden'])
  edgeIds.forEach(eid => updates[eid] = ['hidden'])
  const neighborSet = new Set()
  const related = []
  edges.forEach((e) => {
    if (e.source === id) { neighborSet.add(e.target); related.push(e.id) }
    else if (e.target === id) { neighborSet.add(e.source); related.push(e.id) }
  })
  updates[id] = ['focus']
  Array.from(neighborSet).forEach(nid => updates[nid] = ['focus'])
  related.forEach(eid => updates[eid] = ['focus'])
  await graphInstance.setElementState(updates)
  await graphInstance.draw()
}

async function clearFocus() {
  if (!graphInstance) return
  const { nodes, edges } = graphInstance.getData()
  const nodeIds = nodes.map(n => n.id)
  const edgeIds = edges.map(e => e.id)
  const updates = {}
  nodeIds.forEach(nid => updates[nid] = [])
  edgeIds.forEach(eid => updates[eid] = [])
  await graphInstance.setElementState(updates)
  await graphInstance.draw()
}

watch(() => props.graphData, () => {
  clearTimeout(renderTimeout)
  renderTimeout = setTimeout(() => setGraphData(), 50)
}, { deep: true })

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
  renderTimeout = setTimeout(() => { renderGraph() }, 300)

  window.addEventListener('resize', refreshGraph)
})

onUnmounted(() => {
  window.removeEventListener('resize', refreshGraph)
  if (resizeObserver && container.value) resizeObserver.unobserve(container.value)
  clearTimeout(renderTimeout)
  try { graphInstance?.destroy() } catch (e) {}
  graphInstance = null
})

// 暴露方法
defineExpose({ refreshGraph, fitView, fitCenter, getInstance, focusNode, clearFocus, setData: setGraphData })
</script>

<style lang="less">
.graph-canvas-container {
  position: relative;
  width: 100%;
  height: 100%;

  .graph-canvas {
    width: 100%;
    height: 100%;
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

      &.top { top: 0; }
      &.bottom { bottom: 0; }
    }
    .content {
      // 中间内容层及其子元素全部穿透
      pointer-events: none;
      flex: 1;
    }
    .content * {
      pointer-events: none;
    }
  }
}

</style>