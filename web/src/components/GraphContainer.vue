<template>
  <div class="graph-container" ref="container"></div>
</template>

<script setup>
import { Graph } from "@antv/g6";
import { onMounted, watch, ref } from 'vue';

const props = defineProps({
  graphData: {
    type: Object,
    required: true,
    default: () => ({ nodes: [], edges: [] })
  }
});

const container = ref(null);
let graphInstance = null;

const initGraph = () => {
  graphInstance = new Graph({
    container: container.value,
    width: container.value.offsetWidth,
    height: container.value.offsetHeight,
    autoFit: true,
    autoResize: true,
    layout: {
      type: 'd3-force',
      preventOverlap: true,
      kr: 20,
      collide: {
        strength: 1.0,
      },
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
  if (!graphInstance) {
    initGraph();
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
};

onMounted(() => {
  renderGraph();
  window.addEventListener('resize', renderGraph);
});

watch(() => props.graphData, renderGraph, { deep: true });
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