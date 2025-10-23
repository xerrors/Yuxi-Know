<template>
  <div>
    <a-alert message="自定义模型在 0.3.x 的稳定版中移除，只能通过修改 src/config/static/models.py 来添加模型和供应商。" type="warning" />
    <br>
    <div class="model-provider-card configured-provider" v-for="(item, key) in modelKeys" :key="key">
      <div class="card-header" @click="toggleExpand(item)">
        <div :class="{'model-icon': true, 'available': modelStatus[item]}">
          <img :src="modelIcons[item] || modelIcons.default" alt="模型图标">
        </div>
        <div class="model-title-container">
          <h3>{{ modelNames[item].name }}</h3>
        </div>
        <a-button
          type="text"
          class="expand-button"
          @click.stop="openProviderConfig(item)"
          title="配置模型提供商"
        >
          <SettingOutlined />
        </a-button>
        <a-button
          type="text"
          class="expand-button"
          @click.stop="toggleExpand(item)"
        >
          <span class="icon-wrapper" :class="{'rotated': expandedModels[item]}">
            <DownCircleOutlined />
          </span>
        </a-button>
      </div>
      <div class="card-body-wrapper" :class="{'expanded': expandedModels[item]}">
        <div class="card-body" v-if="modelStatus[item]">
          <div class="card-models" v-for="(model, idx) in modelNames[item].models" :key="idx">
            <div class="model_name">{{ model }}</div>
          </div>
        </div>
      </div>
    </div>
    <div class="model-provider-card unconfigured-provider" v-for="(item, key) in notModelKeys" :key="key">
      <div class="card-header">
        <div class="model-icon">
          <img :src="modelIcons[item] || modelIcons.default" alt="模型图标">
        </div>
        <div class="model-title-container">
          <h3 style="font-weight: 400">{{ modelNames[item].name }}</h3>
          <a :href="modelNames[item].url" target="_blank" class="model-url">
            <InfoCircleOutlined />
          </a>
        </div>
        <a-button
          type="text"
          class="config-button"
          @click.stop="openProviderConfig(item)"
          title="配置模型提供商"
        >
          <SettingOutlined />
        </a-button>
        <div class="missing-keys">
          需配置<span>{{ modelNames[item].env }}</span>
        </div>
      </div>
    </div>


    <!-- 模型提供商配置弹窗 -->
    <a-modal
      class="provider-config-modal"
      v-model:open="providerConfig.visible"
      :title="`配置${providerConfig.providerName}模型`"
      @ok="saveProviderConfig"
      @cancel="cancelProviderConfig"
      :okText="'保存配置'"
      :cancelText="'取消'"
      :ok-type="'primary'"
      :width="800"
    >
      <div v-if="providerConfig.loading" class="modal-loading-container">
        <a-spin :indicator="h(LoadingOutlined, { style: { fontSize: '32px', color: 'var(--main-color)' }})" />
        <div class="loading-text">正在获取模型列表...</div>
      </div>
      <div v-else class="modal-config-content">
        <div class="modal-config-header">
          <h3>选择 {{ providerConfig.providerName }} 的模型</h3>
          <p class="description">勾选您希望在系统中启用的模型，请注意，列表中可能包含非对话模型，请仔细甄别。</p>
        </div>

        <div class="modal-models-section">
          <div class="model-search">
            <a-input
              v-model:value="providerConfig.searchQuery"
              placeholder="搜索模型..."
              allow-clear
            >
              <template #prefix>
                <SearchOutlined />
              </template>
            </a-input>
          </div>

          <!-- 显示选中统计信息 -->
          <div class="selection-summary">
            <span>已选择 {{ providerConfig.selectedModels.length }} 个模型</span>
            <span v-if="providerConfig.searchQuery" class="filter-info">
              （当前筛选显示 {{ filteredModels.length }} 个）
            </span>
          </div>

          <div class="modal-checkbox-list">
            <div v-for="(model, index) in filteredModels" :key="index" class="modal-checkbox-item">
              <a-checkbox
                :checked="providerConfig.selectedModels.includes(model.id)"
                @change="(e) => handleModelSelect(model.id, e.target.checked)"
              >
                {{ model.id }}
              </a-checkbox>
            </div>
          </div>
          <div v-if="providerConfig.allModels.length === 0" class="modal-no-models">
            <a-alert v-if="!modelStatus[providerConfig.provider]" type="warning" message="请在 .env 中配置对应的 APIKEY，并重新启动服务" />
            <div v-else>
              <a-alert type="warning" message="该提供商暂未适配获取模型列表的方法，如需添加模型，请编辑 src/config/static/models.py 。" />
              <img src="@/assets/pics/guides/how-to-add-models.png" alt="添加模型指引" style="width: 100%; height: 100%; margin-top: 16px;">
            </div>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, reactive, watch, h } from 'vue'
