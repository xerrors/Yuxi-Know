<template>
  <a-modal
    :open="props.modelValue"
    title="检索配置"
    width="800px"
    :confirm-loading="loading"
    @ok="handleSave"
    @cancel="handleCancel"
    ok-text="保存"
    cancel-text="取消"
  >
    <div class="search-config-modal">
      <div v-if="loading" class="config-loading">
        <a-spin size="large" />
        <p>加载配置参数中...</p>
      </div>

      <div v-else-if="error" class="config-error">
        <a-result status="error" title="配置加载失败" :sub-title="error">
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
                  style="width: 100%"
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
                  :value="computedMeta[param.key]"
                  @update:value="(value) => updateMeta(param.key, value)"
                  style="width: 100%"
                >
                  <a-select-option value="true">启用</a-select-option>
                  <a-select-option value="false">关闭</a-select-option>
                </a-select>
                <a-input-number
                  v-else-if="param.type === 'number'"
                  v-model:value="meta[param.key]"
                  style="width: 100%"
                  :min="param.min || 0"
                  :max="param.max || 100"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </a-form>
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { useDatabaseStore } from '@/stores/database'
import { message } from 'ant-design-vue'
import { queryApi } from '@/apis/knowledge_api'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  databaseId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'save'])

const store = useDatabaseStore()

// 响应式数据
const loading = ref(false)
const error = ref('')
const queryParams = ref([])
const meta = reactive({})

// 计算属性：处理布尔类型的双向绑定
const computedMeta = computed(() => {
  const result = {}
  for (const key in meta) {
    const param = queryParams.value.find((p) => p.key === key)
    if (param?.type === 'boolean') {
      // 对于布尔类型，返回字符串给 select，但保持内部为布尔值
      result[key] = meta[key].toString()
    } else {
      result[key] = meta[key]
    }
  }
  return result
})

// 处理值更新
const updateMeta = (key, value) => {
  const param = queryParams.value.find((p) => p.key === key)
  if (param?.type === 'boolean') {
    // 将字符串转换回布尔值
    meta[key] = value === 'true'
  } else {
    meta[key] = value
  }
}

// 加载查询参数
const loadQueryParams = async () => {
  try {
    loading.value = true
    error.value = ''

    // 如果没有 databaseId，不执行请求
    if (!props.databaseId) {
      queryParams.value = []
      loading.value = false
      return
    }

    const response = await queryApi.getKnowledgeBaseQueryParams(props.databaseId)
    queryParams.value = response.params?.options || []

    // 过滤掉 include_distances 配置项，默认为 True 且不可修改
    queryParams.value = queryParams.value.filter((param) => param.key !== 'include_distances')

    // 初始化 meta 对象
    queryParams.value.forEach((param) => {
      if (param.default !== undefined) {
        // 对于布尔类型，确保使用布尔值而不是字符串
        if (param.type === 'boolean') {
          meta[param.key] = Boolean(param.default)
        } else {
          meta[param.key] = param.default
        }
      }
    })

    // 确保设置 include_distances 为 true（即使不显示也要设置）
    meta['include_distances'] = true

    // 加载保存的配置
    loadSavedConfig()
  } catch (err) {
    console.error('Failed to load query params:', err)
    error.value = err.message || '加载查询参数失败'
  } finally {
    loading.value = false
  }
}

// 加载保存的配置
const loadSavedConfig = () => {
  if (!props.databaseId) return

  const saved = localStorage.getItem(`search-config-${props.databaseId}`)
  if (saved) {
    try {
      const savedConfig = JSON.parse(saved)

      // 处理布尔类型转换
      queryParams.value.forEach((param) => {
        if (param.type === 'boolean' && savedConfig[param.key] !== undefined) {
          // 将字符串值转换为布尔值
          if (typeof savedConfig[param.key] === 'string') {
            savedConfig[param.key] = savedConfig[param.key] === 'true'
          }
        }
      })

      Object.assign(meta, savedConfig)
    } catch (e) {
      console.warn('Failed to parse saved config:', e)
    }
  }
  // 确保 include_distances 始终为 true，覆盖任何保存的值
  meta['include_distances'] = true
}

// 重置为默认值
const resetToDefaults = () => {
  queryParams.value.forEach((param) => {
    if (param.default !== undefined) {
      meta[param.key] = param.default
    }
  })
  // 确保 include_distances 始终为 true
  meta['include_distances'] = true
  message.success('已重置为默认配置')
}

// 保存配置
const handleSave = async () => {
  // 如果没有 databaseId，不执行保存
  if (!props.databaseId) {
    message.error('无法保存配置：缺少知识库ID')
    return
  }

  // 确保 include_distances 始终为 true
  meta['include_distances'] = true

  // 先保存到知识库元数据
  try {
    const response = await queryApi.updateKnowledgeBaseQueryParams(props.databaseId, meta)
    if (response.message === 'success') {
      // 服务器保存成功后，再保存到 localStorage（兼容性）
      localStorage.setItem(`search-config-${props.databaseId}`, JSON.stringify(meta))
      message.success('配置已保存')

      // 更新 store 中的配置
      Object.assign(store.meta, meta)

      // 触发保存事件
      emit('save', { ...meta })
      emit('update:modelValue', false)
    } else {
      throw new Error(response.message || '保存失败')
    }
  } catch (error) {
    console.error('保存配置到知识库失败:', error)
    message.error('保存配置失败：' + error.message)
  }
}

// 处理取消
const handleCancel = () => {
  emit('update:modelValue', false)
}

// 监听弹窗显示状态，显示时加载数据
watch(
  () => props.modelValue,
  (newVal) => {
    if (newVal && props.databaseId) {
      loadQueryParams()
    }
  }
)
</script>

<style lang="less" scoped>
.config-loading,
.config-error {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 300px;
  color: var(--gray-500);

  p {
    margin-top: 16px;
    font-size: 14px;
  }
}

.config-forms {
  max-width: 100%;
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
