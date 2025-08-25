<template>
  <div class="database-empty" v-if="!state.showPage">
    <a-empty>
      <template #description>
        <span>
          前往 <router-link to="/setting" style="color: var(--main-color); font-weight: bold;">设置</router-link> 页面启用知识图谱。
        </span>
      </template>
    </a-empty>
  </div>
  <div class="graph-container layout-container" v-else>
    <HeaderComponent
      title="图数据库"
      :description="graphDescription"
    >
      <template #actions>
        <div class="status-wrapper">
          <div class="status-indicator" :class="graphStatusClass"></div>
          <span class="status-text">{{ graphStatusText }}</span>
        </div>
        <a-button type="default" @click="openLink('http://localhost:7474/')" :icon="h(GlobalOutlined)">
          Neo4j 浏览器
        </a-button>
        <a-button type="default" @click="state.showInfoModal = true" :icon="h(InfoCircleOutlined)">
          说明
        </a-button>
        <a-button type="primary" @click="state.showModal = true" ><UploadOutlined/> 上传文件</a-button>
        <a-button v-if="unindexedCount > 0" type="primary" @click="indexNodes" :loading="state.indexing">
          <SyncOutlined/> 为{{ unindexedCount }}个节点添加索引
        </a-button>
      </template>
    </HeaderComponent>

    <div class="actions">
      <div class="actions-left">
        <input
          v-model="state.searchInput"
          placeholder="输入要查询的实体"
          style="width: 300px"
          @keydown.enter="onSearch"
        />
        <a-button
          type="primary"
          :loading="state.searchLoading"
          :disabled="state.searchLoading"
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
    <a-empty v-show="graphData.nodes.length === 0" style="padding: 4rem 0;"/>

    <a-modal
      :open="state.showModal" title="上传文件"
      @ok="addDocumentByFile"
      @cancel="() => state.showModal = false"
      ok-text="添加到图数据库" cancel-text="取消"
      :confirm-loading="state.processing">
      <div class="upload">
        <div class="note">
          <p>上传的文件内容参考 test/data/A_Dream_of_Red_Mansions_tiny.jsonl 中的格式：</p>
        </div>
        <a-upload-dragger
          class="upload-dragger"
          v-model:fileList="fileList"
          name="file"
          :fileList="fileList"
          :max-count="1"
          action="/api/knowledge/files/upload"
          :headers="getAuthHeaders()"
          @change="handleFileUpload"
          @drop="handleDrop"
        >
          <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
          <p class="ant-upload-hint">
            目前仅支持上传 jsonl 文件。
          </p>
        </a-upload-dragger>
      </div>
    </a-modal>

    <!-- 说明弹窗 -->
    <a-modal
      :open="state.showInfoModal"
      title="图数据库说明"
      @cancel="() => state.showInfoModal = false"
      :footer="null"
      width="600px"
    >
      <div class="info-content">
        <p>本页面展示的是 Neo4j 图数据库中的知识图谱信息。</p>
        <p>具体展示内容包括：</p>
        <ul>
          <li>带有 <code>Entity</code> 标签的节点</li>
          <li>带有 <code>RELATION</code> 类型的关系边</li>
        </ul>
        <p>注意：</p>
        <ul>
          <li>这里仅展示用户上传的实体和关系，不包含知识库中自动创建的图谱。</li>
          <li>查询逻辑基于 <code>graphbase.py</code> 中的 <code>get_sample_nodes</code> 方法实现：</li>
        </ul>
        <pre><code>MATCH (n:Entity)-[r]-&gt;(m:Entity)
RETURN
    {id: elementId(n), name: n.name} AS h,
    {type: r.type, source_id: elementId(n), target_id: elementId(m)} AS r,
    {id: elementId(m), name: m.name} AS t
LIMIT $num</code></pre>
        <p>如需查看完整的 Neo4j 数据库内容，请使用 "Neo4j 浏览器" 按钮访问原生界面。</p>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { Graph } from "@antv/g6";
import { computed, onMounted, reactive, ref, h } from 'vue';
import { message, Button as AButton } from 'ant-design-vue';
import { useConfigStore } from '@/stores/config';
import { UploadOutlined, SyncOutlined, GlobalOutlined, InfoCircleOutlined } from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import { neo4jApi } from '@/apis/graph_api';
import { useUserStore } from '@/stores/user';

const configStore = useConfigStore();
const cur_embed_model = computed(() => configStore.config?.embed_model);
const modelMatched = computed(() => !graphInfo?.value?.embed_model_name || graphInfo.value.embed_model_name === cur_embed_model.value)

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
  showInfoModal: false,
  precessing: false,
  indexing: false,
  showPage: true,
})

// 计算未索引节点数量
const unindexedCount = computed(() => {
  return graphInfo.value?.unindexed_node_count || 0;
});

const loadGraphInfo = () => {
  state.loadingGraphInfo = true
  neo4jApi.getInfo()
    .then(data => {
      console.log(data)
      graphInfo.value = data.data
      state.loadingGraphInfo = false
    })
    .catch(error => {
      console.error(error)
      message.error(error.message || '加载图数据库信息失败')
      state.loadingGraphInfo = false
    })
}

