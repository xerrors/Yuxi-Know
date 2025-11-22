<template>
  <div class="search-config-tab">
    <div class="config-header">
      <p class="config-title">检索配置</p>
      <div class="config-actions">
        <a-button size="small" @click="resetToDefaults">重置默认</a-button>
        <a-button size="small" type="primary" @click="saveConfig">保存配置</a-button>
      </div>
    </div>

    <div class="config-content">
      <div v-if="loading" class="config-loading">
        <a-spin size="large" />
        <p>加载配置参数中...</p>
      </div>

      <div v-else-if="error" class="config-error">
        <a-result
          status="error"
          title="配置加载失败"
          :sub-title="error"
        >
          <template #extra>
            <a-button type="primary" @click="loadQueryParams">重新加载</a-button>
          </template>
        </a-result>
      </div>

      <div v-else class="config-forms">
        <a-form layout="vertical">
          <a-row :gutter="16">
            <a-col :span="12" v-for="param in queryParams" :key="param.key">
              <a-form-item :label="param.label">
                <a-select
                  v-if="param.type === 'select'"
                  v-model:value="meta[param.key]"
                  style="width: 100%;"
                >
                  <a-select-option
                    v-for="option in param.options"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </a-select-option>
                </a-select>
                <a-select
                  v-else-if="param.type === 'boolean'"
                  v-model:value="meta[param.key]"
                  style="width: 100%;"
                >
                  <a-select-option :value="true">启用</a-select-option>
                  <a-select-option :value="false">关闭</a-select-option>
                </a-select>
                <a-input-number
                  v-else-if="param.type === 'number'"
                  v-model:value="meta[param.key]"
                  style="width: 100%;"
                  :min="param.min || 0"
                  :max="param.max || 100"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </a-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue';
import { useDatabaseStore } from '@/stores/database';
import { message } from 'ant-design-vue';
import { queryApi } from '@/apis/knowledge_api';

const props = defineProps({
  databaseId: {
    type: String,
    required: true
  }
});

const store = useDatabaseStore();

// 响应式数据
const loading = ref(false);
const error = ref('');
const queryParams = ref([]);
const meta = reactive({});

// 加载查询参数
const loadQueryParams = async () => {
  try {
    loading.value = true;
    error.value = '';

    const response = await queryApi.getKnowledgeBaseQueryParams(props.databaseId);
    queryParams.value = response.params?.options || [];

    // 过滤掉 include_distances 配置项，默认为 True 且不可修改
    queryParams.value = queryParams.value.filter(param => param.key !== 'include_distances');

    // 初始化 meta 对象
    queryParams.value.forEach(param => {
      if (param.default !== undefined) {
        meta[param.key] = param.default;
      }
    });

    // 确保设置 include_distances 为 true（即使不显示也要设置）
    meta['include_distances'] = true;

    // 加载保存的配置
    loadSavedConfig();

  } catch (err) {
    console.error('Failed to load query params:', err);
    error.value = err.message || '加载查询参数失败';
  } finally {
    loading.value = false;
  }
};

// 加载保存的配置
const loadSavedConfig = () => {
  const saved = localStorage.getItem(`search-config-${props.databaseId}`);
  if (saved) {
    try {
      const savedConfig = JSON.parse(saved);
      Object.assign(meta, savedConfig);
    } catch (e) {
      console.warn('Failed to parse saved config:', e);
    }
  }
  // 确保 include_distances 始终为 true，覆盖任何保存的值
  meta['include_distances'] = true;
};

// 重置为默认值
const resetToDefaults = () => {
  queryParams.value.forEach(param => {
    if (param.default !== undefined) {
      meta[param.key] = param.default;
    }
  });
  // 确保 include_distances 始终为 true
  meta['include_distances'] = true;
  message.success('已重置为默认配置');
};

// 保存配置
const saveConfig = () => {
  // 确保 include_distances 始终为 true
  meta['include_distances'] = true;

  localStorage.setItem(`search-config-${props.databaseId}`, JSON.stringify(meta));

  // 更新 store 中的配置
  Object.assign(store.meta, meta);

  message.success('配置已保存');
};

// 组件挂载时加载数据
onMounted(() => {
  loadQueryParams();
});
</script>

<style lang="less" scoped>
.search-config-tab {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--gray-0);
}

.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  // border-bottom: 1px solid var(--gray-200);
  flex-shrink: 0;

  .config-title {
    margin: 0;
    color: var(--gray-800);
  }

  .config-actions {
    display: flex;
    gap: 8px;
  }
}

.config-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.config-loading,
.config-error {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100%;
  color: var(--gray-500);

  p {
    margin-top: 16px;
    font-size: 14px;
  }
}

.config-forms {
  max-width: 800px;
}


// 表单样式优化
:deep(.ant-form-item) {
  margin-bottom: 16px;
}

:deep(.ant-form-item-label > label) {
  font-weight: 500;
  color: var(--gray-700);
}

:deep(.ant-input),
:deep(.ant-select-selector) {
  border-radius: 6px;
}

:deep(.ant-switch) {
  background-color: var(--gray-300);

  &.ant-switch-checked {
    background-color: var(--main-color);
  }
}
</style>