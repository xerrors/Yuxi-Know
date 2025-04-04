<template>
  <div class="token-manager">
    <div class="token-tools">
      <a-button type="primary" size="small" @click="showAddTokenModal">
        <PlusOutlined /> 创建 Token
      </a-button>
    </div>
    <!-- 令牌列表 -->
    <div class="token-list" v-if="tokens.length > 0">
      <a-spin :spinning="loading">
        <a-list size="small">
          <a-list-item v-for="token in tokens" :key="token.id">
            <div class="token-item">
              <div class="token-info">
                <div class="token-name">{{ token.name }}</div>
                <div class="token-value">
                  <code>{{ token.token }}</code>
                  <a-button type="link" size="small" @click="copyToken(token.token)">
                    <CopyOutlined />
                  </a-button>
                </div>
                <div class="token-time">创建时间: {{ formatDate(token.created_at) }}</div>
              </div>
              <div class="token-actions">
                <a-popconfirm
                  title="确定要删除这个令牌吗?"
                  ok-text="确定"
                  cancel-text="取消"
                  @confirm="deleteToken(token.id)"
                >
                  <a-button type="text" danger size="small">
                    <DeleteOutlined />
                  </a-button>
                </a-popconfirm>
              </div>
            </div>
          </a-list-item>
        </a-list>
      </a-spin>
    </div>
    <a-empty v-else description="暂无访问令牌" :image="Empty.PRESENTED_IMAGE_SIMPLE" />

    <!-- 添加令牌弹窗 -->
    <a-modal
      v-model:open="addTokenModalVisible"
      title="添加访问令牌"
      ok-text="创建"
      cancel-text="取消"
      @ok="createToken"
    >
      <a-form :model="newToken" layout="vertical">
        <a-form-item label="令牌名称" name="name">
          <a-input v-model:value="newToken.name" placeholder="请输入令牌名称" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue';
import { message, Empty } from 'ant-design-vue';
import { PlusOutlined, DeleteOutlined, CopyOutlined } from '@ant-design/icons-vue';

const props = defineProps({
  agentId: {
    type: String,
    required: true
  }
});

// 状态
const tokens = ref([]);
const loading = ref(false);
const addTokenModalVisible = ref(false);
const newToken = ref({
  name: ''
});

// 获取令牌列表
const fetchTokens = async () => {
  loading.value = true;
  try {
    const response = await fetch(`/api/admin/tokens?agent_id=${props.agentId}`);
    if (response.ok) {
      const data = await response.json();
      tokens.value = data;
    } else {
      message.error('获取令牌列表失败');
    }
  } catch (error) {
    console.error('获取令牌列表出错:', error);
    message.error('获取令牌列表出错');
  } finally {
    loading.value = false;
  }
};

// 创建新令牌
const createToken = async () => {
  if (!newToken.value.name.trim()) {
    message.warning('请输入令牌名称');
    return;
  }

  try {
    const response = await fetch('/api/admin/tokens', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        agent_id: props.agentId,
        name: newToken.value.name
      })
    });

    if (response.ok) {
      const data = await response.json();
      tokens.value.push(data);
      message.success('令牌创建成功');
      addTokenModalVisible.value = false;
      newToken.value.name = '';
    } else {
      message.error('创建令牌失败');
    }
  } catch (error) {
    console.error('创建令牌出错:', error);
    message.error('创建令牌出错');
  }
};

// 删除令牌
const deleteToken = async (tokenId) => {
  try {
    const response = await fetch(`/api/admin/tokens/${tokenId}`, {
      method: 'DELETE'
    });

    if (response.ok) {
      tokens.value = tokens.value.filter(token => token.id !== tokenId);
      message.success('令牌已删除');
    } else {
      message.error('删除令牌失败');
    }
  } catch (error) {
    console.error('删除令牌出错:', error);
    message.error('删除令牌出错');
  }
};

// 复制令牌到剪贴板
const copyToken = (token) => {
  navigator.clipboard.writeText(token).then(() => {
    message.success('令牌已复制到剪贴板');
  });
};

// 显示添加令牌弹窗
const showAddTokenModal = () => {
  newToken.value.name = '';
  addTokenModalVisible.value = true;
};

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleString();
};

// 监听agentId变化
watch(() => props.agentId, (newAgentId) => {
  if (newAgentId) {
    fetchTokens();
  } else {
    tokens.value = [];
  }
}, { immediate: true });

// 组件挂载时获取令牌列表
onMounted(() => {
  if (props.agentId) {
    fetchTokens();
  }
});
</script>

<style lang="less" scoped>
.token-manager {
  margin-top: 1rem;
  // padding: 0 0.5rem;
}

.manager-title {
  font-size: 1rem;
  margin-bottom: 1rem;
}

.token-tools {
  margin-bottom: 1rem;
  display: flex;
  justify-content: flex-end;
}

.token-list {
  max-height: calc(100vh - 400px);
  overflow-y: auto;
  li.ant-list-item {
    background-color: var(--gray-100);
    border-radius: 0.5rem;
    padding: 0.5rem;
    margin-bottom: 0.5rem;
  }
}

.token-item {
  display: flex;
  justify-content: space-between;
  width: 100%;
}

.token-info {
  flex: 1;
}

.token-name {
  font-weight: 500;
  margin-bottom: 0.25rem;
}

.token-value {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  background-color: var(--main-light-4);
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  margin-bottom: 0.25rem;
  overflow-x: auto;
  user-select: all;

  code {
    flex: 1;
  }
}

.token-time {
  font-size: 0.75rem;
  color: var(--gray-500);
}

.token-actions {
  display: flex;
  align-items: center;
}
</style>