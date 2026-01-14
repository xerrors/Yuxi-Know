<template>
  <div class="header-container">
    <div class="header-content">
      <div class="header-actions" v-if="$slots.left">
        <slot name="left"></slot>
      </div>
      <div class="header-title">
        <div class="header-title-block">
          <h1>{{ title }}</h1>
          <slot name="behind-title"></slot>
        </div>
        <slot name="description">
          <p v-if="description">{{ description }}</p>
        </slot>
      </div>
      <div class="header-actions" v-if="$slots.actions">
        <loading-outlined v-if="loading" />
        <slot name="actions"></slot>
      </div>
    </div>
  </div>
</template>

<script setup>
import { LoadingOutlined } from '@ant-design/icons-vue'
const props = defineProps({
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  },
  loading: {
    type: Boolean,
    default: false
  }
})
</script>

<style scoped lang="less">
.header-container {
  background-color: var(--bg-sider);
  backdrop-filter: blur(10px);
  padding: 10px 24px;
  border-bottom: 1px solid var(--gray-150);
  position: sticky;
  top: 0;
  z-index: 1000;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.header-title {
  flex: 1;
  width: 100%;
  font-size: 14px;
  color: rgba(0, 0, 0, 0.45);

  .header-title-block {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }

  h1 {
    margin: 0;
    font-size: 18px;
    font-weight: 500;
    color: var(--gray-2000);
  }

  p {
    margin: 8px 0 0;
  }
}

.header-actions {
  display: flex;
  gap: 8px;
}
</style>
