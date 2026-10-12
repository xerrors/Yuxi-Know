<template>
  <figure class="widget-image" :style="{ aspectRatio: node.aspectRatio || 16 / 9 }">
    <img
      v-show="!failed"
      :src="node.src"
      :alt="node.alt"
      :style="{ objectFit: node.fit || 'cover' }"
      loading="lazy"
      referrerpolicy="no-referrer"
      @load="loaded = true; failed = false"
      @error="failed = true"
    />
    <p v-if="failed" class="widget-image-status" role="alert">图片无法加载：{{ node.alt }}</p>
    <p v-else-if="!loaded" class="widget-image-status" role="status">图片加载中…</p>
  </figure>
</template>

<script setup>
import { ref } from 'vue'
defineProps({ node: { type: Object, required: true } })
const loaded = ref(false)
const failed = ref(false)
</script>

<style lang="less">
.yuxi-widget .widget-image {
  position: relative;
  width: 100%;
  margin: 0;
  overflow: hidden;
  border-radius: 12px;
  background: var(--widget-field);
  img {
    display: block;
    width: 100%;
    height: 100%;
    max-width: 100%;
  }
  .widget-image-status {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    margin: 0;
    font-size: 13px;
    color: var(--widget-muted);
  }
}
</style>
