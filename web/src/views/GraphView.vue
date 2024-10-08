<template>
  <div class="database-empty" v-if="!state.showPage">
    <a-empty>
      <template #description>
        <span>
          前往 <router-link to="/setting" style="color: var(--main-color); font-weight: bold;">设置</router-link> 页面配置图数据库。
        </span>
      </template>
    </a-empty>
  </div>
  <div class="graph-container layout-container" v-else>
    <HeaderComponent
      title="图数据库"
      :description="`${graphInfo?.database_name || ''} - 共 ${graphInfo?.entity_count || 0} 实体，${graphInfo?.relationship_count || 0} 个关系`"
    >
      <template #actions>
        <div class="status-wrapper">
          <div class="status-indicator" :class="graphStatusClass"></div>
        </div>
        <a-button type="primary" @click="state.showModal = true" ><UploadOutlined/> 上传文件</a-button>
      </template>
    </HeaderComponent>

    <div class="actions">
      <div class="actions-left">
        <input
          v-model="state.searchInput"
          placeholder="输入要查询的实体"
          style="width: 200px"
          @keydown.enter="onSearch"
        />
        <a-button
          type="primary"
          :loading="state.searchLoading"
          @click="onSearch"
        >
          检索实体
        </a-button>
      </div>
      <div class="actions-right">
        <input v-model="sampleNodeCount">
        <a-button @click="loadSampleNodes" :loading="state.fetching">获取节点</a-button>
      </div>
    </div>
    <div class="main" id="container" ref="container" v-show="graphData.nodes.length > 0"></div>
    <a-empty v-show="graphData.nodes.length === 0"  style="padding: 4rem 0;"/>

    <a-modal
      :open="state.showModal" title="上传文件"
      @ok="addDocumentByFile"
      @cancel="() => state.showModal = false"
      ok-text="添加到图数据库" cancel-text="取消"
      :confirm-loading="state.precessing">
      <div class="upload">
        <a-upload-dragger
          class="upload-dragger"
          v-model:fileList="fileList"
          name="file"
          :fileList="fileList"
          :max-count="1"
          :disabled="state.precessing"
          action="/api/data/upload"
          @change="handleFileUpload"
          @drop="handleDrop"
        >
          <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
          <p class="ant-upload-hint">
            目前仅支持上传 jsonl 文件。且同名文件无法重复添加。
          </p>
        </a-upload-dragger>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { Graph } from "@antv/g6";
import { computed, onMounted, reactive, ref } from 'vue';
import { message, Button as AButton } from 'ant-design-vue';
import { useConfigStore } from '@/stores/config';
import { UploadOutlined } from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';

const configStore = useConfigStore()

let graphInstance
const graphInfo = ref(null)
const container = ref(null);
const fileList = ref([]);
const sampleNodeCount = ref(100);
const graphData = reactive({
  nodes: [],
  edges: [],
});

const state = reactive({
  fetching: false,
  loadingGraphInfo: false,
  searchInput: '',
  searchLoading: false,
  showModal: false,
  precessing: false,
  showPage: computed(() => configStore.config.enable_knowledge_base && configStore.config.enable_knowledge_graph),
})


const loadGraphInfo = () => {
  state.loadingGraphInfo = true
  fetch('/api/data/graph', {
    method: "GET",
  })
    .then(response => response.json())
    .then(data => {
      console.log(data)
      graphInfo.value = data.graph
      state.loadingGraphInfo = false
    })
    .catch(error => {
      console.error(error)
      message.error(error.message)
      state.loadingGraphInfo = false
    })
}

const getGraphData = () => {
  return {
    nodes: graphData.nodes.map(node => {
      return {
        id: node.id,
        data: {
          label: node.name
        },
      }
    }),
    edges: graphData.edges.map(edge => {
      return {
        source: edge.source_id,
        target: edge.target_id,
        data: {
          label: edge.type
        }
      }
    }),
  }
}

const addDocumentByFile = () => {
  state.precessing = true
  const files = fileList.value.filter(file => file.status === 'done').map(file => file.response.file_path)
  fetch('/api/data/graph/add', {
    method: 'POST',
    headers: {
      "Content-Type": "application/json"  // 添加 Content-Type 头
    },
    body: JSON.stringify({
      file_path: files[0]
    }),
  })
  .then(response => response.json())
  .then((data) => {
    message.success(data.message);
    state.showModal = false;
  })
  .catch((error) => {
    message.error(error.message);
  })
  .finally(() => state.precessing = false)
};

