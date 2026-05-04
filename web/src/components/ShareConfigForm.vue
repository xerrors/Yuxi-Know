<template>
  <div class="share-config-form">
    <div class="share-config-content">
      <div class="share-mode-cards" role="radiogroup" aria-label="共享设置">
        <button
          v-for="option in shareModeOptions"
          :key="option.value"
          type="button"
          role="radio"
          class="share-mode-card"
          :class="{ active: config.is_shared === option.value }"
          :aria-checked="config.is_shared === option.value"
          :tabindex="config.is_shared === option.value ? 0 : -1"
          @click="setShareMode(option.value)"
          @keydown.enter.prevent="setShareMode(option.value)"
          @keydown.space.prevent="setShareMode(option.value)"
        >
          <div class="card-icon-wrapper" aria-hidden="true">
            <component :is="option.icon" class="card-icon" :size="20" />
          </div>
          <div class="card-content">
            <div class="card-title">{{ option.title }}</div>
            <div class="card-description">{{ option.description }}</div>
          </div>
        </button>
      </div>
      <div v-if="!config.is_shared" class="compact-dept-selection">
        <div class="dept-selection-header">
          <div class="dept-selection-label">可访问部门</div>
          <div class="dept-selection-hint">请选择可访问该知识库的部门</div>
        </div>
        <a-select
          v-model:value="config.accessible_department_ids"
          mode="multiple"
          placeholder="请选择部门"
          size="small"
          class="full-width dept-selection-input"
          :options="departmentOptions"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { Globe, Building2 } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { departmentApi } from '@/apis/department_api'

const userStore = useUserStore()
const departments = ref([])

const shareModeOptions = [
  {
    value: true,
    title: '公开给团队',
    description: '团队内所有成员都可以访问这个知识库',
    icon: Globe
  },
  {
    value: false,
    title: '仅指定部门',
    description: '只有选中的部门成员可以访问这个知识库',
    icon: Building2
  }
]

const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
    default: () => ({
      is_shared: true,
      accessible_department_ids: []
    })
  },
  // 是否自动选中当前用户所在部门
  autoSelectUserDept: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])

// 本地状态，直接从 props 初始化
const config = reactive({
  is_shared: true,
  accessible_department_ids: []
})

// 初始化 config
const initConfig = () => {
  // 后端返回的是 accessible_departments，前端使用 accessible_department_ids
  const sourceDepts =
    props.modelValue.accessible_department_ids ?? props.modelValue.accessible_departments ?? []
  config.is_shared = props.modelValue.is_shared ?? true
  config.accessible_department_ids = sourceDepts.map((id) => Number(id))
  console.log('[ShareConfigForm] initConfig:', JSON.stringify(config))
}

// 只在组件挂载时初始化一次
onMounted(() => {
  initConfig()
})

// 监听本地 config 变化，同步到父组件
watch(
  config,
  (newVal) => {
    console.log('[ShareConfigForm] config 变化，emit:', JSON.stringify(newVal))
    emit('update:modelValue', {
      is_shared: newVal.is_shared,
      accessible_department_ids: newVal.accessible_department_ids
    })
  },
  { deep: true }
)

const setShareMode = (isShared) => {
  if (config.is_shared === isShared) {
    return
  }
  config.is_shared = isShared
}

// 监听共享模式变化
watch(
  () => config.is_shared,
  (newVal) => {
    if (!newVal && props.autoSelectUserDept && config.accessible_department_ids.length === 0) {
      // 切换到指定部门模式且未选中任何部门时，默认选中当前用户所在部门
      tryAutoSelectUserDept()
    }
  }
)

// 尝试自动选中用户所在部门
const tryAutoSelectUserDept = () => {
  const userDeptId = userStore.departmentId
  if (userDeptId) {
    const deptExists = departments.value.find((d) => d.id === userDeptId)
    if (deptExists) {
      // 确保存储为数字类型（a-select 返回的是字符串）
      config.accessible_department_ids = [Number(userDeptId)]
    }
  }
}

// 监听用户部门变化（处理时序问题：departmentId 可能在组件 mounted 后才获取到）
watch(
  () => userStore.departmentId,
  (newDeptId) => {
    if (
      props.autoSelectUserDept &&
      !config.is_shared &&
      config.accessible_department_ids.length === 0 &&
      newDeptId
    ) {
      tryAutoSelectUserDept()
    }
  }
)

