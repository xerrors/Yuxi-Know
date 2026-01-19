<template>
  <div class="knowledge-base-card">
    <!-- 标题栏 -->
    <div class="card-header">
      <div class="header-left">
        <a-button
          @click="backToDatabase"
          class="back-button"
          shape="circle"
          :icon="h(LeftOutlined)"
          type="text"
          size="small"
        ></a-button>
        <h3 class="card-title">{{ database.name || '数据库信息加载中' }}</h3>
      </div>
      <div class="header-right">
        <a-button type="text" size="small" @click="copyDatabaseId" title="复制知识库ID">
          <template #icon>
            <Copy :size="14" />
          </template>
        </a-button>
        <a-button @click="showEditModal" type="text" size="small">
          <template #icon>
            <Pencil :size="14" />
          </template>
        </a-button>
      </div>
    </div>

    <!-- 卡片内容 -->
    <div class="card-content">
      <!-- 描述文本 -->
      <div class="description">
        <p class="description-text">{{ database.description || '暂无描述' }}</p>
      </div>

      <!-- Tags -->
      <div class="tags-section">
        <a-tag :color="getKbTypeColor(database.kb_type || 'lightrag')" size="small">
          {{ getKbTypeLabel(database.kb_type || 'lightrag') }}
        </a-tag>
        <a-tag color="blue" size="small">{{ database.embed_info?.name || 'N/A' }}</a-tag>
      </div>
    </div>
  </div>

  <!-- 编辑对话框 -->
  <a-modal v-model:open="editModalVisible" title="编辑知识库信息">
    <template #footer>
      <a-button danger @click="deleteDatabase" style="margin-right: auto; margin-left: 0">
        <template #icon>
          <Trash2 :size="16" style="vertical-align: -3px; margin-right: 4px" />
        </template>
        删除数据库
      </a-button>
      <a-button key="back" @click="editModalVisible = false">取消</a-button>
      <a-button key="submit" type="primary" @click="handleEditSubmit">确定</a-button>
    </template>
    <a-form :model="editForm" :rules="rules" ref="editFormRef" layout="vertical">
      <a-form-item label="知识库名称" name="name" required>
        <a-input v-model:value="editForm.name" placeholder="请输入知识库名称" />
      </a-form-item>
      <a-form-item label="知识库描述" name="description">
        <AiTextarea
          v-model="editForm.description"
          :name="editForm.name"
          :files="fileList"
          placeholder="请输入知识库描述"
          :rows="4"
        />
      </a-form-item>

      <a-form-item label="自动生成问题" name="auto_generate_questions">
        <a-switch
          v-model:checked="editForm.auto_generate_questions"
          checked-children="开启"
          un-checked-children="关闭"
        />
        <span style="margin-left: 8px; font-size: 12px; color: var(--gray-500)"
          >上传文件后自动生成测试问题</span
        >
      </a-form-item>

      <!-- 仅对 LightRAG 类型显示 LLM 配置 -->
      <a-form-item v-if="database.kb_type === 'lightrag'" label="语言模型 (LLM)" name="llm_info">
        <ModelSelectorComponent
          :model_spec="llmModelSpec"
          placeholder="请选择模型"
          @select-model="handleLLMSelect"
          style="width: 100%"
        />
      </a-form-item>

      <!-- 共享配置（超级管理员可编辑，非共享时本部门管理员也可编辑） -->
      <a-form-item v-if="canEditShareConfig" label="共享设置" name="share_config">
        <a-form-item-rest>
          <ShareConfigForm
            ref="shareConfigFormRef"
            :model-value="database.share_config"
            :auto-select-user-dept="true"
          />
        </a-form-item-rest>
      </a-form-item>
      <!-- 非编辑状态下显示共享配置信息 -->
      <a-form-item v-else-if="database.share_config" label="共享设置" name="share_config_readonly">
        <div class="share-config-readonly">
          <a-tag :color="database.share_config.is_shared !== false ? 'green' : 'blue'">
            {{ database.share_config.is_shared !== false ? '全员共享' : '指定部门' }}
          </a-tag>
          <span v-if="database.share_config.is_shared === false" class="dept-names">
            {{ getAccessibleDeptNames() }}
          </span>
        </div>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup>
import { ref, reactive, computed, h, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDatabaseStore } from '@/stores/database'
import { useUserStore } from '@/stores/user'
import { getKbTypeLabel, getKbTypeColor } from '@/utils/kb_utils'
import { message } from 'ant-design-vue'
import { LeftOutlined } from '@ant-design/icons-vue'
import { Pencil, Trash2, Copy } from 'lucide-vue-next'
import { departmentApi } from '@/apis/department_api'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'
import AiTextarea from '@/components/AiTextarea.vue'
import ShareConfigForm from '@/components/ShareConfigForm.vue'

const router = useRouter()
const store = useDatabaseStore()
const userStore = useUserStore()

const database = computed(() => store.database)

// 部门列表（用于显示部门名称）
const departments = ref([])

// 加载部门列表
const loadDepartments = async () => {
  try {
    const res = await departmentApi.getDepartments()
    departments.value = res.departments || res || []
  } catch (e) {
    console.error('加载部门列表失败:', e)
    departments.value = []
  }
}

// 初始化时加载部门
onMounted(() => {
  loadDepartments()
})

// 获取可访问的部门名称
const getAccessibleDeptNames = () => {
  const deptIds = database.value?.share_config?.accessible_departments || []
  if (deptIds.length === 0) return '无'
  return deptIds
    .map((id) => {
      const dept = departments.value.find((d) => d.id === id)
      return dept?.name || `部门${id}`
    })
    .join('、')
}

