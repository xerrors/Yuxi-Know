<template>
  <div class="share-config-form">
    <div class="share-config-content">
      <div class="share-mode">
        <a-radio-group v-model:value="config.is_shared" class="share-mode-radio">
          <a-radio :value="true">全员共享</a-radio>
          <a-radio :value="false">指定部门</a-radio>
        </a-radio-group>
      </div>
      <p class="share-hint">
        {{ config.is_shared ? '所有用户都可以访问' : '只有指定部门的用户可以访问' }}
      </p>
      <!-- 部门选择 -->
      <div v-if="!config.is_shared" class="dept-selection">
        <a-select
          v-model:value="config.accessible_department_ids"
          mode="multiple"
          placeholder="请选择可访问的部门"
          style="width: 100%"
          :options="departmentOptions"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { departmentApi } from '@/apis/department_api'

const userStore = useUserStore()
const departments = ref([])

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
  h3 {
    margin-top: 20px;
    margin-bottom: 12px;
  }

  .share-config-content {
    background: var(--gray-25);
    border-radius: 8px;
    padding: 16px;
    border: 1px solid var(--gray-150);

    .share-mode {
      .share-mode-radio {
        display: flex;
        gap: 24px;
      }
    }

    .share-hint {
      font-size: 13px;
      color: var(--gray-600);
      margin: 8px 0 0 0;
    }

    .dept-selection {
      margin-top: 12px;
    }
  }
}
</style>
