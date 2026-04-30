<template>
  <aside class="workspace-sidebar">
    <section class="sidebar-section">
      <button
        type="button"
        class="workspace-nav-item"
        :class="{ active: activeKey === 'personal' }"
        @click="$emit('select-personal')"
      >
        <FolderKanban :size="16" />
        <span>个人工作区</span>
      </button>
    </section>

    <section class="sidebar-section">
      <div class="section-title">知识库</div>
      <button
        v-for="database in databases"
        :key="database.db_id || database.id || database.name"
        type="button"
        class="workspace-nav-item secondary"
        :class="{ active: activeKey === `database:${database.db_id}` }"
        @click="$emit('select-database', database)"
      >
        <LibraryBig :size="15" />
        <span>{{ database.name }}</span>
      </button>
      <div v-if="loadingDatabases" class="sidebar-muted">正在加载知识库...</div>
      <div v-else-if="!databases.length" class="sidebar-muted">暂无可访问知识库</div>
    </section>

    <section class="sidebar-section">
      <div class="section-title">共享空间</div>
      <button type="button" class="workspace-nav-item secondary disabled" disabled>
        <UsersRound :size="15" />
        <span>团队工作区</span>
        <span class="soon-tag">即将支持</span>
      </button>
    </section>
  </aside>
</template>

<script setup>
import { FolderKanban, LibraryBig, UsersRound } from 'lucide-vue-next'

defineProps({
  activeKey: { type: String, default: 'personal' },
  databases: { type: Array, default: () => [] },
  loadingDatabases: { type: Boolean, default: false }
})

defineEmits(['select-personal', 'select-database'])
</script>

<style scoped lang="less">
.workspace-sidebar {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
  padding: 14px calc(var(--page-padding) - 8px);
  border-right: 1px solid var(--gray-100);
  background: var(--gray-25);
  overflow-y: auto;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-title {
  padding: 0 8px;
  color: var(--gray-500);
  font-size: 12px;
  font-weight: 600;
  line-height: 20px;
}

.workspace-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--gray-700);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease;

  span:first-of-type {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &:hover:not(:disabled),
  &.active {
    border-color: transparent;
    background: var(--main-20);
    color: var(--main-color);
  }

  &.secondary {
    min-height: 32px;
    font-size: 13px;
  }

  &.disabled {
    color: var(--gray-400);
    cursor: not-allowed;
  }
}

.soon-tag {
  flex: 0 0 auto;
  margin-left: auto;
  color: var(--gray-400);
  font-size: 11px;
}

.sidebar-muted {
  padding: 6px 8px;
  color: var(--gray-500);
  font-size: 12px;
  line-height: 1.5;
}
</style>