import { message } from 'ant-design-vue';
import {
  InfoCircleOutlined,
  SettingOutlined,
  DownCircleOutlined,
  LoadingOutlined,
  SearchOutlined
} from '@ant-design/icons-vue';
import { useConfigStore } from '@/stores/config';
import { modelIcons } from '@/utils/modelIcon';
import { agentApi } from '@/apis/agent_api';

const configStore = useConfigStore();

// 计算属性
const modelNames = computed(() => configStore.config?.model_names);
const modelStatus = computed(() => configStore.config?.model_provider_status);


// 提供商配置相关状态
const providerConfig = reactive({
  visible: false,
  provider: '',
  providerName: '',
  models: [],
  allModels: [], // 所有可用的模型
  selectedModels: [], // 用户选择的模型
  loading: false,
  searchQuery: '',
});

// 筛选 modelStatus 中为真的key
const modelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter(key => modelStatus.value[key]);
});

// 筛选 modelStatus 中为假的key
const notModelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter(key => !modelStatus.value[key]);
});

// 模型展开状态管理
const expandedModels = reactive({});

// 监听 modelKeys 变化，确保新添加的模型也是默认展开状态
watch(modelKeys, (newKeys) => {
  newKeys.forEach(key => {
    if (expandedModels[key] === undefined) {
      expandedModels[key] = true;
    }
  });
}, { immediate: true });


// 切换展开状态
const toggleExpand = (item) => {
  expandedModels[item] = !expandedModels[item];
};

// 处理模型选择
const handleModelSelect = (modelId, checked) => {
  const selectedModels = providerConfig.selectedModels;
  const index = selectedModels.indexOf(modelId);

  if (checked && index === -1) {
    selectedModels.push(modelId);
  } else if (!checked && index > -1) {
    selectedModels.splice(index, 1);
  }
};

// 打开提供商配置
const openProviderConfig = (provider) => {
  providerConfig.provider = provider;
  providerConfig.providerName = modelNames.value[provider].name;
  providerConfig.allModels = [];
  providerConfig.visible = true;
  providerConfig.loading = true;
  providerConfig.searchQuery = ''; // 重置搜索关键词

  // 获取当前选择的模型作为初始选中值
  const currentModels = modelNames.value[provider]?.models || [];
  providerConfig.selectedModels = [...currentModels];

  // 获取所有可用模型
  fetchProviderModels(provider);
};

// 获取模型提供商的模型列表
const fetchProviderModels = (provider) => {
  providerConfig.loading = true;
  agentApi.getProviderModels(provider)
    .then(data => {
      console.log(`${provider} 模型列表:`, data);

      // 处理各种可能的API返回格式
      let modelsList = [];

      // 情况1: { data: [...] }
      if (data.data && Array.isArray(data.data)) {
        modelsList = data.data;
      }
      // 情况2: { models: [...] } (字符串数组)
      else if (data.models && Array.isArray(data.models)) {
        modelsList = data.models.map(model => typeof model === 'string' ? { id: model } : model);
      }
      // 情况3: { models: { data: [...] } }
      else if (data.models && data.models.data && Array.isArray(data.models.data)) {
        modelsList = data.models.data;
      }

      console.log("处理后的模型列表:", modelsList);
      providerConfig.allModels = modelsList;
      providerConfig.loading = false;
    })
    .catch(error => {
      console.error(`获取${provider}模型列表失败:`, error);
      message.error({ content: `获取${modelNames.value[provider].name}模型列表失败`, duration: 2 });
      providerConfig.loading = false;
    });
};

// 保存提供商配置
const saveProviderConfig = async () => {
  if (!modelStatus.value[providerConfig.provider]) {
    message.error('请在 .env 中配置对应的 APIKEY，并重新启动服务');
    return;
  }

  message.loading({ content: '保存配置中...', key: 'save-config', duration: 0 });

  try {
    // 发送选择的模型列表到后端
    const data = await agentApi.updateProviderModels(providerConfig.provider, providerConfig.selectedModels);
    console.log('更新后的模型列表:', data.models);

    message.success({ content: '模型配置已保存!', key: 'save-config', duration: 2 });

    // 关闭弹窗
    providerConfig.visible = false;

    // 刷新配置
    configStore.refreshConfig();

  } catch (error) {
    console.error('保存配置失败:', error);
    message.error({ content: '保存配置失败: ' + error.message, key: 'save-config', duration: 2 });
  }
};

