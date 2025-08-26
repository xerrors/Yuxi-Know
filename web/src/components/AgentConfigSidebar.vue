<template>
  <div class="agent-config-sidebar" :class="{ 'open': isOpen }">
    <!-- 侧边栏头部 -->
    <div class="sidebar-header">
      <div class="sidebar-title">
        <SettingOutlined class="title-icon" />
        <span>{{ selectedAgent?.name || '未选择智能体' }} 配置</span>
      </div>
      <a-button
        type="text"
        size="small"
        @click="closeSidebar"
        class="close-btn"
      >
        <CloseOutlined />
      </a-button>
    </div>

    <!-- 侧边栏内容 -->
    <div class="sidebar-content">
      <div class="agent-info" v-if="selectedAgent">
        <div class="agent-basic-info">
          <p class="agent-description">{{ selectedAgent.description }}</p>
          <!-- <div class="debug-toggle" v-if="selectedAgent.name">
            <span class="debug-text">调试信息</span>
            <a-switch v-model:checked="debugMode" size="small" />
          </div>
          <pre v-if="debugMode && selectedAgent.name" class="debug-info">{{ selectedAgent }}</pre> -->
        </div>

        <a-divider />

        <div v-if="selectedAgentId && configSchema" class="config-form-content">
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
                :label="getConfigLabel(key, value)"
                :name="key"
                class="config-item"
              >
                <p v-if="value.description" class="config-description">{{ value.description }}</p>

                <!-- 模型选择 -->
                <div v-if="key === 'model'" class="model-selector">
                  <ModelSelectorComponent
                    @select-model="handleModelChange"
                    :model_name="agentConfig[key] ? agentConfig[key].split('/').slice(1).join('/') : ''"
                    :model_provider="agentConfig[key] ? agentConfig[key].split('/')[0] : ''"
                  />
                </div>

                <!-- 系统提示词 -->
                <a-textarea
                  v-else-if="key === 'system_prompt'"
                  :value="agentConfig[key]"
                  @update:value="(val) => agentStore.updateAgentConfig({ [key]: val })"
                  :rows="10"
                  :placeholder="getPlaceholder(key, value)"
                  class="system-prompt-input"
                />

                <!-- 工具选择 -->
                <div v-else-if="key === 'tools'" class="tools-selector">
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
                </div>

                <!-- 布尔类型 -->
                <a-switch
                  v-else-if="typeof agentConfig[key] === 'boolean'"
                  :checked="agentConfig[key]"
                  @update:checked="(val) => agentStore.updateAgentConfig({ [key]: val })"
                />

                <!-- 单选 -->
                <a-select
                  v-else-if="value?.options && (value?.type === 'str' || value?.type === 'select')"
                  :value="agentConfig[key]"
                  @update:value="(val) => agentStore.updateAgentConfig({ [key]: val })"
                  class="config-select"
                >
                  <a-select-option v-for="option in value.options" :key="option" :value="option">
                    {{ option.label || option }}
                  </a-select-option>
                </a-select>

                <!-- 多选 -->
                <div v-else-if="value?.options && value?.type === 'list'" class="multi-select-cards">
                  <div class="multi-select-label">
                    <span>已选择 {{ getSelectedCount(key) }} 项</span>
                    <a-button
                      type="link"
                      size="small"
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
                        'selected': isOptionSelected(key, option),
                        'unselected': !isOptionSelected(key, option)
                      }"
                      @click="toggleOption(key, option)"
                    >
                      <div class="option-content">
                        <span class="option-text">{{ option }}</span>
                        <div class="option-indicator">
                          <CheckCircleOutlined v-if="isOptionSelected(key, option)" />
                          <PlusCircleOutlined v-else />
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

      <!-- 固定在底部的操作按钮 -->
      <div class="sidebar-footer" v-if="!isEmptyConfig">
        <div class="form-actions">
          <a-button @click="saveConfig" class="save-btn" :class="{'changed': agentStore.hasConfigChanges}">
            保存配置
          </a-button>
          <!-- TODO：BUG 目前有 bug 暂时不展示 -->
          <!-- <a-button @click="resetConfig" class="reset-btn">
            重置
          </a-button> -->
        </div>
      </div>
    </div>

    <!-- 工具选择弹窗 -->
    <a-modal
      v-model:open="toolsModalOpen"
      title="选择工具"
      :width="600"
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
              <SearchOutlined class="search-icon" />
            </template>
          </a-input>
        </div>

        <div class="tools-list">
          <div
            v-for="tool in filteredTools"
            :key="tool.id"
            class="tool-item"
            :class="{ 'selected': selectedTools.includes(tool.id) }"
            @click="toggleToolSelection(tool.id)"
          >
            <div class="tool-content">
              <div class="tool-header">
                <span class="tool-name">{{ tool.name }}</span>
                <div class="tool-indicator">
                  <CheckCircleOutlined v-if="selectedTools.includes(tool.id)" />
                  <PlusCircleOutlined v-else />
                </div>
              </div>
              <div class="tool-description">{{ tool.description }}</div>
            </div>
          </div>
        </div>

        <div class="tools-modal-footer">
          <div class="selected-count">
            已选择 {{ selectedTools.length }} 个工具
          </div>
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
import { ref, computed, watch } from 'vue';
import {
  SettingOutlined,
  CloseOutlined,
  CheckCircleOutlined,
  PlusCircleOutlined,
  SearchOutlined
} from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue';
import { useAgentStore } from '@/stores/agent';
import { storeToRefs } from 'pinia';

