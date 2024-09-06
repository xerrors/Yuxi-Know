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
    <div class="info">
      <h2>图数据库 {{ graphInfo?.database_name }}</h2>
      <p>
        <span v-if="state.loadingGraphInfo">加载中</span>
        <span class="green-dot" v-if="graphInfo?.status == 'open'"></span>
        <span class="red-dot" v-else></span>
        <span>{{ graphInfo?.status }}</span> ·
        <span>共 {{ graphInfo?.entity_count }} 实体，{{ graphInfo?.relationship_count }} 个关系</span>
      </p>
    </div>
    <div class="actions">
      <div class="actions-left">
        <a-button @click="state.showModal = true"><UploadOutlined /> 上传文件</a-button>
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
              action="/api/database/upload"
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
        <input v-model="sampleNodeCount">
        <a-button @click="loadSampleNodes">获取节点</a-button>
      </div>
      <div class="actions-right">
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
    </div>
    <div class="main" id="container" ref="container"></div>
  </div>
</template>

<script setup>
import { Graph } from "@antv/g6";
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from "ant-design-vue";
import { useConfigStore } from '@/stores/config';
import { UploadOutlined } from '@ant-design/icons-vue';

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
  loadingGraphInfo: false,
  searchInput: '',
  searchLoading: false,
  showModal: false,
  precessing: false,
  showPage: computed(() => configStore.config.enable_knowledge_base && configStore.config.enable_knowledge_graph),
})


const loadGraphInfo = () => {
  state.loadingGraphInfo = true
  fetch('/api/database/graph', {
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
  fetch('/api/database/graph/add', {
    method: 'POST',
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
  fetch(`/api/database/graph/nodes?kgdb_name=neo4j&num=${sampleNodeCount.value}`)
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
}

const onSearch = () => {
  if (!state.searchInput) {
    message.error('请输入要查询的实体')
    return
  }

  state.searchLoading = true
  fetch(`/api/database/graph/node?entity_name=${state.searchInput}`)
    .then((res) => {
      if (res.ok) {
        return res.json();
      } else {
        throw new Error("查询失败");
      }
    })
    .then((data) => {
      graphData.nodes = data.result.nodes
      graphData.edges = data.result.edges
      console.log(data)
      console.log(graphData)
      randerGraph()
    })
    .catch((error) => {
      message.error(error.message);
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

</script>

<style lang="less" scoped>
.graph-container {

  .info span.green-dot, .info span.red-dot {
    display: inline-block;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    margin: 0 5px;
  }

  .info span.green-dot {
    background: #52c41a;
  }

  .info span.red-dot {
    background: #f5222d;
  }

  .info {
    margin-bottom: 20px;
  }
}


.actions {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;

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
  margin: 20px 0;
  border-radius: 16px;
  width: 100%;
  height: 800px;
  resize: horizontal;
}

.database-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  flex-direction: column;
  color: var(--c-text-light-1);
}
</style>
