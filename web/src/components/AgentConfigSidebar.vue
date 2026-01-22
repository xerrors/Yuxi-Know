<template>
  <div class="agent-config-sidebar" :class="{ open: isOpen }">
    <!-- 侧边栏头部 -->
    <div class="sidebar-header">
      <div class="header-center">
        <a-segmented v-model:value="activeTab" :options="segmentedOptions" />
      </div>
      <a-button type="text" size="small" @click="closeSidebar" class="close-btn">
        <X :size="16" />
      </a-button>
    </div>

    <!-- 侧边栏内容 -->
    <div class="sidebar-content">
      <div class="agent-info" v-if="selectedAgent">
        <div class="agent-basic-info">
          <p class="agent-description">{{ selectedAgent.description }}</p>
        </div>

        <!-- <a-divider /> -->

        <div v-if="selectedAgentId && configurableItems" class="config-form-content">
          <!-- 配置表单 -->
          <a-form :model="agentConfig" layout="vertical" class="config-form">
            <a-alert
              v-if="isEmptyConfig"
              type="warning"
              message="该智能体没有配置项"
              show-icon
              class="config-alert"
            />
            <a-alert
              v-if="!selectedAgent.has_checkpointer"
              type="error"
              message="该智能体没有配置 Checkpointer，功能无法正常使用"
              show-icon
              class="config-alert"
            />

            <!-- 统一显示所有配置项 -->
            <template v-for="(value, key) in configurableItems" :key="key">
              <a-form-item
                v-if="shouldShowConfig(key, value)"
                :label="getConfigLabel(key, value)"
                :name="key"
                class="config-item"
              >
                <p v-if="value.description" class="config-description">{{ value.description }}</p>

                <!-- <div>{{ value }}</div> -->
                <!-- 模型选择 -->
                <div v-if="value.template_metadata.kind === 'llm'" class="model-selector">
                  <ModelSelectorComponent
                    @select-model="(spec) => handleModelChange(key, spec)"
                    :model_spec="agentConfig[key] || ''"
                  />
                </div>

                <!-- 系统提示词 -->
                <div v-else-if="value.template_metadata.kind === 'prompt'" class="system-prompt-container">
                  <!-- 编辑模式 -->
                  <a-textarea
                    v-if="systemPromptEditMode"
                    :value="agentConfig[key]"
                    @update:value="(val) => agentStore.updateAgentConfig({ [key]: val })"
                    :rows="10"
                    :placeholder="getPlaceholder(key, value)"
                    class="system-prompt-input"
                    @blur="systemPromptEditMode = false"
                    ref="systemPromptTextarea"
                  />
                  <!-- 显示模式 -->
                  <div v-else class="system-prompt-display" @click="enterEditMode">
                    <div
                      class="system-prompt-content"
                      :class="{ 'is-placeholder': !agentConfig[key] }"
                    >
                      {{ agentConfig[key] || getPlaceholder(key, value) }}
                    </div>
                    <div class="edit-hint">点击编辑</div>
                  </div>
                </div>

                <!-- 工具选择 -->
                <!-- <div v-else-if="value.template_metadata.kind === 'tools'" class="tools-selector">
                  <div class="tools-summary">
                    <div class="tools-summary-info">
                      <span class="tools-count">已选择 {{ getSelectedCount(key) }} 个工具</span>
                      <a-button
                        type="link"
                        size="small"
                        @click="clearSelection(key)"
                        v-if="getSelectedCount(key) > 0"
                        class="clear-btn"
                      >
                        清空
                      </a-button>
                    </div>
                    <a-button
                      type="primary"
                      @click="openToolsModal"
                      class="select-tools-btn"
                      size="small"
                    >
                      选择工具
                    </a-button>
                  </div>
                  <div v-if="getSelectedCount(key) > 0" class="selected-tools-preview">
                    <a-tag
                      v-for="toolId in agentConfig[key]"
                      :key="toolId"
                      closable
                      @close="removeSelectedTool(toolId)"
                      class="tool-tag"
                    >
                      {{ getToolNameById(toolId) }}
                    </a-tag>
                  </div>
                </div> -->

                <!-- 布尔类型 -->
                <a-switch
                  v-else-if="typeof agentConfig[key] === 'boolean'"
                  :checked="agentConfig[key]"
                  @update:checked="(val) => agentStore.updateAgentConfig({ [key]: val })"
                />

                <!-- 单选 -->
                <a-select
                  v-else-if="
                    value?.options.length > 0 && (value?.type === 'str' || value?.type === 'select')
                  "
                  :value="agentConfig[key]"
                  @update:value="(val) => agentStore.updateAgentConfig({ [key]: val })"
                  class="config-select"
                >
                  <a-select-option v-for="option in value.options" :key="option" :value="option">
                    {{ option.label || option }}
                  </a-select-option>
                </a-select>

                <!-- 多选 -->
                <div
                  v-else-if="value?.options.length > 0 && value?.type === 'list'"
                  class="multi-select-cards"
                >
                  <div class="multi-select-label">
                    <span>已选择 {{ getSelectedCount(key) }} 项</span>
                    <a-button
                      type="link"
                      size="small"
                      class="clear-btn"
                      @click="clearSelection(key)"
                      v-if="getSelectedCount(key) > 0"
                    >
                      清空
                    </a-button>
                  </div>
                  <div class="options-grid">
                    <div
                      v-for="option in value.options"
                      :key="option"
                      class="option-card"
                      :class="{
                        selected: isOptionSelected(key, option),
                        unselected: !isOptionSelected(key, option)
                      }"
                      @click="toggleOption(key, option)"
                    >
                      <div class="option-content">
                        <span class="option-text">{{ option }}</span>
                        <div class="option-indicator">
                          <Check v-if="isOptionSelected(key, option)" :size="16" />
                          <Plus v-else :size="16" />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 数字 -->
                <a-input-number
                  v-else-if="value?.type === 'number'"
                  :value="agentConfig[key]"
                  @update:value="(val) => agentStore.updateAgentConfig({ [key]: val })"
                  :placeholder="getPlaceholder(key, value)"
                  class="config-input-number"
                />

                <!-- 滑块 -->
                <a-slider
                  v-else-if="value?.type === 'slider'"
                  :value="agentConfig[key]"
                  @update:value="(val) => agentStore.updateAgentConfig({ [key]: val })"
                  :min="value.min"
                  :max="value.max"
                  :step="value.step"
                  class="config-slider"
                />

                <!-- 其他类型 -->
                <a-input
                  v-else
                  :value="agentConfig[key]"
                  @update:value="(val) => agentStore.updateAgentConfig({ [key]: val })"
                  :placeholder="getPlaceholder(key, value)"
                  class="config-input"
                />
              </a-form-item>
            </template>
          </a-form>
        </div>
      </div>
    </div>

    <!-- 固定在底部的操作按钮 -->
    <div class="sidebar-footer" v-if="!isEmptyConfig && userStore.isAdmin">
      <div class="form-actions">
        <a-button
          type="primary"
          @click="saveConfig"
          class="save-btn"
          :class="{ changed: agentStore.hasConfigChanges }"
          :disabled="isSavingConfig"
        >
          保存
        </a-button>

        <a-tooltip :title="isCurrentDefault ? '当前已是默认配置' : '设为默认配置'">
          <a-button type="text" shape="circle" class="icon-btn" @click="setAsDefault">
            <Star
              :size="18"
              :fill="isCurrentDefault ? 'currentColor' : 'none'"
              :class="{ 'is-default': isCurrentDefault }"
            />
          </a-button>
        </a-tooltip>

        <a-tooltip title="删除配置">
          <a-button
            type="text"
            shape="circle"
            danger
            class="icon-btn"
            @click="confirmDeleteConfig"
            :disabled="isDeletingConfig"
          >
            <Trash2 :size="18" />
          </a-button>
        </a-tooltip>
      </div>
    </div>

    <!-- 工具选择弹窗 -->
    <a-modal
      v-model:open="toolsModalOpen"
      title="选择工具"
      :width="800"
      :footer="null"
      :maskClosable="false"
      class="tools-modal"
    >
      <div class="tools-modal-content">
        <div class="tools-search">
          <a-input
            v-model:value="toolsSearchText"
            placeholder="搜索工具..."
            allow-clear
            class="search-input"
          >
            <template #prefix>
              <Search :size="16" class="search-icon" />
            </template>
          </a-input>
        </div>

        <div class="tools-list">
          <div
            v-for="tool in filteredTools"
            :key="tool.id"
            class="tool-item"
            :class="{ selected: selectedTools.includes(tool.id) }"
            @click="toggleToolSelection(tool.id)"
          >
            <div class="tool-content">
              <div class="tool-header">
                <span class="tool-name">{{ tool.name }}</span>
                <div class="tool-indicator">
                  <Check v-if="selectedTools.includes(tool.id)" :size="16" />
                  <Plus v-else :size="16" />
                </div>
              </div>
              <div class="tool-description">{{ tool.description }}</div>
            </div>
          </div>
        </div>

        <div class="tools-modal-footer">
          <div class="selected-count">已选择 {{ selectedTools.length }} 个工具</div>
          <div class="modal-actions">
            <a-button @click="cancelToolsSelection">取消</a-button>
            <a-button type="primary" @click="confirmToolsSelection">确认</a-button>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { X, Save, Trash2, Check, Plus, Search, Star } from 'lucide-vue-next'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'

