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
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-600);
  font-size: 15px;
  font-weight: 500;
  line-height: 1;
  text-decoration: none;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;

  &:hover {
    color: var(--gray-900);
    background-color: var(--gray-50);
  }

  &:focus-visible {
    outline: 2px solid var(--main-200);
    outline-offset: 2px;
  }

  &.active {
    color: var(--main-color);
    background-color: color-mix(in srgb, var(--main-color) 6%, var(--gray-0));
    border-color: transparent;
    position: relative;
  }
}
</style>
