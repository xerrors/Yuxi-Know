<template>
  <div class="agent-single-view">
    <!-- Token验证弹窗 -->
    <a-modal
      v-model:open="tokenModalVisible"
      title="访问验证"
      :closable="false"
      :maskClosable="false"
      :keyboard="false"
      :footer="null"
      width="500px"
    >
      <div class="token-verify-form">
        <p>需要输入访问令牌才能使用该智能体</p>
        <a-input-password
          v-model:value="tokenInput"
          placeholder="请输入访问令牌"
          @pressEnter="verifyToken"
        />
        <div class="error-message" v-if="errorMessage">{{ errorMessage }}</div>
        <div class="token-actions">
          <a-button type="primary" :loading="verifying" @click="verifyToken">验证</a-button>
        </div>
      </div>
    </a-modal>

    <!-- 智能体聊天界面 -->
    <AgentChatComponent v-if="isVerified" :agent-id="agentId" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AgentChatComponent from '@/components/AgentChatComponent.vue';
import { message } from 'ant-design-vue';

const route = useRoute();
const router = useRouter();
const agentId = computed(() => route.params.agent_id);

// Token验证相关状态
const tokenModalVisible = ref(false);
const tokenInput = ref('');
const isVerified = ref(false);
const verifying = ref(false);
const errorMessage = ref('');

// 验证Token
const verifyToken = async () => {
  if (!tokenInput.value) {
    errorMessage.value = '请输入访问令牌';
    return;
  }

  verifying.value = true;
  errorMessage.value = '';

  try {
    const response = await fetch('/api/admin/verify_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        agent_id: agentId.value,
        token: tokenInput.value
      })
    });

    if (response.ok) {
      // 验证成功
      isVerified.value = true;
      tokenModalVisible.value = false;

      // 保存令牌到localStorage
      localStorage.setItem(`agent-token-${agentId.value}`, tokenInput.value);
    } else {
      // 验证失败
      const data = await response.json();
      errorMessage.value = data.detail || '令牌验证失败';
    }
  } catch (error) {
    console.error('验证令牌出错:', error);
    errorMessage.value = '验证令牌时发生错误';
  } finally {
    verifying.value = false;
  }
};

// 检查是否已经验证
const checkVerification = async () => {
  const savedToken = localStorage.getItem(`agent-token-${agentId.value}`);

  if (savedToken) {
    // 即使有保存的令牌，也要重新验证其有效性
    verifying.value = true;

    try {
      const response = await fetch('/api/admin/verify_token', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          agent_id: agentId.value,
          token: savedToken
        })
      });

      if (response.ok) {
        // 验证成功
        isVerified.value = true;
        tokenInput.value = savedToken; // 保存已验证的令牌到输入框
      } else {
        // 令牌无效，清除本地存储并显示输入框
        localStorage.removeItem(`agent-token-${agentId.value}`);
        tokenModalVisible.value = true;
      }
    } catch (error) {
      console.error('验证令牌出错:', error);
      tokenModalVisible.value = true;
    } finally {
      verifying.value = false;
    }
  } else {
    // 没有保存的令牌，显示输入框
    tokenModalVisible.value = true;
  }
};

// 组件挂载时检查验证状态
onMounted(() => {
  checkVerification();
});
</script>

<style lang="less" scoped>
.agent-single-view {
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.token-verify-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;

  .error-message {
    color: #ff4d4f;
    font-size: 0.85rem;
  }

  .token-actions {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
  }
}
</style>