// 取消提供商配置
const cancelProviderConfig = () => {
  providerConfig.visible = false;
};

// 计算筛选后的模型列表
const filteredModels = computed(() => {
  const allModels = providerConfig.allModels || [];
  const searchQuery = providerConfig.searchQuery.toLowerCase();
  return allModels.filter(model => model.id.toLowerCase().includes(searchQuery));
});
</script>

<style lang="less" scoped>
.model-provider-card {
  border: 1px solid var(--gray-150);
  background-color: white;
  border-radius: 8px;
  margin-bottom: 16px;
  padding: 0;
  transition: all 0.3s ease;
  overflow: hidden;

  &:hover {
    border-color: var(--gray-200);
  }

  // 自定义模型容器特殊样式
  &.custom-models-card {
    .card-header {

      h3 {
        color: var(--main-color);
        font-weight: 600;
      }
    }
  }

  // 已配置provider的样式
  &.configured-provider {
    .card-header {

      .model-icon {
        &.available {
          position: relative;
          overflow: visible;
          box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.05);
        }
      }
    }
  }

  // 未配置provider的样式
  &.unconfigured-provider {
    .card-header {
      background: #fafafa;
      border-bottom: 1px solid var(--gray-150);

      h3 {
        color: var(--gray-700);
      }

      .missing-keys {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        border-radius: 4px;
        padding: 4px 8px;
        margin: 0;
      }
    }
  }

  .card-header {
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    padding: 8px 16px;
    background: white;
    transition: all 0.3s ease;

    &:hover {
      background: var(--gray-50);
    }

    .model-title-container {
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 10px;
      flex: 1;
    }

    .model-url {
      font-size: 12px;
      width: fit-content;
      color: var(--gray-500);
      transition: color 0.2s ease;

      &:hover {
        color: var(--main-color);
      }
    }

    .model-icon {
      width: 28px;
      height: 28px;
      position: relative;
      border-radius: 6px;
      overflow: hidden;
      filter: grayscale(100%);
      transition: filter 0.2s ease;

      img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        border: 1px solid var(--gray-100);
        border-radius: 6px;
      }

      &.available {
        filter: grayscale(0%);
      }
    }

    h3 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      color: var(--gray-900);
    }

    a {
      text-decoration: none;
      color: var(--gray-500);
      font-size: 12px;
      transition: all 0.2s ease;

      &:hover {
        color: var(--main-color);
      }
    }

    .details, .missing-keys {
      margin-left: auto;
    }

    .missing-keys {
      color: var(--gray-700);
      font-size: 12px;
      font-weight: 500;

      & > span {
        margin-left: 6px;
        user-select: all;
        background-color: rgba(251, 146, 60, 0.15);
        color: #d97706;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 11px;
        border: 1px solid rgba(251, 146, 60, 0.2);
      }
    }

    .expand-button, .config-button {
      height: 32px;
      width: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      cursor: pointer;
      color: var(--gray-500);
      border-radius: 6px;
      transition: all 0.2s ease;

      &:hover {
        background-color: var(--gray-50);
        color: var(--gray-700);
      }

      .icon-wrapper {
        display: inline-flex;
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &.rotated {
          transform: rotate(180deg);
        }
      }
    }
  }

  .card-body-wrapper {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    background: white;

    &.expanded {
      max-height: 800px;
    }
  }

  .card-body {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
    padding: 16px;
    background: var(--gray-10);

    // 普通模型卡片样式
    .card-models {
      width: 100%;
      border-radius: 6px;
      border: 1px solid var(--gray-150);
      padding: 12px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      box-sizing: border-box;
      background: white;
      transition: all 0.3s ease;
      min-height: 48px;

      &:hover {
        box-shadow: 0 1px 8px rgba(0, 0, 0, 0.03);
        border-color: var(--gray-200);
      }

      .model_name {
        font-size: 14px;
        font-weight: 500;
        color: var(--gray-900);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        line-height: 1.4;
      }

      .select-btn {
        width: 16px;
        height: 16px;
        flex: 0 0 16px;
        border-radius: 50%;
        border: 2px solid var(--gray-300);
        background: white;
        transition: all 0.2s ease;

        &:hover {
          border-color: var(--main-color);
        }
      }
    }

    // 自定义模型卡片样式 - 统一设计
    .custom-model {
      display: flex;
      flex-direction: column;
      align-items: stretch;
      padding: 12px 16px;
      gap: 8px;
      cursor: pointer;
      min-height: 72px;
      background: white;
      border-radius: 6px;
      border: 1px solid var(--gray-150);
      transition: all 0.3s ease;

      &:hover {
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
        border-color: var(--gray-200);

        .card-models__header .action {
          opacity: 1;
        }
      }

        .card-models__header {
        width: 100%;
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        min-height: 18px;

        .name {
          font-size: 14px;
          font-weight: 500;
          color: var(--gray-900);
          line-height: 1.4;
          flex: 1;
          margin-right: 8px;
          word-break: break-word;
        }

        .action {
          opacity: 0;
          transition: opacity 0.2s ease;
          display: flex;
          gap: 4px;
          flex-shrink: 0;
          margin-top: -1px;

          button {
            padding: 4px;
            height: 24px;
            width: 24px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;

            &:hover {
              background-color: var(--gray-100);
            }

            &:disabled {
              opacity: 0.4;
              cursor: not-allowed;

              &:hover {
                background-color: transparent;
              }
            }
          }
        }
      }

      .api_base {
        font-size: 12px;
        color: var(--gray-600);
        line-height: 1.3;
        word-break: break-all;
        margin-top: auto;
      }

      // 添加模型的special样式
      &.add-model {
        border: 2px dashed var(--gray-300);
        background: white;
        justify-content: center;
        align-items: center;
        text-align: center;
        min-height: 64px;

        &:hover {
          border-color: var(--main-color);
          background: #fafafa;
        }

        .card-models__header {
          justify-content: center;
          align-items: center;
          text-align: center;

          .name {
            color: var(--main-color);
            font-weight: 600;
            margin-right: 0;
            text-align: center;
          }
        }

        .api_base {
          color: var(--gray-500);
          text-align: center;
          margin-top: 4px;
        }
      }
    }
  }
}

