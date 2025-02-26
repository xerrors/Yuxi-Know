<template>
  <a-card class="config-card" style="max-width: 960px">
    <a-form layout="vertical">
      <div
        v-for="(item, index) in configList"
        :key="index"
        class="config-item"
      >
        <a-row :gutter="[16, 8]" align="middle">
          <a-col :span="8">
            <a-input
              v-model:value="item.key"
              placeholder="模型名称"
              readonly
              class="key-input"
            />
          </a-col>
          <a-col :span="14">
            <a-input
              v-model:value="item.value"
              @change="updateValue(index)"
              placeholder="模型本地路径"
              class="value-input"
            />
          </a-col>
          <a-col :span="2" class="delete-btn-col">
            <a-button
              type="link"
              danger
              class="delete-btn"
              @click="deleteConfig(index)"
            >
              <DeleteOutlined />
            </a-button>
          </a-col>
        </a-row>
      </div>

      <a-button block @click="addConfig" class="add-btn" :disabled="isAdding">
        <PlusOutlined /> 添加路径映射
      </a-button>
    </a-form>

    <a-modal
      title="添加路径映射"
      v-model:open="addConfigModalVisible"
      @ok="confirmAddConfig"
      class="config-modal"
    >
      <a-form layout="vertical">
        <a-form-item label="模型名称（与Huggingface名称一致，比如 BAAI/bge-large-zh-v1.5" required>
          <a-input
            v-model:value="newConfig.key"
            placeholder="请输入模型名称"
            class="modal-input"
          />
        </a-form-item>
        <a-form-item label="模型本地路径（绝对路径，比如 /hdd/models/BAAI/bge-large-zh-v1.5）" required>
          <a-input
            v-model:value="newConfig.value"
            placeholder="请输入模型本地路径"
            class="modal-input"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue';
import { message } from 'ant-design-vue';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue';

const props = defineProps({
  config: {
    type: Object,
    default: () => ({})
  }
});

const emit = defineEmits(['update:config']);

// 配置列表
const configList = reactive([]);

// 初始化配置列表
props.config && Object.entries(props.config).forEach(([key, value]) => {
  configList.push({ key, value });
});

// 控制模态框显示
const addConfigModalVisible = ref(false);
const isAdding = ref(false); // 添加新的ref变量

// 新增配置项数据
const newConfig = ref({ key: '', value: '' });

// 添加配置
const addConfig = () => {
  isAdding.value = true;  // 设置添加状态
  addConfigModalVisible.value = true;
};

// 确认添加配置
const confirmAddConfig = () => {
  if (newConfig.value.key === '' || newConfig.value.value === '') {
    message.warning('键或值不能为空');
    return;
  }
  if (configList.some(item => item.key === newConfig.value.key)) {
    message.warning('键已存在');
    return;
  }
  configList.push({ key: newConfig.value.key, value: newConfig.value.value });
  addConfigModalVisible.value = false;
  newConfig.value = { key: '', value: '' };
  isAdding.value = false;  // 重置添加状态
};

// 删除配置
const deleteConfig = (index) => {
  configList.splice(index, 1);
};

// 更新值
const updateValue = (index) => {
  // 值的更新实时反映在 configList 中，无需额外处理
};

// 将配置列表转换为对象
const configObject = computed(() => {
  return configList.reduce((acc, item) => {
    acc[item.key] = item.value;
    return acc;
  }, {});
});

// 监听配置变化并传递回父组件
watch(configObject, (newValue) => {
  emit('update:config', newValue);
}, { deep: true });

// 监听模态框关闭
watch(addConfigModalVisible, (newValue) => {
  if (!newValue) {
    isAdding.value = false;  // 当模态框关闭时重置添加状态
  }
});
</script>

<style scoped>
.config-card {
  background-color: var(--gray-10);
  border-radius: 8px;
  border: 1px solid var(--gray-300);
}

.config-item {
  border-bottom: 1px solid #f0f0f0;
  padding: 12px 0;
  transition: background-color 0.3s ease;
}

.config-item:hover {
  background-color: #fafafa;
}

.config-item:last-child {
  border-bottom: none;
}

.key-input {
  background-color: #f8f8f8;
  border-color: #e8e8e8;
}

.delete-btn-col {
  display: flex;
  justify-content: center;
  align-items: center;
}

.delete-btn {
  opacity: 0.6;
  transition: opacity 0.3s ease;
}

.delete-btn:hover {
  opacity: 1;
}

.add-btn {
  margin-top: 16px;
  height: 40px;
  transition: all 0.3s ease;
  width: auto;
}

.modal-input {
  margin-bottom: 8px;
}

:deep(.ant-modal-content) {
  border-radius: 8px;
}

:deep(.ant-card-body) {
  padding: 16px;
}
</style>