// Props
const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

// Emits
const emit = defineEmits(['close'])

// Store 管理
const agentStore = useAgentStore()
const userStore = useUserStore()
const {
  availableTools,
  selectedAgent,
  selectedAgentId,
  selectedAgentConfigId,
  selectedConfigSummary,
  agentConfigs,
  agentConfig,
  configurableItems
} = storeToRefs(agentStore)

// console.log(availableTools.value)

// 本地状态
const toolsModalOpen = ref(false)
const selectedTools = ref([])
const toolsSearchText = ref('')
const systemPromptEditMode = ref(false)
const activeTab = ref('basic')

const isEmptyConfig = computed(() => {
  return !selectedAgentId.value || Object.keys(configurableItems.value).length === 0
})

const isCurrentDefault = computed(() => {
  return !!selectedConfigSummary.value?.is_default
})

const isSavingConfig = ref(false)
const isDeletingConfig = ref(false)

const hasOtherConfigs = computed(() => {
  if (isEmptyConfig.value) return false
  return Object.entries(configurableItems.value).some(([key, value]) => {
    const isBasic = value.template_metadata?.kind === 'prompt' || value.template_metadata?.kind === 'llm'
    const isTools =
      value.template_metadata?.kind === 'mcps' ||
      value.template_metadata?.kind === 'knowledges' ||
      value.template_metadata?.kind === 'tools'

    return !isBasic && !isTools
  })
})

