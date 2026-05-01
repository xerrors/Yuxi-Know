<template>
  <div class="extension-detail-layout">
    <div class="extension-detail-inner" :class="{ 'extension-detail-narrow': narrow }">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  narrow: { type: Boolean, default: false }
})
</script>

<style lang="less" scoped>
.extension-detail-layout {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background-color: var(--gray-10);
}

.extension-detail-inner {
  max-width: 900px;
  margin: 0 auto;

  &.extension-detail-narrow {
    max-width: 720px;
  }
}
</style>