const loadSampleNodes = () => {
  state.fetching = true
  fetch(`/api/data/graph/nodes?kgdb_name=neo4j&num=${sampleNodeCount.value}`)
    .then((res) => {
      if (res.ok) {
        return res.json();
      } else {
        throw new Error("加载失败");
      }
    })
    .then((data) => {
      graphData.nodes = data.result.nodes
      graphData.edges = data.result.edges
      console.log(graphData)
      randerGraph()
    })
    .catch((error) => {
      message.error(error.message);
    })
    .finally(() => state.fetching = false)
}

const onSearch = () => {
  if (!state.searchInput) {
    message.error('请输入要查询的实体')
    return
  }

  const cur_embed_model = configStore.config.embed_model
  if (cur_embed_model !== 'zhipu-embedding-3') {
    message.error('当前不支持实体检索，请在设置中选择向量模型为 zhipu-embedding-3')
    return
  }

  state.searchLoading = true
  fetch(`/api/data/graph/node?entity_name=${state.searchInput}`)
    .then((res) => {
      if (!res.ok) {
        return res.json().then(errorData => {
          throw new Error(errorData.message || `查询失败：${res.status} ${res.statusText}`);
        });
      }
      return res.json();
    })
    .then((data) => {
      if (!data.result || !data.result.nodes || !data.result.edges) {
        throw new Error('返回数据格式不正确');
      }
      graphData.nodes = data.result.nodes
      graphData.edges = data.result.edges
      if (graphData.nodes.length === 0) {
        message.info('未找到相关实体')
      }
      console.log(data)
      console.log(graphData)
      randerGraph()
    })
    .catch((error) => {
      console.error('查询错误:', error);
      message.error(`查询出错：${error.message}`);
    })
    .finally(() => state.searchLoading = false)
};

const randerGraph = () => {

  if (graphInstance) {
    graphInstance.destroy();
  }

  initGraph();
  graphInstance.setData(getGraphData());
  graphInstance.render();
}

const initGraph = () => {
  graphInstance = new Graph({
    container: container.value,
    width: container.value.offsetWidth,
    height: container.value.offsetHeight,
    autoFit: true,
    autoResize: true,
    layout: {
      type: 'd3-force',
      preventOverlap: true,
      kr: 20,
      collide: {
        strength: 1.0,
      },
    },
    node: {
      type: 'circle',
      style: {
        labelText: (d) => d.data.label,
        size: 70,
      },
      palette: {
        field: 'label',
        color: 'tableau',
      },
    },
    edge: {
      type: 'line',
      style: {
        labelText: (d) => d.data.label,
        labelBackground: '#fff',
        endArrow: true,
      },
    },
    behaviors: ['drag-element', 'zoom-canvas', 'drag-canvas'],
  });
  window.addEventListener('resize', randerGraph);
}

onMounted(() => {
  loadGraphInfo();
  loadSampleNodes();
});


const handleFileUpload = (event) => {
  console.log(event)
  console.log(fileList.value)
}

const handleDrop = (event) => {
  console.log(event)
  console.log(fileList.value)
}

const graphStatusClass = computed(() => {
  if (state.loadingGraphInfo) return 'loading';
  return graphInfo.value?.status === 'open' ? 'open' : 'closed';
});

const graphStatusText = computed(() => {
  if (state.loadingGraphInfo) return '加载中';
  return graphInfo.value?.status === 'open' ? '已连接' : '已关闭';
});

</script>

<style lang="less" scoped>
.graph-container {
  padding: 0;
}

.status-wrapper {
  display: flex;
  align-items: center;
  margin-right: 16px;
  font-size: 14px;
  color: rgba(0, 0, 0, 0.65);
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;

  &.loading {
    background-color: #faad14;
    animation: pulse 1.5s infinite ease-in-out;
  }

  &.open {
    background-color: #52c41a;
  }

  &.closed {
    background-color: #f5222d;
  }
}

@keyframes pulse {
  0% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.2);
    opacity: 1;
  }
  100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
}

.actions {
  display: flex;
  justify-content: space-between;
  margin: 20px 0;
  padding: 0 24px;

  .actions-left, .actions-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  input {
    width: 100px;
    border-radius: 8px;
    padding: 4px 12px;
    border: 2px solid var(--main-300);
    outline: none;
    height: 42px;

    &:focus {
      border-color: var(--main-color);
    }
  }

  button {
    border-width: 2px;
    height: 40px;
    box-shadow: none;
  }
}


.upload {
  margin-bottom: 20px;

  .upload-dragger {
    margin: 0px;
  }
}

#container {
  background: #F7F7F7;
  margin: 20px 24px;
  border-radius: 16px;
  width: calc(100% - 48px);
  height: calc(100vh - 200px);
  resize: horizontal;
  overflow: hidden;
}

.database-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  flex-direction: column;
  color: var(--gray-900);
}
</style>
