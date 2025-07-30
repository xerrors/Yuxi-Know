<template>
  <div class="graph-container" ref="container"></div>
</template>

<script setup>
import { Graph } from "@antv/g6";
import { onMounted, watch, ref, onUnmounted } from 'vue';

const props = defineProps({
  graphData: {
    type: Object,
    required: true,
    default: () => ({ nodes: [], edges: [] })
  }
});

const container = ref(null);
let graphInstance = null;
let resizeObserver = null;
let renderTimeout = null;
let retryCount = 0;
const MAX_RETRIES = 5;

const initGraph = () => {
  // 确保容器存在
  if (!container.value) {
    console.warn('GraphContainer: container is not available');
    return;
  }

  // 确保容器大小已经稳定
  const width = container.value.offsetWidth;
  const height = container.value.offsetHeight;

  // 如果容器尺寸为0，增加重试次数
  if (width === 0 && height === 0) {
    if (retryCount < MAX_RETRIES) {
      retryCount++;
      // console.log(`GraphContainer: Container size is 0, retrying (${retryCount}/${MAX_RETRIES})`);
      setTimeout(initGraph, 200);
      return;
    } else {
      console.warn('GraphContainer: Container size remains 0 after maximum retries');
      return;
    }
  }

  retryCount = 0; // 重置重试计数

  // 确保容器干净，没有残留元素
  container.value.innerHTML = '';

  // 确保没有已存在的实例
  if (graphInstance) {
    graphInstance.destroy();
    graphInstance = null;
  }

  graphInstance = new Graph({
    container: container.value,
    width: width,
    height: height,
    autoFit: true,
    autoResize: true,
    layout: {
      type: 'd3-force',
      preventOverlap: true,
      kr: 30,
      linkDistance: 200,
      nodeStrength: -100,
      collide: {
        strength: 1.5,
        radius: 60,
      },
      alpha: 0.8,
      alphaDecay: 0.028,
      center: [width / 2, height / 2],
    },
    node: {
      type: 'circle',
      style: {
        labelText: (d) => d.data.label,
        size: 70,
      },
      palette: {
        field: 'label',
        color: 'tableau',
      },
    },
    edge: {
      type: 'line',
      style: {
        labelText: (d) => d.data.label,
        labelBackground: '#fff',
        endArrow: true,
      },
    },
    behaviors: ['drag-element', 'zoom-canvas', 'drag-canvas'],
  });

  // console.log(`GraphContainer: Graph initialized with dimensions ${width}x${height}`);
};

const renderGraph = () => {
  // 检查数据是否有效
  if (!props.graphData || !props.graphData.nodes || !props.graphData.edges) {
    console.warn('GraphContainer: Invalid graphData provided');
    return;
  }

  // console.log('GraphContainer: Rendering graph with', props.graphData.nodes.length, 'nodes and', props.graphData.edges.length, 'edges');

  // 如果已有实例且容器大小发生明显变化，则销毁重建
  if (graphInstance && container.value) {
    const currentWidth = container.value.offsetWidth;
    const currentHeight = container.value.offsetHeight;
    let graphWidth = 0;
    let graphHeight = 0;

    // 安全地获取图表宽高
    try {
      if (typeof graphInstance.getWidth === 'function') {
        graphWidth = graphInstance.getWidth();
      } else if (graphInstance.cfg && graphInstance.cfg.width) {
        graphWidth = graphInstance.cfg.width;
      }

      if (typeof graphInstance.getHeight === 'function') {
        graphHeight = graphInstance.getHeight();
      } else if (graphInstance.cfg && graphInstance.cfg.height) {
        graphHeight = graphInstance.cfg.height;
      }
    } catch (e) {
      console.error('Error getting graph dimensions:', e);
    }

    // 如果宽度变化超过50px，重新初始化图表
    if (Math.abs(currentWidth - graphWidth) > 50 || Math.abs(currentHeight - graphHeight) > 50) {
      // console.log('GraphContainer: Container size changed significantly, reinitializing graph');
      graphInstance.destroy();
      graphInstance = null;

      // 清理容器内容
      if (container.value) {
        container.value.innerHTML = '';
      }
    }
  }

  // 如果没有图表实例，尝试初始化
  if (!graphInstance) {
    initGraph();
  }

  // 如果仍然没有图表实例，直接返回
  if (!graphInstance) {
    // console.warn('GraphContainer: Failed to initialize graph instance');
    return;
  }

  const formattedData = {
    nodes: props.graphData.nodes.map(node => ({
      id: node.id,
      data: { label: node.name }
    })),
    edges: props.graphData.edges.map(edge => ({
      source: edge.source_id,
      target: edge.target_id,
      data: { label: edge.type }
    }))
  };

  // console.log('GraphContainer: Setting data and rendering graph');
  graphInstance.setData(formattedData);

  // 强制刷新视图
  graphInstance.render();

  // 确保图表正确居中和适应视图
  setTimeout(() => {
    if (graphInstance) {
      graphInstance.fitCenter();
      graphInstance.fitView();
      // console.log('GraphContainer: Graph rendered and fitted');
    }
  }, 100);
};

// 添加供父组件调用的刷新方法
const refreshGraph = () => {
  // console.log('GraphContainer: refreshGraph called');

  // 销毁现有图表实例
  if (graphInstance) {
    graphInstance.destroy();
    graphInstance = null;
  }

  // 清理容器内容
  if (container.value) {
    container.value.innerHTML = '';
  }

  // 重置重试计数
  retryCount = 0;

  // 延迟重新渲染，确保容器大小已经稳定
  // 增加延迟时间确保窗口完全打开
  clearTimeout(renderTimeout);
  renderTimeout = setTimeout(() => {
    renderGraph();
  }, 300);
};

// 向父组件暴露方法
defineExpose({
  refreshGraph
});

onMounted(() => {
  // 使用ResizeObserver监听容器大小变化
  if (window.ResizeObserver) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === container.value) {
          // console.log('GraphContainer: Container resized to', entry.contentRect.width, 'x', entry.contentRect.height);
          renderGraph();
        }
      }
    });

    if (container.value) {
      resizeObserver.observe(container.value);
    }
  }

  // 初始渲染，增加延迟确保容器完全展开
  clearTimeout(renderTimeout);
  renderTimeout = setTimeout(() => {
    renderGraph();
  }, 300);

  window.addEventListener('resize', renderGraph);
});

// 添加组件卸载时的清理
onUnmounted(() => {
  window.removeEventListener('resize', renderGraph);

  clearTimeout(renderTimeout);

  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }

  if (graphInstance) {
    graphInstance.destroy();
    graphInstance = null;
  }

  // 确保清理容器内容
  if (container.value) {
    container.value.innerHTML = '';
  }
});

watch(() => props.graphData, (newData, oldData) => {
  // 强制重新渲染图表
  if (newData !== oldData) {
    // console.log('GraphContainer: graphData changed, refreshing graph');
    refreshGraph();
  }
}, { deep: true });
</script>

<style scoped>
.graph-container {
  background: #F7F7F7;
  border-radius: 16px;
  width: 100%;
  min-height: 400px;
  height: 100%;
  overflow: hidden;
}
</style>