const segmentedOptions = computed(() => {
  const options = [
    { label: '基础', value: 'basic' },
    { label: '工具', value: 'tools' }
  ]

  if (hasOtherConfigs.value) {
    options.push({ label: '其他', value: 'other' })
  }

  return options
})

const filteredTools = computed(() => {
  const toolsList = availableTools.value ? Object.values(availableTools.value) : []
  if (!toolsSearchText.value) {
    return toolsList
  }
  const searchLower = toolsSearchText.value.toLowerCase()
  return toolsList.filter(
    (tool) =>
      tool.name.toLowerCase().includes(searchLower) ||
      tool.description.toLowerCase().includes(searchLower)
  )
})

// 方法
const shouldShowConfig = (key, value) => {
  const isBasic = value.template_metadata?.kind === 'prompt' || value.template_metadata?.kind === 'llm'
  const isTools =
    value.template_metadata?.kind === 'mcps' ||
    value.template_metadata?.kind === 'knowledges' ||
    value.template_metadata?.kind === 'tools'

  if (activeTab.value === 'basic') {
    // 基础：System Prompt, LLM Model
    return isBasic
  } else if (activeTab.value === 'tools') {
    // 工具：Tools, MCPs, Knowledges
    return isTools
  } else {
    // 其他：剩余所有配置
    return !isBasic && !isTools
  }
}

const closeSidebar = () => {
  emit('close')
}

const getConfigLabel = (key, value) => {
  // console.log(configurableItems)
  if (value.description && value.name !== key) {
    return `${value.name}`
    // return `${value.name}（${key}）`;
  }
  return key
}

const getPlaceholder = (key, value) => {
  return `（默认: ${value.default}）`
}

const handleModelChange = (key, spec) => {
  if (typeof spec !== 'string' || !spec) return
  agentStore.updateAgentConfig({
    [key]: spec
  })
}

// 多选相关方法
const ensureArray = (key) => {
  const config = agentConfig.value || {}
  if (!config[key] || !Array.isArray(config[key])) {
    return []
  }
  return config[key]
}

