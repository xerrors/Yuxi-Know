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

const initGraph = () => {
  // 确保容器大小已经稳定
  const width = container.value.offsetWidth;
  const height = container.value.offsetHeight;

  if (width < 100) {
    // 如果容器宽度太小，可能是抽屉还在展开中，稍后重试
    setTimeout(initGraph, 100);
    return;
  }

  // 确保容器干净，没有残留元素
  if (container.value) {
    container.value.innerHTML = '';
  }

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
};

const renderGraph = () => {
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
      graphInstance.destroy();
      graphInstance = null;

      // 清理容器内容
      if (container.value) {
        container.value.innerHTML = '';
      }
    }
  }

  if (!graphInstance) {
    initGraph();
  }

  if (!graphInstance) {
    // 初始化可能推迟执行，此时直接返回
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

  graphInstance.setData(formattedData);
  graphInstance.render();

  // 确保图表正确居中和适应视图
  setTimeout(() => {
    if (graphInstance) {
      graphInstance.fitCenter();
      graphInstance.fitView();
    }
  }, 300);
};

// 添加供父组件调用的刷新方法
const refreshGraph = () => {
  // 销毁现有图表实例
  if (graphInstance) {
    graphInstance.destroy();
    graphInstance = null;
  }

  // 清理容器内容
  if (container.value) {
    container.value.innerHTML = '';
  }

  // 延迟重新渲染，确保容器大小已经稳定
  setTimeout(() => {
    renderGraph();
  }, 100);
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
          renderGraph();
        }
      }
    });

    if (container.value) {
      resizeObserver.observe(container.value);
    }
  }

  renderGraph();
  window.addEventListener('resize', renderGraph);
});

// 添加组件卸载时的清理
onUnmounted(() => {
  window.removeEventListener('resize', renderGraph);

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
    refreshGraph();
  }
}, { deep: true });
</script>

<style scoped>
.graph-container {
  background: #F7F7F7;
  border-radius: 16px;
  width: 100%;
  height: 600px;
  overflow: hidden;
}
</style>