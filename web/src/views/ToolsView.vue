<template>
  <div class="tools-container layout-container">
    <HeaderComponent
      title="工具箱"
      description="这里展示了各种可用的工具。点击查看详情。"
    >
    </HeaderComponent>

    <div class="tools-grid">
      <div v-for="tool in tools" :key="tool.id" class="tool-card" @click="navigateToTool(tool.id)">
        <div class="tool-icon">
          <component :is="tool.icon" />
        </div>
        <div class="tool-info">
          <h3>{{ tool.name }}</h3>
          <p>{{ tool.description }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { CalculatorOutlined, FileSearchOutlined, TranslationOutlined } from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import { Button as AButton } from 'ant-design-vue';

const router = useRouter();

const tools = ref([
  {
    id: 'calculator',
    name: '计算器',
    description: '进行各种数学计算',
    icon: CalculatorOutlined,
  },
  {
    id: 'file-analyzer',
    name: '文件分析器',
    description: '分析各种文件的内容和结构',
    icon: FileSearchOutlined,
  },
  {
    id: 'translator',
    name: '翻译工具',
    description: '在不同语言之间进行翻译',
    icon: TranslationOutlined,
  },
  // 可以继续添加更多工具...
]);

const navigateToTool = (toolId) => {
  router.push({ name: 'ToolsComponent', params: { id: toolId } });
};
</script>

<style scoped lang="less">
.tools-container {
  padding: 0;
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 20px;
  padding: 24px;
}

.tool-card {
  background-color: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: all 0.3s ease;

  &:hover {
    transform: translateY(-5px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  .tool-icon {
    font-size: 24px;
    margin-bottom: 10px;
    color: #1890ff;
  }

  .tool-info {
    h3 {
      margin: 0 0 10px;
      font-size: 18px;
    }

    p {
      margin: 0;
      color: #666;
      font-size: 14px;
    }
  }
}
</style>
