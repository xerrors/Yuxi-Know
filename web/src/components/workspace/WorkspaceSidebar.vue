<template>
  <aside class="workspace-sidebar">
    <section class="sidebar-section">
      <button
        type="button"
        class="workspace-nav-item"
        :class="{ active: activeKey === 'personal' && !isQuickAccessPath(currentPath) }"
        @click="$emit('select-personal')"
      >
        <FileTypeIcon is-dir folder-variant="personal" :size="18" />
        <span>个人工作区</span>
      </button>
    </section>

    <section class="sidebar-section">
      <div class="section-title">快速访问</div>
      <button
        type="button"
        class="workspace-nav-item secondary"
        :class="{
          active: activeKey === 'personal' && isSameOrChildPath(currentPath, savedArtifactsPath)
        }"
        @click="$emit('select-path', savedArtifactsPath)"
      >
        <FileTypeIcon is-dir folder-variant="favorite" :size="18" />
        <span>保存的交付物</span>
      </button>
      <button
        type="button"
        class="workspace-nav-item secondary"
        :class="{ active: activeKey === 'personal' && isSameOrChildPath(currentPath, agentsPath) }"
        @click="$emit('select-path', agentsPath)"
      >
        <FileTypeIcon is-dir folder-variant="agent" :size="18" />
        <span>智能体文件</span>
      </button>
    </section>

    <section v-if="myDatabases.length" class="sidebar-section">
      <div class="section-title">我的知识库</div>
      <button
        v-for="database in myDatabases"
        :key="database.kb_id || database.id || database.name"
        type="button"
        class="workspace-nav-item secondary"
        :class="{ active: activeKey === `database:${database.kb_id}` }"
        @click="$emit('select-database', database)"
      >
        <FileTypeIcon is-dir :size="18" />
        <span>{{ database.name }}</span>
      </button>
    </section>

    <section v-if="sharedDatabases.length" class="sidebar-section">
      <div class="section-title">共享知识库</div>
      <button
        v-for="database in sharedDatabases"
        :key="database.kb_id || database.id || database.name"
        type="button"
        class="workspace-nav-item secondary"
        :class="{ active: activeKey === `database:${database.kb_id}` }"
        @click="$emit('select-database', database)"
      >
        <FileTypeIcon is-dir :size="18" />
        <span>{{ database.name }}</span>
      </button>
    </section>

    <section v-if="loadingDatabases" class="sidebar-section">
      <div class="sidebar-muted">正在加载知识库...</div>
    </section>
    <section v-else-if="!databases.length" class="sidebar-section">
      <div class="sidebar-muted">暂无可访问知识库</div>
    </section>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import FileTypeIcon from '@/components/common/FileTypeIcon.vue'

const savedArtifactsPath = '/saved_artifacts'
const agentsPath = '/agents/'
const quickAccessPaths = [savedArtifactsPath, agentsPath]

const normalizePath = (path) => String(path || '/').replace(/\/$/, '') || '/'
const isSameOrChildPath = (path, targetPath) => {
  const current = normalizePath(path)
  const target = normalizePath(targetPath)
  return current === target || current.startsWith(`${target}/`)
}
const isQuickAccessPath = (path) =>
  quickAccessPaths.some((targetPath) => isSameOrChildPath(path, targetPath))

const props = defineProps({
  activeKey: { type: String, default: 'personal' },
  currentPath: { type: String, default: '/' },
  databases: { type: Array, default: () => [] },
  loadingDatabases: { type: Boolean, default: false },
  currentUid: { type: String, default: '' }
})

defineEmits(['select-personal', 'select-database', 'select-path'])

const myDatabases = computed(() =>
  props.databases.filter((db) => db.created_by === props.currentUid)
)

const sharedDatabases = computed(() =>
  props.databases.filter((db) => db.created_by !== props.currentUid)
)
</script>

<style scoped lang="less">
.workspace-sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 14px 10px;
  border-right: 1px solid var(--gray-100);
  background: var(--gray-0);
  overflow-y: auto;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  // gap: 6px;
}

.section-title {
  padding: 4px 8px;
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
  color: var(--gray-600);
  font-size: 14px;
  font-weight: 600;
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
    font-weight: 500;
  }

  &:hover:not(:disabled),
  &.active {
    border-color: transparent;
    color: var(--main-600);
  }

  &.secondary {
    min-height: 32px;
    font-size: 13px;
  }
}

.sidebar-muted {
  padding: 6px 8px;
  color: var(--gray-500);
  font-size: 12px;
  line-height: 1.5;
}
</style>