const getGraphData = () => {
  // 计算每个节点的度数（连接数）
  const nodeDegrees = {};

  // 初始化所有节点的度数为0
  graphData.nodes.forEach(node => {
    nodeDegrees[node.id] = 0;
  });

  // 计算每个节点的连接数
  graphData.edges.forEach(edge => {
    nodeDegrees[edge.source_id] = (nodeDegrees[edge.source_id] || 0) + 1;
    nodeDegrees[edge.target_id] = (nodeDegrees[edge.target_id] || 0) + 1;
  });

  return {
    nodes: graphData.nodes.map(node => {
      // 计算节点大小，基础大小为15，每个连接增加5的大小，最小为15，最大为50
      const degree = nodeDegrees[node.id] || 0;
      const nodeSize = Math.min(15 + degree * 5, 50);

      return {
        id: node.id,
        data: {
          label: node.name,
          degree: degree, // 存储度数信息
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
  state.processing = true
  const files = fileList.value.filter(file => file.status === 'done').map(file => file.response.file_path)
  neo4jApi.addEntities(files[0])
    .then((data) => {
      if (data.status === 'success') {
        message.success(data.message);
        state.showModal = false;
      } else {
        throw new Error(data.message);
      }
    })
    .catch((error) => {
      console.error(error)
      message.error(error.message || '添加文件失败');
    })
    .finally(() => state.processing = false)
};

const loadSampleNodes = () => {
  state.fetching = true
  neo4jApi.getSampleNodes('neo4j', sampleNodeCount.value)
    .then((data) => {
      graphData.nodes = data.result.nodes
      graphData.edges = data.result.edges
      console.log(graphData)
      setTimeout(() => renderGraph(), 500)
    })
    .catch((error) => {
      console.error(error)
      message.error(error.message || '加载节点失败');
    })
    .finally(() => state.fetching = false)
}

const onSearch = () => {
  if (state.searchLoading) {
    message.error('请稍后再试')
    return
  }

  if (graphInfo?.value?.embed_model_name !== cur_embed_model.value) {
    // if (!graphInfo?.value?.embed_model_name) {
    //   message.error('请先上传文件(jsonl)')
    //   return
    // }

    // if (!confirm(`构建图数据库时向量模型为 ${graphInfo?.value?.embed_model_name}，当前向量模型为 ${cur_embed_model.value}，是否继续查询？`)) {
    //   return
    // }
  }

  if (!state.searchInput) {
    message.error('请输入要查询的实体')
    return
  }

  state.searchLoading = true
  neo4jApi.queryNode(state.searchInput)
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
      renderGraph()
    })
    .catch((error) => {
      console.error('查询错误:', error);
      message.error(`查询出错：${error.message || '未知错误'}`);
    })
    .finally(() => state.searchLoading = false)
};

const renderGraph = () => {

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
      collide: {
        radius: 40,
        strength: 0.5, // 碰撞强度
      },
    },
    node: {
      type: 'circle',
      style: {
        labelText: (d) => d.data.label,
        // 使用节点度数来决定大小
        size: (d) => {
          const degree = d.data.degree || 0;
          // 基础大小为15，每个连接增加5的大小，最小为15，最大为50
          return Math.min(15 + degree * 5, 50);
        },
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
  window.addEventListener('resize', renderGraph);
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

const graphDescription = computed(() => {
  const dbName = graphInfo.value?.graph_name || '';
  const entityCount = graphInfo.value?.entity_count || 0;
  const relationCount = graphInfo.value?.relationship_count || 0;
  const unindexed = unindexedCount.value > 0 ? `，${unindexedCount.value}个节点未索引` : '';

  return `${dbName} - 共 ${entityCount} 实体，${relationCount} 个关系；${unindexed}`;
});

// 为未索引节点添加索引
const indexNodes = () => {
  // 判断 embed_model_name 是否相同
  if (!modelMatched.value) {
    message.error(`向量模型不匹配，无法添加索引，当前向量模型为 ${cur_embed_model.value}，图数据库向量模型为 ${graphInfo.value?.embed_model_name}`)
    return
  }

  if (state.processing) {
    message.error('后台正在处理，请稍后再试')
    return
  }

  state.indexing = true;
  neo4jApi.indexEntities('neo4j')
    .then(data => {
      message.success(data.message || '索引添加成功');
      // 刷新图谱信息
      loadGraphInfo();
    })
    .catch(error => {
      console.error(error);
      message.error(error.message || '添加索引失败');
    })
    .finally(() => {
      state.indexing = false;
    });
};

const getAuthHeaders = () => {
  const userStore = useUserStore();
  return userStore.getAuthHeaders();
};

const openLink = (url) => {
  window.open(url, '_blank')
}

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

.status-text {
  margin-left: 8px;
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

.info-content {
  line-height: 1.6;

  ul {
    padding-left: 20px;
    margin: 10px 0;
  }

  li {
    margin: 8px 0;
  }

  code {
    background-color: #f0f0f0;
    padding: 2px 4px;
    border-radius: 4px;
    font-family: monospace;
  }

  pre {
    background-color: #f8f8f8;
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
    margin: 15px 0;
    font-size: 13px;
  }
}
</style>