.custom-model-modal {
  .ant-form-item {
    margin-bottom: 10px;
    .form-item-description {
      font-size: 12px;
      color: var(--gray-600);
      margin-bottom: 10px;
    }
  }
}

.provider-config-modal {
  .ant-modal-body {
    padding: 16px 0 !important;
    .modal-loading-container {
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      height: 200px;

      .loading-text {
        margin-top: 20px;
        color: var(--gray-700);
        font-size: 14px;
      }
    }

    .modal-config-content {
      max-height: 70vh;
      overflow-y: auto;

      .modal-config-header {
        margin-bottom: 20px;

        .description {
          font-size: 14px;
          color: var(--gray-600);
          margin: 0;
        }
      }

      .modal-models-section {
        .model-search {
          margin-bottom: 10px;
          padding: 0 6px;

          .ant-input-affix-wrapper {
            border-radius: 6px;
            &:hover, &:focus {
              border-color: var(--main-color);
            }
            .anticon {
              color: var(--gray-500);
            }
          }
        }
        .selection-summary {
          margin: 0 6px 10px;
          font-size: 14px;
          color: var(--gray-600);

          .filter-info {
            color: var(--gray-500);
          }
        }
        .modal-checkbox-list {
          max-height: 50vh;
          overflow-y: auto;
          .modal-checkbox-item {
            display: inline-block;
            margin-bottom: 4px;
            padding: 4px 6px;
            border-radius: 6px;
            background-color: white;
            border: 1px solid var(--gray-150);

            &:hover {
              background-color: var(--gray-50);
            }
          }
        }
      }
    }
  }
}

// 针对不同状态的额外样式调整
.unconfigured-provider {
  .card-body {
    .card-models {
      opacity: 0.6;
      pointer-events: none;

      .model_name {
        color: var(--gray-500);
      }

      &:hover {
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
        border-color: var(--gray-200);
      }
    }
  }
}

// 响应式调整
@media (max-width: 768px) {
  .model-provider-card {
    margin-bottom: 10px;

    .card-body {
      grid-template-columns: 1fr;
      gap: 8px;
      padding: 10px;
    }

    .card-header {
      padding: 10px;
      gap: 8px;

      .model-icon {
        width: 24px;
        height: 24px;
      }

      h3 {
        font-size: 14px;
      }

      .expand-button, .config-button {
        height: 30px;
        width: 30px;
      }
    }
  }
}
</style>