// Props
const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  }
});

// Emits
const emit = defineEmits([
  'close'
]);

// Store 管理
const agentStore = useAgentStore();
const {
  availableTools,
  selectedAgent,
  selectedAgentId,
  agentConfig
} = storeToRefs(agentStore);

// console.log(availableTools.value)

// 本地状态
const debugMode = ref(false);
const toolsModalOpen = ref(false);
const selectedTools = ref([]);
const toolsSearchText = ref('');

// 计算属性
const configSchema = computed(() => selectedAgent.value?.config_schema || {});

const configurableItems = computed(() => {
  const items = configSchema.value.configurable_items || {};
  // 遍历所有的配置项，将所有的 x_oap_ui_config 的层级提升到上一层
  Object.keys(items).forEach(key => {
    const item = items[key];
    if (item.x_oap_ui_config) {
      items[key] = { ...item, ...item.x_oap_ui_config };
      delete items[key].x_oap_ui_config;
    }
  });
  return items;
});

const isEmptyConfig = computed(() => {
  return !selectedAgentId.value || Object.keys(configurableItems.value).length === 0;
});

const filteredTools = computed(() => {
  const toolsList = availableTools.value ? Object.values(availableTools.value) : [];
  if (!toolsSearchText.value) {
    return toolsList;
  }
  const searchLower = toolsSearchText.value.toLowerCase();
  return toolsList.filter(tool =>
    tool.name.toLowerCase().includes(searchLower) ||
    tool.description.toLowerCase().includes(searchLower)
  );
});

// 方法
const closeSidebar = () => {
  emit('close');
};

const toggleDebugMode = () => {
  debugMode.value = !debugMode.value;
};

const getConfigLabel = (key, value) => {
  // console.log(configurableItems)
  if (value.description && value.name !== key) {
    return `${value.name}（${key}）`;
  }
  return key;
};

const getPlaceholder = (key, value) => {
  return `（默认: ${value.default}）`;
};

const handleModelChange = (data) => {
  agentStore.updateAgentConfig({
    model: `${data.provider}/${data.name}`
  });
};

// 多选相关方法
const ensureArray = (key) => {
  const config = agentConfig.value || {};
  if (!config[key] || !Array.isArray(config[key])) {
    return [];
  }
  return config[key];
};

const isOptionSelected = (key, option) => {
  const currentOptions = ensureArray(key);
  return currentOptions.includes(option);
};

const getSelectedCount = (key) => {
  const currentOptions = ensureArray(key);
  return currentOptions.length;
};

const toggleOption = (key, option) => {
  const currentOptions = [...ensureArray(key)];
  const index = currentOptions.indexOf(option);

  if (index > -1) {
    currentOptions.splice(index, 1);
  } else {
    currentOptions.push(option);
  }

  agentStore.updateAgentConfig({
    [key]: currentOptions
  });
};

const clearSelection = (key) => {
  agentStore.updateAgentConfig({
    [key]: []
  });
};

// 工具相关方法
const getToolNameById = (toolId) => {
  const toolsList = availableTools.value ? Object.values(availableTools.value) : [];
  const tool = toolsList.find(t => t.id === toolId);
  return tool ? tool.name : toolId;
};

const loadAvailableTools = async () => {
  try {
    await agentStore.fetchTools();
  } catch (error) {
    console.error('加载工具列表失败:', error);
  }
};

const openToolsModal = async () => {
  try {
    if (!availableTools.value || Object.keys(availableTools.value).length === 0) {
      await loadAvailableTools();
    }
    selectedTools.value = [...(agentConfig.value?.tools || [])];
    toolsModalOpen.value = true;
  } catch (error) {
    console.error('打开工具选择弹窗失败:', error);
    message.error('打开工具选择弹窗失败');
  }
};

const toggleToolSelection = (toolId) => {
  const index = selectedTools.value.indexOf(toolId);
  if (index > -1) {
    selectedTools.value.splice(index, 1);
  } else {
    selectedTools.value.push(toolId);
  }
};

const removeSelectedTool = (toolId) => {
  const currentTools = [...(agentConfig.value?.tools || [])];
  const index = currentTools.indexOf(toolId);
  if (index > -1) {
    currentTools.splice(index, 1);
    agentStore.updateAgentConfig({
      tools: currentTools
    });
  }
};

const confirmToolsSelection = () => {
  agentStore.updateAgentConfig({
    tools: [...selectedTools.value]
  });
  toolsModalOpen.value = false;
  toolsSearchText.value = '';
};