const isOptionSelected = (key, option) => {
  const currentOptions = ensureArray(key)
  return currentOptions.includes(option)
}

const getSelectedCount = (key) => {
  const currentOptions = ensureArray(key)
  return currentOptions.length
}

const toggleOption = (key, option) => {
  const currentOptions = [...ensureArray(key)]
  const index = currentOptions.indexOf(option)

  if (index > -1) {
    currentOptions.splice(index, 1)
  } else {
    currentOptions.push(option)
  }

  agentStore.updateAgentConfig({
    [key]: currentOptions
  })
}

const clearSelection = (key) => {
  agentStore.updateAgentConfig({
    [key]: []
  })
}

// 工具相关方法
const getToolNameById = (toolId) => {
  const toolsList = availableTools.value ? Object.values(availableTools.value) : []
  const tool = toolsList.find((t) => t.id === toolId)
  return tool ? tool.name : toolId
}

const openToolsModal = async () => {
  console.log('availableTools.value', availableTools.value)
  try {
    // 强制刷新智能体详情以获取最新工具列表
    if (selectedAgentId.value) {
      await agentStore.fetchAgentDetail(selectedAgentId.value, true)
    }
    selectedTools.value = [...(agentConfig.value?.tools || [])]
    toolsModalOpen.value = true
  } catch (error) {
    console.error('打开工具选择弹窗失败:', error)
    message.error('打开工具选择弹窗失败')
  }
}

const toggleToolSelection = (toolId) => {
  const index = selectedTools.value.indexOf(toolId)
  if (index > -1) {
    selectedTools.value.splice(index, 1)
  } else {
    selectedTools.value.push(toolId)
  }
}

const removeSelectedTool = (toolId) => {
  const currentTools = [...(agentConfig.value?.tools || [])]
  const index = currentTools.indexOf(toolId)
  if (index > -1) {
    currentTools.splice(index, 1)
    agentStore.updateAgentConfig({
      tools: currentTools
    })
  }
}

const confirmToolsSelection = () => {
  agentStore.updateAgentConfig({
    tools: [...selectedTools.value]
  })
  toolsModalOpen.value = false
  toolsSearchText.value = ''
}

const cancelToolsSelection = () => {
  toolsModalOpen.value = false
  toolsSearchText.value = ''
  selectedTools.value = []
}

// 系统提示词编辑相关方法
const enterEditMode = () => {
  systemPromptEditMode.value = true
  // 使用 nextTick 确保 DOM 更新后再聚焦
  nextTick(() => {
    const textarea = document.querySelector('.system-prompt-input')
    if (textarea) {
      textarea.focus()
    }
  })
}

// 验证和过滤配置项
const validateAndFilterConfig = () => {
  const validatedConfig = { ...agentConfig.value }
  const configItems = configurableItems.value

  // 遍历所有配置项
  Object.keys(configItems).forEach((key) => {
    const configItem = configItems[key]
    const currentValue = validatedConfig[key]

    // 检查工具配置
    if (configItem.template_metadata?.kind === 'tools' && Array.isArray(currentValue)) {
      const availableToolIds = availableTools.value
        ? Object.values(availableTools.value).map((tool) => tool.id)
        : []
      validatedConfig[key] = currentValue.filter((toolId) => availableToolIds.includes(toolId))

      if (validatedConfig[key].length !== currentValue.length) {
        console.warn(`工具配置 ${key} 中包含无效的工具ID，已自动过滤`)
      }
    }

    // 检查多选配置项 (type === 'list' 且有 options)
    else if (configItem.type === 'list' && configItem.options && Array.isArray(currentValue)) {
      const validOptions = configItem.options
      validatedConfig[key] = currentValue.filter((value) => validOptions.includes(value))

      if (validatedConfig[key].length !== currentValue.length) {
        console.warn(`配置项 ${key} 中包含无效的选项，已自动过滤`)
      }
    }
  })

  return validatedConfig
}

