<template>
  <HeaderComponent
    :title="database.name || '数据库信息加载中'"
    :loading="loading"
    class="database-info-header"
  >
    <template #left>
      <a-button
        @click="backToDatabase"
        shape="circle"
        :icon="h(LeftOutlined)"
        type="text"
      ></a-button>
    </template>
    <template #behind-title>
      <a-button type="link" @click="showEditModal" :style="{ padding: '0px', color: 'inherit' }">
        <EditOutlined />
      </a-button>
    </template>
    <template #actions>
      <div class="header-info">
        <span class="db-id"
          >ID:
          <span style="user-select: all">{{ database.db_id || 'N/A' }}</span>
        </span>
        <span class="file-count"
          >{{ database.files ? Object.keys(database.files).length : 0 }} 文件</span
        >
        <a-tag color="blue">{{ database.embed_info?.name }}</a-tag>
        <a-tag
          :color="getKbTypeColor(database.kb_type || 'lightrag')"
          class="kb-type-tag"
          size="small"
        >
          <component :is="getKbTypeIcon(database.kb_type || 'lightrag')" class="type-icon" />
          {{ getKbTypeLabel(database.kb_type || 'lightrag') }}
        </a-tag>
      </div>
    </template>
  </HeaderComponent>

  <!-- 添加编辑对话框 -->
  <a-modal v-model:open="editModalVisible" title="编辑知识库信息">
    <template #footer>
      <a-button danger @click="deleteDatabase" style="margin-right: auto; margin-left: 0">
        <DeleteOutlined /> 删除数据库
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
          placeholder="请输入知识库描述"
          :rows="4"
        />
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
    </a-form>
  </a-modal>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDatabaseStore } from '@/stores/database'
import { getKbTypeLabel, getKbTypeIcon, getKbTypeColor } from '@/utils/kb_utils'
import { LeftOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import HeaderComponent from '@/components/HeaderComponent.vue'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'
import AiTextarea from '@/components/AiTextarea.vue'
import { h } from 'vue'

const router = useRouter()
const store = useDatabaseStore()

const database = computed(() => store.database)
const loading = computed(() => store.state.databaseLoading)

const editModalVisible = ref(false)
const editFormRef = ref(null)
const editForm = reactive({
  name: '',
  description: '',
  llm_info: {
    provider: '',
    model_name: ''
  }
})

const rules = {
  name: [{ required: true, message: '请输入知识库名称' }]
}

const backToDatabase = () => {
  router.push('/database')
}

const showEditModal = () => {
  editForm.name = database.value.name || ''
  editForm.description = database.value.description || ''
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
      const updateData = {
        name: editForm.name,
        description: editForm.description
      }

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

<style scoped>
.database-info-header {
  padding: 8px;
  height: 50px;
}

.header-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.db-id {
  font-size: 12px;
  color: var(--gray-500);
}

.file-count {
  font-size: 12px;
  color: var(--gray-500);
}

.kb-type-tag {
  display: flex;
  align-items: center;
  gap: 4px;
}

.type-icon {
  width: 14px;
  height: 14px;
}
</style>
