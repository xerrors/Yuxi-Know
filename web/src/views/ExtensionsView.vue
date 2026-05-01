<template>
  <div class="extensions-view extension-page-root">
    <PageHeader
      v-if="!isDetailPage"
      v-model:active-key="activeTab"
      title="扩展管理"
      :tabs="extensionTabs"
      :loading="activeChildLoading"
      :show-border="true"
      aria-label="扩展管理视图切换"
    />

    <div v-if="!isDetailPage" class="extensions-content">
      <div v-show="activeTab === 'tools'" class="tab-panel">
        <ToolsCardList ref="toolsRef" />
      </div>
      <div v-show="activeTab === 'skills'" class="tab-panel">
        <SkillCardList ref="skillsRef" />
      </div>
      <div v-show="activeTab === 'mcp'" class="tab-panel">
        <McpCardList ref="mcpRef" />
      </div>
      <div v-show="activeTab === 'subagents'" class="tab-panel">
        <SubagentCardList ref="subagentsRef" />
      </div>
    </div>

    <router-view v-else />
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import ToolsCardList from '@/components/extensions/ToolsCardList.vue'
import McpCardList from '@/components/extensions/McpCardList.vue'
import SubagentCardList from '@/components/extensions/SubagentCardList.vue'
import SkillCardList from '@/components/extensions/SkillCardList.vue'
import PageHeader from '@/components/shared/PageHeader.vue'

const route = useRoute()
const activeTab = ref('tools')
const skillsRef = ref(null)
const mcpRef = ref(null)
const subagentsRef = ref(null)
const toolsRef = ref(null)

const extensionTabs = [
  { key: 'tools', label: '工具' },
  { key: 'mcp', label: 'MCP' },
  { key: 'subagents', label: 'Subagents' },
  { key: 'skills', label: 'Skills' }
]

const isDetailPage = computed(() => {
  return (
    route.path.startsWith('/extensions/mcp/') ||
    route.path.startsWith('/extensions/subagent/') ||
    route.path.startsWith('/extensions/skill/')
  )
})

const activeChildLoading = computed(() => {
  const refMap = { tools: toolsRef, skills: skillsRef, mcp: mcpRef, subagents: subagentsRef }
  const child = refMap[activeTab.value]
  return child?.value?.loading || false
})

watch(
  () => route.query,
  (query) => {
    if (query.tab && ['tools', 'skills', 'mcp', 'subagents'].includes(query.tab)) {
      activeTab.value = query.tab
    }
  },
  { immediate: true }
)
</script>

<style scoped lang="less">
@import '@/assets/css/extensions.less';

.extensions-view {
  .extensions-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;

    .tab-panel {
      height: 100%;
      min-height: 0;
      overflow-y: auto;
    }
  }
}
</style>
