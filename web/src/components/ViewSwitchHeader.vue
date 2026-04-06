<template>
  <HeaderComponent :title="title" :loading="loading">
    <template #behind-title>
      <nav class="view-switcher" :aria-label="ariaLabel">
        <slot name="options" :items="items" :active-key="activeKey" :select="selectItem">
          <template v-for="item in items" :key="item.key">
            <RouterLink
              v-if="item.path"
              :to="item.path"
              class="switcher-item"
              :class="{ active: activeKey === item.key }"
              @click="selectItem(item)"
            >
              {{ item.label }}
            </RouterLink>
            <button
              v-else
              type="button"
              class="switcher-item"
              :class="{ active: activeKey === item.key }"
              @click="selectItem(item)"
            >
              {{ item.label }}
            </button>
          </template>
        </slot>
      </nav>
    </template>

    <template #actions v-if="$slots.actions">
      <slot name="actions"></slot>
    </template>
  </HeaderComponent>
</template>

<script setup>
import { RouterLink } from 'vue-router'
import HeaderComponent from '@/components/HeaderComponent.vue'

defineProps({
  title: {
    type: String,
    required: true
  },
  loading: {
    type: Boolean,
    default: false
  },
  activeKey: {
    type: String,
    required: true
  },
  items: {
    type: Array,
    required: true
  },
  ariaLabel: {
    type: String,
    default: '视图切换'
  }
})

const emit = defineEmits(['update:activeKey', 'change'])

const selectItem = (item) => {
  emit('update:activeKey', item.key)
  emit('change', item)
}
</script>

<style scoped lang="less">
.view-switcher {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding-left: 12px;
  margin-left: 2px;
  border-left: 1px solid var(--gray-200);
}

.switcher-item {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-700);
  font-size: 15px;
  font-weight: 500;
  line-height: 1;
  text-decoration: none;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;

  &:hover {
    color: var(--main-color);
    background-color: var(--gray-50);
  }

  &.active {
    color: var(--main-color);
    background-color: var(--main-40);
  }
}
</style>
