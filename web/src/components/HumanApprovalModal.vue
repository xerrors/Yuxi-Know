<template>
  <transition name="slide-up">
    <div v-if="visible" class="approval-modal">
      <div class="approval-content">
        <div class="approval-header">
          <h4>{{ question }}</h4>
        </div>

        <!-- <div class="approval-operation">
          <span class="label">操作：</span>
          <span class="operation-text">{{ operation }}</span>
        </div> -->
  
        <div class="approval-operation-table">
          <div v-if="typeof handleOperation === 'string'"> 
              <span class="param-key">{{ handleOperation }}</span>
          </div>
          <div v-else>
            <div v-for="(param, index) in handleOperation.params" :key="index" class="param-row">
              <span class="param-key">{{ param.key }}</span>
              <input class="param-value" v-model="param.value" type="text" />
            </div>
          </div>
        </div>
      </div>
      <div class="approval-actions">
        <button class="btn btn-reject" @click="handleReject" :disabled="isProcessing">
          ✕ 拒绝
        </button>
        <button class="btn btn-approve" @click="handleApprove" :disabled="isProcessing">
          ✓ 批准
        </button>
      </div>

      <div v-if="isProcessing" class="approval-processing">
        <span class="processing-spinner"></span>
        处理中...
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, computed } from 'vue';

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  question: {
    type: String,
    default: '是否批准此操作？'
  },
  operation: {
    type: String,
    default: ''
  }
});

const emit = defineEmits(['approve', 'reject']);

const isProcessing = ref(false);

// 监听弹窗关闭，重置处理状态
watch(() => props.visible, (newVal) => {
  if (!newVal) {
    isProcessing.value = false;
  }
});

const handleOperation = computed(() => {
  try {
    // 处理 Interrupt(value={...}) 格式的字符串
    let operationData = props.operation;
    let operationName = operationData['name']
    let operationParams = operationData['args']
    // 转换为键值对数组
    return {
      name: operationName,
      params: Object.entries(operationParams).map(([key, value]) => ({ 
            key, 
            value 
      }))
    };
    
  } catch (e) {
    // 如果解析失败，返回原始值
    console.error('Error parsing operation:', e);
    return props.operation;
  }
});


const handleApprove = () => {
  if (isProcessing.value) return;
  isProcessing.value = true;
  emit('approve', handleOperation.value);
};

const handleReject = () => {
  if (isProcessing.value) return;
  isProcessing.value = true;
  emit('reject');
};

</script>

<style scoped>
.param-row {
  display: flex;
  border-bottom: 1px solid var(--gray-200);
}

.param-row:last-child {
  border-bottom: none;
}

.param-key {
  padding: 8px 12px;
  font-weight: 500;
  color: var(--gray-600);
  background-color: var(--gray-100);
  /* flex: 0 0 120px; 固定宽度 */
  flex: none;              /* 或 flex: 0 0 auto */
  display: flex;           /* 关键：让子元素可居中 */
  align-items: center;     /* 垂直居中 */
  justify-content: left; /* 水平居中 */
  height: auto;           /* 高度自适应 */
  padding: 8px 12px;      /* 添加内边距，让高度有内容 */
  border-right: 1px solid var(--gray-200);
  width: 50%;
}

.param-value {
  padding: 8px 12px;
  color: var(--gray-800);
  background-color: var(--gray-100);
  /* word-break: break-word;
  white-space: pre-wrap;  */
  flex: none;              /* 或 flex: 0 0 auto */
  display: flex;           /* 关键：让子元素可居中 */
  align-items: center;     /* 垂直居中 */
  justify-content: left; /* 水平居中 */
  height: auto;           /* 高度自适应 */
  padding: 8px 12px;      /* 添加内边距，让高度有内容 */
  border-right: 1px solid var(--gray-200);
  width: 50%;
}

.approval-modal {
  background: var(--gray-0);
  border-radius: 12px 12px;
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.12);
  margin: 0 auto 8px;
  max-width: 800px;
  width: 100%;
  border: 1px solid var(--gray-200);
}

.approval-content {
  padding: 16px 20px;
}

.approval-header {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 12px;
}

.approval-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--gray-800);
  text-align: center;
}

.approval-operation-table {
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  max-height: 200px;
  overflow-y: auto;
}

.approval-operation {
  background: var(--gray-50);
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  display: flex;
  gap: 6px;
}

.approval-operation .label {
  color: var(--gray-600);
  font-weight: 500;
  flex-shrink: 0;
}

.approval-operation .operation-text {
  color: var(--gray-800);
  word-break: break-word;
}

.approval-actions {
  display: flex;
  gap: 10px;
  padding: 12px 20px 16px;
}

.btn {
  flex: 1;
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-reject {
  background: var(--gray-100);
  color: var(--gray-700);
}

.btn-reject:hover:not(:disabled) {
  background: var(--gray-200);
}

.btn-approve {
  background: var(--main-color);
  color: var(--gray-0);
}

.btn-approve:hover:not(:disabled) {
  background: var(--main-700);
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.25);
}

.approval-processing {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px;
  color: var(--gray-600);
  font-size: 13px;
  background: var(--gray-25);
  border-top: 1px solid var(--gray-100);
}

.processing-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--gray-300);
  border-top-color: var(--main-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 滑入滑出动画 */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.25s ease;
}

.slide-up-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

@media (max-width: 520px) {
  .approval-content {
    padding: 12px 16px;
  }

  .approval-header h4 {
    font-size: 14px;
  }

  .approval-operation {
    font-size: 12px;
    padding: 8px 10px;
  }

  .approval-actions {
    padding: 10px 16px 12px;
    gap: 8px;
  }

  .btn {
    padding: 8px 16px;
    font-size: 13px;
  }
}
</style>