// 配置保存和重置
const saveConfig = async () => {
  if (!selectedAgentId.value) {
    message.error('没有选择智能体')
    return
  }

  if (!agentStore.hasConfigChanges) return

  try {
    isSavingConfig.value = true
    // 验证和过滤配置
    const validatedConfig = validateAndFilterConfig()

    // 如果配置有变化，先更新到store
    if (JSON.stringify(validatedConfig) !== JSON.stringify(agentConfig.value)) {
      agentStore.updateAgentConfig(validatedConfig)
      message.info('检测到无效配置项，已自动过滤')
    }

    await agentStore.saveAgentConfig()
    message.success('配置已保存到服务器')
  } catch (error) {
    console.error('保存配置到服务器出错:', error)
    message.error('保存配置到服务器失败')
  } finally {
    isSavingConfig.value = false
  }
}

const setAsDefault = async () => {
  if (!selectedAgentId.value || !selectedAgentConfigId.value) return
  try {
    await agentStore.setSelectedAgentConfigDefault()
    message.success('已设为默认配置')
  } catch (error) {
    console.error('设置默认配置出错:', error)
    message.error('设置默认配置失败')
  }
}

const confirmDeleteConfig = async () => {
  if (!selectedAgentId.value || !selectedAgentConfigId.value) return

  const currentName = selectedConfigSummary.value?.name || '当前配置'
  const list = agentConfigs.value[selectedAgentId.value] || []
  const content =
    list.length <= 1
      ? `将删除「${currentName}」。删除后系统会自动创建一个新的默认配置。`
      : `将删除「${currentName}」。`

  Modal.confirm({
    title: '确认删除配置？',
    content,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      isDeletingConfig.value = true
      try {
        await agentStore.deleteSelectedAgentConfigProfile()
        message.success('配置已删除')
      } catch (error) {
        console.error('删除配置出错:', error)
        message.error('删除配置失败')
      } finally {
        isDeletingConfig.value = false
      }
    }
  })
}

const resetConfig = async () => {
  if (!selectedAgentId.value) {
    message.error('没有选择智能体')
    return
  }

  try {
    agentStore.resetAgentConfig()
    message.info('配置已重置')
  } catch (error) {
    console.error('重置配置出错:', error)
    message.error('重置配置失败')
  }
}
</script>

