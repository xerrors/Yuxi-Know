<template>
  <HeaderComponent
    :title="database.name || '数据库信息加载中'"
    :loading="loading"
    class="database-info-header"
  >
    <template #left>
      <a-button @click="backToDatabase" shape="circle" :icon="h(LeftOutlined)" type="text"></a-button>
    </template>
    <template #behind-title>
      <a-button type="link" @click="showEditModal" :style="{ padding: '0px', color: 'inherit' }">
        <EditOutlined />
      </a-button>
    </template>
    <template #actions>
      <div class="header-info">
        <span class="db-id">ID:
          <span style="user-select: all;">{{ database.db_id || 'N/A' }}</span>
        </span>
        <span class="file-count">{{ database.files ? Object.keys(database.files).length : 0 }} 文件</span>
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
      <a-button danger @click="deleteDatabase" style="margin-right: auto; margin-left: 0;">
        <DeleteOutlined /> 删除数据库
      </a-button>
      <a-button key="back" @click="editModalVisible = false">取消</a-button>
      <a-button key="submit" type="primary" :loading="loading" @click="handleEditSubmit">确定</a-button>
    </template>
    <a-form :model="editForm" :rules="rules" ref="editFormRef" layout="vertical">
      <a-form-item label="知识库名称" name="name" required>
        <a-input v-model:value="editForm.name" placeholder="请输入知识库名称" />
      </a-form-item>
      <a-form-item label="知识库描述" name="description">
        <a-textarea v-model:value="editForm.description" placeholder="请输入知识库描述" :rows="4" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup>
import { ref, reactive, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useDatabaseStore } from '@/stores/database';
import { getKbTypeLabel, getKbTypeIcon, getKbTypeColor } from '@/utils/kb_utils';
import {
  LeftOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import { h } from 'vue';

const router = useRouter();
const store = useDatabaseStore();

const database = computed(() => store.database);
const loading = computed(() => store.state.databaseLoading);

const editModalVisible = ref(false);
const editFormRef = ref(null);
const editForm = reactive({
  name: '',
  description: ''
});

const rules = {
  name: [{ required: true, message: '请输入知识库名称' }]
};

const backToDatabase = () => {
  router.push('/database');
};

const showEditModal = () => {
  editForm.name = database.value.name || '';
  editForm.description = database.value.description || '';
  editModalVisible.value = true;
};

const handleEditSubmit = () => {
  editFormRef.value.validate().then(async () => {
    await store.updateDatabaseInfo({
      name: editForm.name,
      description: editForm.description
    });
    editModalVisible.value = false;
  }).catch(err => {
    console.error('表单验证失败:', err);
  });
};

const deleteDatabase = () => {
  store.deleteDatabase();
};
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
  color: #666;
}

.file-count {
  font-size: 12px;
  color: #666;
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