// 是否可以编辑共享配置
// 规则：1. 超级管理员可以编辑所有
//       2. 管理员也可以编辑（后端会验证权限）
const canEditShareConfig = computed(() => {
  if (userStore.isSuperAdmin) {
    return true
  }
  // 管理员可以编辑共享配置，后端会验证权限
  return userStore.isAdmin
})

const fileList = computed(() => {
  if (!database.value?.files) return []
  return Object.values(database.value.files)
    .map((f) => f.filename)
    .filter(Boolean)
})

// 复制数据库ID
const copyDatabaseId = async () => {
  if (!database.value.db_id) {
    message.warning('知识库ID为空')
    return
  }

  try {
    await navigator.clipboard.writeText(database.value.db_id)
    message.success('知识库ID已复制到剪贴板')
  } catch (err) {
    // 降级方案
    const textArea = document.createElement('textarea')
    textArea.value = database.value.db_id
    document.body.appendChild(textArea)
    textArea.select()
    document.execCommand('copy')
    document.body.removeChild(textArea)
    message.success('知识库ID已复制到剪贴板')
  }
}

// 返回数据库列表
const backToDatabase = () => {
  router.push('/database')
}

// 编辑相关逻辑（复用自 DatabaseHeader）
const editModalVisible = ref(false)
const editFormRef = ref(null)
const shareConfigFormRef = ref(null)
const editForm = reactive({
  name: '',
  description: '',
  auto_generate_questions: false,
  llm_info: {
    provider: '',
    model_name: ''
  }
})

const rules = {
  name: [{ required: true, message: '请输入知识库名称' }]
}

// 打开编辑弹窗
const showEditModal = () => {
  console.log('[showEditModal] 被调用')

  editForm.name = database.value.name || ''
  editForm.description = database.value.description || ''
  editForm.auto_generate_questions =
    database.value.additional_params?.auto_generate_questions || false

  // 如果是 LightRAG 类型，加载当前的 LLM 配置
  if (database.value.kb_type === 'lightrag') {
    const llmInfo = database.value.llm_info || {}
    editForm.llm_info.provider = llmInfo.provider || ''
    editForm.llm_info.model_name = llmInfo.model_name || ''
  }

  editModalVisible.value = true
}

const handleEditSubmit = () => {
  editFormRef.value
    .validate()
    .then(async () => {
      // 验证共享配置
      if (shareConfigFormRef.value) {
        const validation = shareConfigFormRef.value.validate()
        if (!validation.valid) {
          message.warning(validation.message)
          return
        }
      }

      // 从 ShareConfigForm 组件直接获取当前值
      let finalIsShared = true
      let finalDeptIds = []

      if (shareConfigFormRef.value) {
        const formConfig = shareConfigFormRef.value.config
        finalIsShared = formConfig.is_shared
        finalDeptIds = formConfig.accessible_department_ids || []
      }

      console.log('[handleEditSubmit] 直接从组件获取 - is_shared:', finalIsShared, 'dept_ids:', JSON.stringify(finalDeptIds))

      const updateData = {
        name: editForm.name,
        description: editForm.description,
        additional_params: {
          auto_generate_questions: editForm.auto_generate_questions
        },
        share_config: {
          is_shared: finalIsShared,
          accessible_departments: finalIsShared ? [] : finalDeptIds
        }
      }

      console.log('[handleEditSubmit] updateData.share_config:', JSON.stringify(updateData.share_config))

      // 如果是 LightRAG 类型，包含 llm_info
      if (database.value.kb_type === 'lightrag') {
        updateData.llm_info = {
          provider: editForm.llm_info.provider,
          model_name: editForm.llm_info.model_name
        }
      }

      await store.updateDatabaseInfo(updateData)
      editModalVisible.value = false
    })
    .catch((err) => {
      console.error('表单验证失败:', err)
    })
}

// LLM 模型选择处理
const llmModelSpec = computed(() => {
  const provider = editForm.llm_info?.provider || ''
  const modelName = editForm.llm_info?.model_name || ''
  if (provider && modelName) {
    return `${provider}/${modelName}`
  }
  return ''
})

const handleLLMSelect = (spec) => {
  console.log('LLM选择:', spec)
  if (typeof spec !== 'string' || !spec) return

  const index = spec.indexOf('/')
  const provider = index !== -1 ? spec.slice(0, index) : ''
  const modelName = index !== -1 ? spec.slice(index + 1) : ''

  editForm.llm_info.provider = provider
  editForm.llm_info.model_name = modelName
}

const deleteDatabase = () => {
  store.deleteDatabase()
}
</script>

<style lang="less" scoped>
.knowledge-base-card {
  background: linear-gradient(120deg, var(--main-30) 0%, var(--gray-0) 100%);
  border-radius: 12px;
  border: 1px solid var(--gray-200);
  margin-bottom: 8px;
}

// 只读共享配置显示
.share-config-readonly {
  display: flex;
  align-items: center;
  gap: 8px;

  .dept-names {
    font-size: 13px;
    color: var(--gray-600);
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;

  .header-left {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1;
    min-width: 0;

    button.back-button {
      margin-left: -5px;
      font-size: 10px;
    }
  }

  .card-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--gray-800);
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    // flex: 1;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;

    button {
      color: var(--gray-500);
      height: 100%;
    }

    button:hover {
      color: var(--gray-700);
      background-color: var(--gray-100);
    }
  }
}

.card-content {
  padding: 0 16px 16px 16px;
}

.description {
  margin-bottom: 12px;

  .description-text {
    font-size: 14px;
    color: var(--gray-700);
    line-height: 1.5;
    margin: 0;
  }
}

.tags-section {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