<style lang="less" scoped>
@padding-bottom: 0px;
.agent-config-sidebar {
  position: relative;
  width: 0;
  height: 100vh;
  background: var(--gray-0);
  border-left: 1px solid var(--gray-200);
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;

  &.open {
    width: 400px;
  }

  .sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    border-bottom: 1px solid var(--gray-200);
    background: var(--gray-0);
    flex-shrink: 0;
    min-width: 400px;
    height: 56px;

    .header-center {
      flex: 1;
      display: flex;
      justify-content: center;
    }

    .close-btn {
      color: var(--gray-600);
      border: none;
      padding: 4px;

      &:hover {
        color: var(--gray-900);
        background: var(--gray-100);
      }
    }
  }

  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 8px 12px;
    min-width: 400px;
    padding-bottom: @padding-bottom;

    .agent-info {
      .agent-basic-info {
        .agent-description {
          margin: 0 0 12px 0;
          font-size: 14px;
          color: var(--gray-700);
          line-height: 1.5;
        }
      }
    }

    .config-form-content {
      margin-bottom: 20px;
      .config-form {
        .config-alert {
          margin-bottom: 16px;
        }

        .config-item {
          background-color: var(--gray-25);
          padding: 12px;
          border-radius: 8px;
          border: 1px solid var(--gray-100);
          // box-shadow: 0px 0px 2px var(--shadow-3);

          :deep(label.form_item_model) {
            font-weight: 600;
          }

          .config-description {
            margin: 4px 0 8px 0;
            font-size: 12px;
            color: var(--gray-600);
            line-height: 1.4;
          }

          .model-selector {
            width: 100%;
          }

          .system-prompt-input {
            resize: vertical;
            background: var(--gray-50);
            border: 1px solid var(--gray-200);
            padding: 8px 12px;

            &:focus {
              outline: none;
            }
          }

          .system-prompt-container {
            width: 100%;
          }

          .system-prompt-display {
            min-height: 60px;
            border-radius: 6px;
            cursor: pointer;
            position: relative;
            transition: all 0.2s ease;

            &:hover {
              border-color: var(--main-color);
              background: var(--gray-25);

              .edit-hint {
                opacity: 1;
              }
            }

            .system-prompt-content {
              white-space: pre-wrap;
              word-break: break-word;
              line-height: 1.5;
              color: var(--gray-900);
              font-size: 14px;
              //  min-height: 100px;

              &.is-placeholder {
                color: var(--gray-400);
                font-style: italic;
              }

              &:empty::before {
                content: attr(data-placeholder);
                color: var(--gray-400);
              }
            }

            .edit-hint {
              position: absolute;
              top: -32px;
              right: 0px;
              font-size: 12px;
              color: var(--main-800);
              opacity: 0;
              transition: opacity 0.2s ease;
              background: var(--gray-0);
              padding: 2px 6px;
              border-radius: 4px;
            }
          }

          .config-select,
          .config-input,
          .config-input-number {
            width: 100%;
          }

          .config-slider {
            width: 100%;
          }
        }
      }
    }
  }

  .sidebar-footer {
    padding: 8px 12px;
    border-top: 1px solid var(--gray-100);
    background: var(--gray-0);
    // min-width: 400px;
    z-index: 10;
    flex-shrink: 0; // Ensure footer doesn't shrink

    .form-actions {
      display: flex;
      flex-direction: row;
      gap: 12px;
      justify-content: space-between;
      align-items: center;

      .icon-btn {
        width: 36px;
        height: 36px;
        border-radius: 6px;
        color: var(--gray-600);
        border: 1px solid var(--gray-200);
        background: var(--gray-0);
        display: flex;
        justify-content: center;
        align-items: center;

        &:hover:not(:disabled) {
          color: var(--main-600);
          border-color: var(--main-200);
          background: var(--main-10);
        }

        &.is-default {
          // color: var(--main-500);
          color: var(--color-warning-500);
        }

        &[danger]:hover:not(:disabled) {
          color: var(--error-600);
          border-color: var(--error-200);
          background: var(--error-10);
        }

        &:disabled {
          cursor: not-allowed;
          background: transparent;
          color: var(--gray-400);
          border-color: var(--gray-200);

          &.is-default {
            opacity: 1;
          }
        }
      }

      .save-btn {
        flex: 1;
        height: 36px;
        border-radius: 6px;
        font-weight: 500;
        font-size: 14px;
        background-color: var(--gray-100);
        border: 1px solid var(--gray-200);
        color: var(--gray-600);
        transition: all 0.2s ease;

        &.changed {
          background-color: var(--main-color);
          color: var(--gray-0);
          border-color: var(--main-color);
        }

        &:hover:not(:disabled) {
          opacity: 0.9;
        }

        &:disabled {
          cursor: not-allowed;
          background-color: var(--gray-100);
          border-color: var(--gray-200);
          color: var(--gray-400);
        }
      }
    }
  }
}

// 工具选择器样式
.tools-selector {
  .tools-summary {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 12px;
    background: var(--gray-20);
    border-radius: 8px;
    border: 1px solid var(--gray-200);
    margin-bottom: 8px;

    .tools-summary-info {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--gray-900);

      .tools-count {
        color: var(--gray-900);
        font-weight: 500;
      }
    }

    .select-tools-btn {
      background: var(--main-color);
      border: none;
      border-radius: 4px;
      height: 28px;
      font-size: 12px;
      font-weight: 500;

      &:hover {
        background: var(--main-color);
        opacity: 0.9;
      }
    }
  }

  .selected-tools-preview {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;

    .tool-tag {
      margin: 0;
      padding: 4px 8px;
      border-radius: 12px;
      background: var(--gray-50);
      border: 1px solid var(--gray-200);
      color: var(--gray-900);
      font-size: 12px;

      :deep(.anticon-close) {
        color: var(--gray-600);
        margin-left: 4px;

        &:hover {
          color: var(--gray-900);
        }
      }
    }
  }
}

// 多选卡片样式
.multi-select-cards {
  .multi-select-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    font-size: 12px;
    color: var(--gray-600);
  }

  .options-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .option-card {
    border: 1px solid var(--gray-300);
    border-radius: 8px;
    padding: 8px 12px;
    cursor: pointer;
    transition: all 0.2s ease;
    background: var(--gray-0);

    &:hover {
      border-color: var(--main-color);
    }

    &.selected {
      border-color: var(--main-color);
      background: var(--main-10);

      .option-indicator {
        color: var(--main-color);
      }

      .option-text {
        color: var(--main-color);
        font-weight: 500;
      }
    }

    &.unselected {
      .option-indicator {
        color: var(--gray-400);
      }

      .option-text {
        color: var(--gray-700);
      }
    }

    .option-content {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;

      .option-text {
        flex: 1;
        font-size: 13px;
        line-height: 1.4;
      }

      .option-indicator {
        flex-shrink: 0;
        font-size: 14px;
      }
    }
  }
}

