<template>
  <div class="extensions-view extension-page-root">
    <ViewSwitchHeader
      v-model:active-key="activeTab"
      title="扩展管理"
      :items="extensionTabs"
      aria-label="扩展管理视图切换"
    >
      <template #actions>
        <div class="extension-header-actions">
          <!-- Skills Tab 的按钮 -->
          <template v-if="activeTab === 'skills'">
            <a-button
              @click="handleOpenRemoteInstall"
              :disabled="skillsLoading || skillsImporting"
              class="lucide-icon-btn"
            >
              <Computer :size="14" />
              <span>远程安装</span>
            </a-button>
            <a-upload
              accept=".zip,.md"
              :show-upload-list="false"
              :custom-request="handleImportUpload"
              :before-upload="beforeSkillUpload"
              :disabled="skillsLoading || skillsImporting"
            >
              <a-button type="primary" :loading="skillsImporting" class="lucide-icon-btn">
                <Upload :size="14" />
                <span>上传 Skill</span>
              </a-button>
            </a-upload>
          </template>
          <!-- MCP Tab 的按钮 -->
          <template v-else-if="activeTab === 'mcp'">
            <a-button type="primary" @click="handleMcpAdd" class="lucide-icon-btn">
              <Plus :size="14" />
              <span>添加 MCP</span>
            </a-button>
          </template>
          <!-- Subagents Tab 的按钮 -->
          <template v-else-if="activeTab === 'subagents'">
            <a-button type="primary" @click="handleSubagentAdd" class="lucide-icon-btn">
              <Plus :size="14" />
              <span>添加</span>
            </a-button>
          </template>
        </div>
      </template>
    </ViewSwitchHeader>

    <div class="extensions-content">
      <div v-show="activeTab === 'tools'" class="tab-panel">
        <ToolsManagerComponent />
      </div>
      <div v-show="activeTab === 'skills'" class="tab-panel">
        <SkillsManagerComponent ref="skillsRef" @import="handleSkillsImport" />
      </div>
      <div v-show="activeTab === 'mcp'" class="tab-panel">
        <McpServersComponent ref="mcpRef" @add="handleMcpAdd" />
      </div>
      <div v-show="activeTab === 'subagents'" class="tab-panel">
        <SubAgentsComponent ref="subagentsRef" @add="handleSubagentAdd" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { Upload, Plus, Computer } from 'lucide-vue-next'
import SkillsManagerComponent from '@/components/SkillsManagerComponent.vue'
import ToolsManagerComponent from '@/components/ToolsManagerComponent.vue'
import McpServersComponent from '@/components/McpServersComponent.vue'
import SubAgentsComponent from '@/components/SubAgentsComponent.vue'
import ViewSwitchHeader from '@/components/ViewSwitchHeader.vue'

const route = useRoute()
const activeTab = ref('tools')
const skillsRef = ref(null)

const extensionTabs = [
  { key: 'tools', label: '工具' },
  { key: 'mcp', label: 'MCP' },
  { key: 'subagents', label: 'Subagents' },
  { key: 'skills', label: 'Skills' }
]

// 监听路由 query 参数变化
watch(
  () => route.query,
  (query) => {
    if (query.tab && ['tools', 'skills', 'mcp', 'subagents'].includes(query.tab)) {
      activeTab.value = query.tab
    }
  },
  { immediate: true }
)
const mcpRef = ref(null)
const subagentsRef = ref(null)

// Skills 相关状态（从子组件透传）
const skillsLoading = ref(false)
const skillsImporting = ref(false)

// 暴露给子组件的状态更新
const updateSkillsState = (loading, importing) => {
  skillsLoading.value = loading
  skillsImporting.value = importing
}

// Skills 事件处理
const handleSkillsImport = () => {
  // 导入完成后自动刷新
  handleSkillsRefresh()
}

const handleSkillsRefresh = () => {
  if (skillsRef.value?.fetchSkills) {
    updateSkillsState(true, skillsImporting.value)
    skillsRef.value.fetchSkills().finally(() => {
      updateSkillsState(false, skillsImporting.value)
    })
  }
}

const handleOpenRemoteInstall = () => {
  if (skillsRef.value?.openRemoteInstallModal) {
    skillsRef.value.openRemoteInstallModal()
  }
}

// MCP 事件处理
const handleMcpAdd = () => {
  if (mcpRef.value?.showAddModal) {
    mcpRef.value.showAddModal()
  }
}

// Subagents 事件处理
const handleSubagentAdd = () => {
  if (subagentsRef.value?.showAddModal) {
    subagentsRef.value.showAddModal()
  }
}

// 上传前校验文件名：仅允许 .zip 或 SKILL.md
const beforeSkillUpload = (file) => {
  const lower = file.name.toLowerCase()
  if (!lower.endsWith('.zip') && lower !== 'skill.md') {
    message.error('仅支持上传 .zip 文件或 SKILL.md 文件')
    return false
  }
  return true
}

// 处理导入上传
const handleImportUpload = async ({ file, onSuccess, onError }) => {
  if (skillsRef.value?.handleImportUpload) {
    updateSkillsState(skillsLoading.value, true)
    try {
      await skillsRef.value.handleImportUpload({ file, onSuccess, onError })
      handleSkillsImport()
    } catch (e) {
      onError?.(e)
    } finally {
      updateSkillsState(skillsLoading.value, false)
    }
  }
}
</script>

<style scoped lang="less">
@import '@/assets/css/extensions.less';

.extensions-view {
  .extension-header-actions {
    display: flex;
    gap: 8px;
  }

  .extensions-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;

    .tab-panel {
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }
  }
}
</style>