const cancelToolsSelection = () => {
  toolsModalOpen.value = false;
  toolsSearchText.value = '';
  selectedTools.value = [];
};

// 配置保存和重置
const saveConfig = async () => {
  if (!selectedAgentId.value) {
    message.error('没有选择智能体');
    return;
  }

  try {
    await agentStore.saveAgentConfig();
    message.success('配置已保存到服务器');
  } catch (error) {
    console.error('保存配置到服务器出错:', error);
    message.error('保存配置到服务器失败');
  }
};

const resetConfig = async () => {
  if (!selectedAgentId.value) {
    message.error('没有选择智能体');
    return;
  }

  try {
    agentStore.resetAgentConfig();
    message.info('配置已重置');
  } catch (error) {
    console.error('重置配置出错:', error);
    message.error('重置配置失败');
  }
};

// 监听器
watch(() => props.isOpen, (newVal) => {
  if (newVal && (!availableTools.value || Object.keys(availableTools.value).length === 0)) {
    loadAvailableTools();
  }
});
</script>

<style lang="less" scoped>

@padding-bottom: 40px;
.agent-config-sidebar {
  position: relative;
  width: 0;
  height: 100vh;
  background: white;
  border-left: 1px solid #e8e8e8;
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
    padding: 10px 20px;
    border-bottom: 1px solid var(--gray-200);
    background: #fff;
    flex-shrink: 0;
    min-width: 400px;

    .sidebar-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 15px;
      font-weight: 600;
      color: var(--gray-900);

      .title-icon {
        color: var(--main-color);
      }
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

        .debug-toggle {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 0;
          cursor: pointer;

          .debug-text {
            font-size: 13px;
            color: var(--gray-600);
          }
        }

        .debug-info {
          margin-top: 12px;
          padding: 12px;
          background: var(--gray-50);
          border-radius: 6px;
          font-size: 12px;
          color: var(--gray-700);
          max-height: 200px;
          overflow-y: auto;
        }
      }
    }

    .sidebar-footer {
      position: sticky;
      bottom: 16px;
      padding: 12px 0;
      border-top: 1px solid var(--gray-200);
      background: #fff;
      // min-width: 400px;
      z-index: 10;

      .form-actions {
        display: flex;
        gap: 12px;
        justify-content: space-between;

        .save-btn {
          flex: 1;
          background-color: var(--gray-100);
          border: none;
          border-radius: 6px;
          font-weight: 500;
          font-size: 14px;

          &.changed {
            background-color: var(--main-color);
            color: #fff;
          }

          &:hover {
            opacity: 0.9;
          }
        }

        .reset-btn {
          flex: 1;
          border: 1px solid var(--gray-300);
          border-radius: 6px;
          color: var(--gray-700);
          font-size: 14px;

          &:hover {
            border-color: var(--main-color);
            color: var(--main-color);
          }
        }
      }
    }

    .config-form-content {
      .config-form {
        .config-alert {
          margin-bottom: 16px;
        }

        .config-item {
          margin-bottom: 20px;

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
}


// 工具选择器样式
.tools-selector {
  .tools-summary {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 12px;
    background: var(--gray-50);
    border-radius: 8px;
    border: 1px solid var(--gray-200);
    margin-bottom: 8px;

    .tools-summary-info {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--gray-700);

      .tools-count {
        color: var(--gray-900);
        font-weight: 500;
      }

      .clear-btn {
        padding: 0;
        height: auto;
        font-size: 12px;
      }
    }

    .select-tools-btn {
      background: var(--main-color);
      border: none;
      border-radius: 6px;
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
      border-radius: 4px;
      background: var(--gray-100);
      border: 1px solid var(--gray-300);
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
    border-radius: 6px;
    padding: 10px 12px;
    cursor: pointer;
    transition: all 0.2s ease;
    background: white;

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
  :deep(.ant-modal-content) {
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    border: 1px solid var(--gray-200);
  }

  :deep(.ant-modal-header) {
    background: white;
    border-bottom: 1px solid var(--gray-200);
    padding: 16px 20px;

    .ant-modal-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--gray-900);
    }
  }

  :deep(.ant-modal-body) {
    padding: 20px;
    background: white;
  }

  .tools-modal-content {
    .tools-search {
      margin-bottom: 16px;

      .search-input {
        border-radius: 8px;
        border: 1px solid var(--gray-300);
        height: 36px;
        font-size: 14px;
        transition: all 0.2s ease;
        background: white;

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
      background: white;

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
        background: white;
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
          background: var(--main-30);
          // border-color: var(--main-color);

          .tool-content {
            .tool-name {
              color: var(--main-color);
            }
            .tool-indicator {
              color: var(--main-color);
            }
          }
          .tool-description {
            color: var(--gray-700);
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
            background: white;

            &:hover {
              border-color: var(--main-color);
              color: var(--main-color);
            }
          }

          &.ant-btn-primary {
            background: var(--main-color);
            border: none;
            color: white;

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

// 响应式适配
@media (max-width: 768px) {
  .agent-config-sidebar.open {
    width: 100vw;
  }
}
</style>