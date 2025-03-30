<template>
  <div class="tools-container layout-container">
    <HeaderComponent
      title="工具箱"
      description="这里展示了各种可用的工具，重点是为了测试部分功能的页面。(注：不是大模型的工具)"
    >
    </HeaderComponent>
    <div class="tools-grid">
      <div v-for="tool in tools" :key="tool.id" class="tool-card" @click="navigateToTool(tool.url)">
        <div class="tool-header">
          <h3>{{ tool.title }}</h3>
        </div>
        <div class="tool-info">
          <p>{{ tool.description }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { CalculatorOutlined, FileSearchOutlined, TranslationOutlined } from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';

const router = useRouter();
const tools = ref([]);
const iconMap = ref({
  "text-chunking": FileSearchOutlined
})

const state = reactive({
  loadingTools: true,
})

const getTools = () => {
  state.loadingTools = true
  fetch('/api/tool/')
    .then(response => response.json())
    .then(data => {
      tools.value = data;
      state.loadingTools = false;
    })
    .catch(error => {
      console.error('Error fetching tools:', error);
      state.loadingTools = false;
    });
};

const navigateToTool = (toolUrl) => {
  router.push(toolUrl);
};

onMounted(() => {
  getTools();
});
</script>

<style scoped lang="less">
.tools-container {
  padding: 0;
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 20px;
  padding: 20px;

  .tool-card {
    display: flex;
    flex-direction: column;
    background-color: white;
    border: 1px solid var(--gray-300);
    border-radius: 8px;
    padding: 20px;
    transition: transform 0.1s ease, box-shadow 0.1s ease;
    cursor: pointer;

    &:hover {
      // transform: translateY(-1px);
      box-shadow: 0 5px 15px rgba(0,0,0,0.05);
    }

    .tool-header {
      display: flex;
      align-items: center;
      margin-bottom: 15px;
      font-size: 15px;

      .tool-icon {
        margin-right: 10px;
      }

      h3 {
        margin: 0;
      }
    }

    .tool-info {
      flex-grow: 1;

      p {
        margin: 0;
        color: var(--gray-800);
      }
    }
  }
}
</style>
