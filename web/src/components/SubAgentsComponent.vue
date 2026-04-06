<template>
  <div class="subagents-component extension-page-root">
    <div v-if="loading" class="loading-bar-wrapper">
      <div class="loading-bar"></div>
    </div>
    <div class="layout-wrapper" :class="{ 'content-loading': loading }">
      <!-- 左侧：SubAgent 列表 -->
      <div class="sidebar-list">
        <!-- 搜索框 -->
        <div class="sidebar-toolbar">
          <div class="search-box">
            <a-input
              v-model:value="searchQuery"
              placeholder="搜索 SubAgent..."
              allow-clear
              class="search-input"
            >
              <template #prefix><Search :size="14" class="text-muted" /></template>
            </a-input>
          </div>

          <a-tooltip title="刷新 Subagents">
            <a-button class="sidebar-tool" :disabled="loading" @click="fetchSubAgents">
              <RotateCw :size="14" />
            </a-button>
          </a-tooltip>
        </div>

        <!-- SubAgent 列表 -->
        <div class="list-container">
          <div
            v-if="!filteredEnabledSubAgents.length && !filteredDisabledSubAgents.length"
            class="empty-text"
          >
            <a-empty
              :image="false"
              :description="searchQuery ? '无匹配 SubAgent' : '暂无 SubAgent'"
            />
          </div>
          <div v-if="filteredEnabledSubAgents.length" class="list-section-title">已添加</div>
          <template
            v-for="(agent, index) in filteredEnabledSubAgents"
            :key="`enabled-${agent.name}`"
          >
            <div
              class="list-item extension-list-item"
              :class="{ active: currentAgent?.name === agent.name }"
              @click="selectAgent(agent)"
            >
              <div class="item-main-row">
                <div class="item-header">
                  <Bot :size="16" class="item-icon" />
                  <span class="item-name">{{ agent.name }}</span>
                </div>
                <div class="item-status">
                  <span class="status-chip status-chip-success">已添加</span>
                  <button
                    type="button"
                    class="inline-hover-action danger"
                    @click.stop="handleSetAgentEnabled(agent, false)"
                  >
                    移除
                  </button>
                </div>
              </div>
              <div class="item-details">
                <span class="item-desc">{{ agent.description || '暂无描述' }}</span>
                <div class="item-tags">
                  <span v-if="agent.is_builtin" class="source-tag builtin">内置</span>
                </div>
              </div>
            </div>
            <div
              v-if="
                index < filteredEnabledSubAgents.length - 1 || filteredDisabledSubAgents.length > 0
              "
              class="list-separator"
            ></div>
          </template>

          <div v-if="filteredDisabledSubAgents.length" class="list-section-title">可添加</div>
          <template
            v-for="(agent, index) in filteredDisabledSubAgents"
            :key="`disabled-${agent.name}`"
          >
            <div
              class="list-item extension-list-item"
              :class="{ active: currentAgent?.name === agent.name }"
              @click="selectAgent(agent)"
            >
              <div class="item-main-row">
                <div class="item-header">
                  <Bot :size="16" class="item-icon" />
                  <span class="item-name">{{ agent.name }}</span>
                </div>
                <div class="item-status">
                  <button
                    type="button"
                    class="skill-inline-action skill-inline-action-primary"
                    @click.stop="handleSetAgentEnabled(agent, true)"
                  >
                    添加
                  </button>
                </div>
              </div>
              <div class="item-details">
                <span class="item-desc">{{ agent.description || '暂无描述' }}</span>
                <div class="item-tags">
                  <span v-if="agent.is_builtin" class="source-tag builtin">内置</span>
                </div>
              </div>
            </div>
            <div v-if="index < filteredDisabledSubAgents.length - 1" class="list-separator"></div>
          </template>
        </div>
      </div>

      <!-- 右侧：详情面板 -->
      <div class="main-panel">
        <div v-if="!currentAgent" class="unselected-state">
          <div class="hint-box">
            <Bot :size="40" class="text-muted" />
            <p>请在左侧选择 SubAgent 进行操作</p>
          </div>
        </div>

        <template v-else>
          <div class="panel-top-bar">
            <h2 class="panel-title-row">
              <Bot :size="18" class="panel-title-icon" />
              <span
                ><strong>{{ currentAgent.name }}</strong></span
              >
            </h2>
            <div class="panel-actions">
              <a-space :size="8">
                <a-button
                  size="small"
                  @click="showEditModal(currentAgent)"
                  class="lucide-icon-btn"
                  v-if="!currentAgent.is_builtin"
                >
                  <Pencil :size="14" />
                  <span>编辑</span>
                </a-button>
                <a-button
                  size="small"
                  danger
                  ghost
                  :disabled="currentAgent.is_builtin"
                  @click="confirmDeleteAgent(currentAgent)"
                  class="lucide-icon-btn"
                  v-if="!currentAgent.is_builtin"
                >
                  <Trash2 :size="14" />
                  <span>删除</span>
                </a-button>
              </a-space>
            </div>
          </div>

          <div class="detail-section-container">
            <div class="detail-section">
              <div class="section-header">
                <MessageSquare :size="14" />
                <span>系统提示词</span>
              </div>
              <div class="section-content">
                <div class="code-panel">
                  <pre class="code-panel-pre">{{ currentAgent.system_prompt }}</pre>
                </div>
              </div>
            </div>

            <div class="detail-section" v-if="currentAgent.description">
              <div class="section-header">
                <FileText :size="14" />
                <span>描述</span>
              </div>
              <div class="section-content description">
                {{ currentAgent.description }}
              </div>
            </div>

            <div class="detail-section" v-if="currentAgent.model">
              <div class="section-header">
                <Cpu :size="14" />
                <span>模型覆盖</span>
              </div>
              <div class="section-content">
                {{ currentAgent.model }}
              </div>
            </div>

            <div class="detail-section" v-if="currentAgent.tools && currentAgent.tools.length > 0">
              <div class="section-header">
                <Wrench :size="14" />
                <span>工具</span>
              </div>
              <div class="section-content">
                <a-tag v-for="tool in currentAgent.tools" :key="tool">{{ tool }}</a-tag>
              </div>
            </div>

            <div
              class="detail-section"
              v-if="currentAgent.is_builtin || currentAgent.enabled === false"
            >
              <div class="section-header">
                <Info :size="14" />
                <span>类型</span>
              </div>
              <div class="section-content">
                <a-tag v-if="currentAgent.is_builtin" color="blue">内置</a-tag>
                <a-tag v-else color="default">自定义</a-tag>
                <a-tag v-if="currentAgent.enabled === false" color="default">未添加</a-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="section-header">
                <Clock :size="14" />
                <span>元信息</span>
              </div>
              <div class="section-content meta-info">
                <div class="meta-item">
                  <span class="meta-label">创建时间</span>
                  <span class="meta-value">{{ formatTime(currentAgent.created_at) }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">更新时间</span>
                  <span class="meta-value">{{ formatTime(currentAgent.updated_at) }}</span>
                </div>
                <div class="meta-item" v-if="currentAgent.created_by">
                  <span class="meta-label">创建人</span>
                  <span class="meta-value">{{ currentAgent.created_by }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 添加/编辑 SubAgent 模态框 -->
    <a-modal
      v-model:open="formModalVisible"
      :title="editMode ? '编辑 SubAgent' : '添加 SubAgent'"
      @ok="handleFormSubmit"
      :confirmLoading="formLoading"
      @cancel="formModalVisible = false"
      :maskClosable="false"
      width="600px"
    >
      <a-form layout="vertical" class="extension-form">
        <a-form-item label="名称" required class="form-item">
          <a-input
            v-model:value="form.name"
            placeholder="请输入 SubAgent 名称（唯一标识）"
            :disabled="editMode"
          />
        </a-form-item>

        <a-form-item label="描述" class="form-item">
          <a-input v-model:value="form.description" placeholder="请输入 SubAgent 描述" />
        </a-form-item>

        <a-form-item label="系统提示词" required class="form-item">
          <a-textarea v-model:value="form.system_prompt" placeholder="请输入系统提示词" :rows="6" />
        </a-form-item>

        <a-form-item label="工具" class="form-item">
          <a-select
            v-model:value="form.tools"
            mode="tags"
            placeholder="选择或输入工具名称"
            style="width: 100%"
            :options="availableTools"
            @focus="fetchAvailableTools"
          />
        </a-form-item>

        <a-form-item label="模型覆盖（可选）" class="form-item">
          <div class="model-override-row">
            <ModelSelectorComponent
              :model_spec="form.model"
              placeholder="请选择模型"
              class="model-selector-full"
              @select-model="handleModelSelect"
            />
            <a-button v-if="form.model" type="link" size="small" @click="form.model = ''">
              清空
            </a-button>
          </div>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  Search,
  Bot,
  Pencil,
  Trash2,
  RotateCw,
  Info,
  MessageSquare,
  FileText,
  Cpu,
  Wrench,
  Clock
} from 'lucide-vue-next'
import { subagentApi } from '@/apis/subagent_api'
import { toolApi } from '@/apis/tool_api'
import { formatFullDateTime } from '@/utils/time'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'

// 状态
const loading = ref(false)
const error = ref(null)
const subagents = ref([])
const searchQuery = ref('')
const currentAgent = ref(null)
const availableTools = ref([])

// 表单相关
const formModalVisible = ref(false)
const formLoading = ref(false)
const editMode = ref(false)
const form = reactive({
  name: '',
  description: '',
  system_prompt: '',
  tools: [],
  model: ''
})

const getSortedSubAgents = (items) => {
  return [...items].sort((a, b) => {
    // 内置的排前面
    if (a.is_builtin !== b.is_builtin) {
      return a.is_builtin ? -1 : 1
    }
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  })
}

// 计算属性
const filteredSubAgents = computed(() => {
  const sorted = getSortedSubAgents(subagents.value)
  if (!searchQuery.value) return sorted
  const q = searchQuery.value.toLowerCase()
  return sorted.filter(
    (a) => a.name.toLowerCase().includes(q) || (a.description || '').toLowerCase().includes(q)
  )
})

const filteredEnabledSubAgents = computed(() =>
  filteredSubAgents.value.filter((item) => item.enabled !== false)
)
const filteredDisabledSubAgents = computed(() =>
  filteredSubAgents.value.filter((item) => item.enabled === false)
)

// 获取 SubAgent 列表
const fetchSubAgents = async () => {
  try {
    loading.value = true
    error.value = null
    const result = await subagentApi.getSubAgents()
    if (result.success) {
      subagents.value = result.data || []
      // 保持选中状态
      if (currentAgent.value) {
        const latest = subagents.value.find((a) => a.name === currentAgent.value.name)
        if (latest) {
          currentAgent.value = latest
        } else {
          currentAgent.value = null
        }
      }
      // 默认选中第一个已添加项
      const defaultList = filteredEnabledSubAgents.value.length
        ? filteredEnabledSubAgents.value
        : filteredDisabledSubAgents.value
      if (!currentAgent.value && defaultList.length > 0) {
        currentAgent.value = defaultList[0]
      }
    } else {
      error.value = result.message || '获取列表失败'
    }
  } catch (err) {
    console.error('获取 SubAgent 列表失败:', err)
    error.value = err.message || '获取列表失败'
  } finally {
    loading.value = false
  }
}

// 获取可选工具列表
const fetchAvailableTools = async () => {
  if (availableTools.value.length > 0) return
  try {
    const result = await toolApi.getToolOptions()
    if (result.success && result.data) {
      availableTools.value = result.data
    }
  } catch (err) {
    console.error('获取工具选项失败:', err)
  }
}

// 格式化时间
const formatTime = (timeStr) => formatFullDateTime(timeStr)

const handleModelSelect = (spec) => {
  form.model = spec || ''
}

const handleSetAgentEnabled = async (agent, enabled) => {
  try {
    const result = await subagentApi.updateSubAgentStatus(agent.name, enabled)
    if (result.success) {
      message.success(result.message || `SubAgent 已${enabled ? '添加' : '移除'}`)
      await fetchSubAgents()
    } else {
      message.error(result.message || '操作失败')
    }
  } catch (err) {
    console.error('更新状态失败:', err)
    message.error(err.message || '操作失败')
  }
}

// 选择 SubAgent
const selectAgent = (agent) => {
  currentAgent.value = agent
}

// 显示添加模态框
const showAddModal = () => {
  editMode.value = false
  Object.assign(form, {
    name: '',
    description: '',
    system_prompt: '',
    tools: [],
    model: ''
  })
  formModalVisible.value = true
}

// 显示编辑模态框
const showEditModal = async (agent) => {
  try {
    const result = await subagentApi.getSubAgent(agent.name)
    if (result.success && result.data) {
      editMode.value = true
      Object.assign(form, {
        name: result.data.name,
        description: result.data.description || '',
        system_prompt: result.data.system_prompt || '',
        tools: result.data.tools || [],
        model: result.data.model || ''
      })
      formModalVisible.value = true
      return
    }
  } catch (err) {
    console.error('获取 SubAgent 详情失败，回退使用列表数据:', err)
  }
  // 回退：使用列表数据
  editMode.value = true
  Object.assign(form, {
    name: agent.name,
    description: agent.description || '',
    system_prompt: agent.system_prompt || '',
    tools: agent.tools || [],
    model: agent.model || ''
  })
  formModalVisible.value = true
}

// 处理表单提交
const handleFormSubmit = async () => {
  try {
    // 校验
    if (!form.name?.trim()) {
      message.error('名称不能为空')
      return
    }
    if (!form.system_prompt?.trim()) {
      message.error('系统提示词不能为空')
      return
    }

    formLoading.value = true

    const data = {
      name: form.name.trim(),
      description: form.description || '',
      system_prompt: form.system_prompt,
      tools: form.tools || [],
      model: form.model || null
    }

    if (editMode.value) {
      const result = await subagentApi.updateSubAgent(form.name, data)
      if (result.success) {
        message.success('SubAgent 更新成功')
      } else {
        message.error(result.message || '更新失败')
        return
      }
    } else {
      const result = await subagentApi.createSubAgent(data)
      if (result.success) {
        message.success('SubAgent 创建成功')
      } else {
        message.error(result.message || '创建失败')
        return
      }
    }

    formModalVisible.value = false
    await fetchSubAgents()
  } catch (err) {
    console.error('操作失败:', err)
    message.error(err.message || '操作失败')
  } finally {
    formLoading.value = false
  }
}

// 确认删除 SubAgent
const confirmDeleteAgent = (agent) => {
  Modal.confirm({
    title: '确认删除 SubAgent',
    content: `确定要删除 SubAgent "${agent.name}" 吗？此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const result = await subagentApi.deleteSubAgent(agent.name)
        if (result.success) {
          message.success('SubAgent 删除成功')
          if (currentAgent.value?.name === agent.name) {
            currentAgent.value = null
          }
          await fetchSubAgents()
        } else {
          message.error(result.message || '删除失败')
        }
      } catch (err) {
        console.error('删除失败:', err)
        message.error(err.message || '删除失败')
      }
    }
  })
}

// 初始化
onMounted(() => {
  fetchSubAgents()
})

// 暴露方法给父组件
defineExpose({
  fetchSubAgents,
  showAddModal
})
</script>

<style lang="less" scoped>
@import '@/assets/css/extensions.less';

.model-override-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-selector-full {
  flex: 1;

  :deep(.model-select) {
    width: 100%;
  }
}
</style>