// 工具选择弹窗样式
.tools-modal {
  .tools-modal-content {
    .tools-search {
      margin-bottom: 16px;

      .search-input {
        border-radius: 8px;
        border: 1px solid var(--gray-300);
        height: 36px;
        font-size: 14px;
        transition: all 0.2s ease;
        background: var(--gray-0);

        .search-icon {
          color: var(--gray-500);
          font-size: 16px;
        }

        &:focus-within {
          border-color: var(--main-color);
          box-shadow: 0 0 0 2px rgba(var(--main-color-rgb), 0.1);

          .search-icon {
            color: var(--main-color);
          }
        }

        &:hover {
          border-color: var(--gray-400);
        }
      }
    }

    .tools-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      max-height: max(60vh, 800px);
      overflow-y: auto;
      border-radius: 8px;
      margin-bottom: 16px;

      // 在小屏幕下调整为单列布局
      @media (max-width: 480px) {
        grid-template-columns: 1fr;
      }

      &::-webkit-scrollbar {
        width: 6px;
      }

      &::-webkit-scrollbar-track {
        background: var(--gray-100);
        border-radius: 3px;
      }

      &::-webkit-scrollbar-thumb {
        background: var(--gray-400);
        border-radius: 3px;
      }

      &::-webkit-scrollbar-thumb:hover {
        background: var(--gray-500);
      }

      .tool-item {
        padding: 12px 16px;
        border-bottom: none;
        cursor: pointer;
        transition: all 0.2s ease;
        border-radius: 8px;
        margin-bottom: 4px;
        background: var(--gray-0);
        border: 1px solid var(--gray-200);

        &:hover {
          border-color: var(--gray-300);
          background: var(--gray-20);
        }
        .tool-content {
          .tool-header {
            display: flex;
            align-items: center;
            margin-bottom: 6px;
            gap: 8px;

            .tool-name {
              font-size: 14px;
              font-weight: 500;
              color: var(--gray-900);
              line-height: 1.3;
              flex: 1;
            }

            .tool-indicator {
              color: var(--gray-400);
              font-size: 16px;
              transition: all 0.2s ease;
              flex-shrink: 0;
            }
          }

          .tool-description {
            font-size: 12px;
            color: var(--gray-600);
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
          }
        }

        &.selected {
          background: var(--main-50);
          border-color: var(--main-200);

          .tool-content {
            .tool-name {
              color: var(--main-800);
            }
            .tool-indicator {
              color: var(--main-800);
            }
          }
          .tool-description {
            color: var(--gray-900);
          }
        }
      }
    }

    .tools-modal-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 16px;
      border-top: 1px solid var(--gray-200);

      .selected-count {
        font-size: 14px;
        color: var(--gray-700);
        font-weight: 500;
        padding: 6px 12px;
        background: var(--gray-50);
        border-radius: 8px;
        border: 1px solid var(--gray-200);
      }

      .modal-actions {
        display: flex;
        gap: 12px;

        :deep(.ant-btn) {
          border-radius: 8px;
          height: 36px;
          font-size: 14px;
          font-weight: 500;
          padding: 0 16px;
          transition: all 0.2s ease;

          &.ant-btn-default {
            border: 1px solid var(--gray-300);
            color: var(--gray-700);
            background: var(--gray-0);

            &:hover {
              border-color: var(--main-color);
              color: var(--main-color);
            }
          }

          &.ant-btn-primary {
            background: var(--main-color);
            border: none;
            color: var(--gray-0);

            &:hover {
              background: var(--main-color);
              opacity: 0.9;
            }
          }
        }
      }
    }
  }
}

.clear-btn {
  padding: 0;
  height: auto;
  font-size: 12px;
  font-weight: 600;
  color: var(--main-700);

  &:hover {
    color: var(--main-800);
  }
}

// 响应式适配
@media (max-width: 768px) {
  .agent-config-sidebar.open {
    width: 100%;
  }

  .sidebar-header,
  .sidebar-content {
    min-width: 100% !important;
  }
}
</style>
