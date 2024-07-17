<template>
  <div class="graph-container">
    <div class="main" id="container"></div>
  </div>
</template>

<script setup>
import { Graph } from "@antv/g6";
import { onMounted } from 'vue';

const getCurWidth = () => document.getElementById("container").offsetWidth
const getCurHeight = () => document.getElementById("container").offsetHeight


onMounted(() => {
  const graph = new Graph({
    container: document.getElementById("container"),
    width: getCurWidth(),
    height: getCurHeight(),
    data: {
      nodes: [
        {
          id: "node-1",
          style: { x: 50, y: 100 },
        },
        {
          id: "node-2",
          style: { x: 150, y: 100 },
        },
      ],
      edges: [{ id: "edge-1", source: "node-1", target: "node-2" }],
    },
    behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
  });

  graph.render();
});
</script>

<style scoped>
.graph-container {}

#container {
  width: 100%;
  height: 100%;
}

</style>