// 部门选项
const departmentOptions = computed(() =>
  departments.value.map((dept) => ({
    label: dept.name,
    value: Number(dept.id)
  }))
)

// 加载部门列表
const loadDepartments = async () => {
  try {
    const res = await departmentApi.getDepartments()
    departments.value = res.departments || res || []

    // 如果需要，自动选中用户所在部门
    if (
      props.autoSelectUserDept &&
      !config.is_shared &&
      config.accessible_department_ids.length === 0
    ) {
      tryAutoSelectUserDept()
    }
  } catch (e) {
    console.error('加载部门列表失败:', e)
    departments.value = []
  }
}

onMounted(() => {
  loadDepartments()
})

// 验证当前用户所在部门是否在可访问范围内
// 返回 { valid: boolean, message: string }
const validate = () => {
  // 全员共享模式不需要验证
  if (config.is_shared) {
    return { valid: true, message: '' }
  }

  // 指定部门模式，需要验证当前用户所在部门是否在列表中
  const userDeptId = userStore.departmentId
  if (!userDeptId) {
    return {
      valid: false,
      message: '您不属于任何部门，无法使用指定部门共享模式'
    }
  }

  if (!config.accessible_department_ids.includes(userDeptId)) {
    return {
      valid: false,
      message: '您所在的部门必须在可访问部门范围内'
    }
  }

  return { valid: true, message: '' }
}

// 暴露方法给父组件
defineExpose({
  config,
  validate
})
</script>

<style lang="less" scoped>
.share-config-form {
  .share-config-content {
    display: flex;
    flex-direction: column;
    gap: 8px;
    border-radius: 10px;

    .share-mode-cards {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;

      @media (max-width: 768px) {
        grid-template-columns: 1fr;
      }
    }

    .share-mode-card {
      position: relative;
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 76px;
      padding: 12px;
      border: 1px solid var(--gray-200);
      border-radius: 10px;
      background: var(--gray-0);
      text-align: left;
      cursor: pointer;
      transition:
        border-color 0.2s ease,
        background-color 0.2s ease,
        box-shadow 0.2s ease;

      &:hover,
      &:focus-visible {
        border-color: var(--main-color);
      }

      &:focus-visible {
        outline: none;
        box-shadow: 0 0 0 2px var(--main-20);
      }

      &.active {
        border-color: var(--main-color);
        background: var(--main-10);
        box-shadow: 0 0 0 1px var(--main-20);
      }

      .card-icon-wrapper {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        flex-shrink: 0;
        border-radius: 10px;
        background: var(--gray-50);
        transition: background-color 0.2s ease;
      }

      .card-icon {
        color: var(--gray-500);
        transition: color 0.2s ease;
      }

      .card-content {
        min-width: 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 3px;
        flex: 1;
      }

      .card-title {
        font-size: 14px;
        font-weight: 600;
        color: var(--gray-800);
        line-height: 1.35;
      }

      &.active .card-icon-wrapper {
        background: var(--main-0);
      }

      &.active .card-icon {
        color: var(--main-color);
      }

      .card-description {
        font-size: 12px;
        line-height: 1.45;
        color: var(--gray-600);
      }
    }

    .dept-selection {
      margin-top: 0;
    }

    .compact-dept-selection {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px 12px;
      border: 1px solid var(--gray-150);
      border-radius: 10px;
      background: linear-gradient(180deg, var(--gray-0) 0%, var(--gray-50) 100%);
    }

    .dept-selection-header {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .dept-selection-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--gray-800);
      line-height: 1.4;
    }

    .dept-selection-hint {
      font-size: 12px;
      line-height: 1.5;
      color: var(--gray-600);
    }

    .dept-selection-input {
      :deep(.ant-select-selector) {
        min-height: 36px;
        padding: 3px 8px !important;
        border-radius: 8px !important;
        border-color: var(--gray-200) !important;
        box-shadow: none !important;
      }

      &:deep(.ant-select-focused .ant-select-selector),
      &:deep(.ant-select-selector:hover) {
        border-color: var(--main-color) !important;
      }
    }
  }
}
</style>
