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
    >
      <template #actions>
        <div class="db-selector">
        <div class="status-wrapper">
          <div class="status-indicator" :class="graphStatusClass"></div>
          <span class="status-text">{{ graphStatusText }}</span>
        </div>
          <span class="label">知识库: </span>
          <a-select
            v-model:value="state.selectedDbId"
            style="width: 200px"
            :options="state.dbOptions"
            @change="handleDbChange"
            :loading="state.loadingDatabases"
          />
        </div>
        <!-- <a-button type="default" @click="openLink('http://localhost:7474/')" :icon="h(GlobalOutlined)">
          Neo4j 浏览器
        </a-button> -->
        <a-button type="primary" @click="state.showModal = true" ><UploadOutlined/> 上传文件</a-button>
        <a-button v-if="unindexedCount > 0" type="primary" @click="indexNodes" :loading="state.indexing">
          <SyncOutlined v-if="!state.indexing"/> 为{{ unindexedCount }}个节点添加索引
        </a-button>
      </template>
    </HeaderComponent>

    <div class="container-outter">
      <GraphCanvas
        ref="graphRef"
        :graph-data="graph.graphData"
        :highlight-keywords="[state.searchInput]"
        @node-click="graph.handleNodeClick"
        @edge-click="graph.handleEdgeClick"
        @canvas-click="graph.handleCanvasClick"
      >
        <template #top>
          <div class="actions">
            <div class="actions-left">
              <a-input
                v-model:value="state.searchInput"
                :placeholder="isNeo4j ? '输入要查询的实体' : '输入要查询的实体 (*为全部)'"
                style="width: 300px"
                @keydown.enter="onSearch"
                allow-clear
              >
                <template #suffix>
                  <component :is="state.searchLoading ? LoadingOutlined : SearchOutlined" @click="onSearch" />
                </template>
              </a-input>
              <a-input
                v-model:value="sampleNodeCount"
                placeholder="查询数量"
                style="width: 100px"
                @keydown.enter="loadSampleNodes"
                :loading="graph.fetching"
              >
                <template #suffix>
                  <component :is="graph.fetching ? LoadingOutlined : ReloadOutlined" @click="loadSampleNodes" />
                </template>
              </a-input>
            </div>
            <div class="actions-right">
              <a-button type="default" @click="state.showInfoModal = true" :icon="h(InfoCircleOutlined)">
                说明
              </a-button>
            </div>
          </div>
        </template>
        <template #content>
          <a-empty v-show="graph.graphData.nodes.length === 0" style="padding: 4rem 0;"/>
        </template>
        <template #bottom>
          <div class="footer">
            <GraphInfoPanel
              v-if="isNeo4j"
              :graph-info="graphInfo"
              :graph-data="graph.graphData"
              :unindexed-count="unindexedCount"
              :model-matched="modelMatched"
              @index-nodes="indexNodes"
              @export-data="exportGraphData"
            />
            <LightRAGInfoPanel
              v-else
              :stats="state.lightragStats"
              :graph-data="graph.graphData"
              :database-name="getDatabaseName()"
              @export-data="exportGraphData"
            />
          </div>
        </template>
        </GraphCanvas>
        <!-- 详情浮动卡片 -->
        <GraphDetailPanel
          :visible="graph.showDetailDrawer"
          :item="graph.selectedItem"
          :type="graph.selectedItemType"
          :nodes="graph.graphData.nodes"
          @close="graph.handleCanvasClick"
          style="width: 380px;"
        />
      </div>

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
          accept=".jsonl"
          action="/api/knowledge/files/upload?allow_jsonl=true"
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
      <div class="info-content" v-if="isNeo4j">
        <p>本页面展示的是 Neo4j 图数据库中的知识图谱信息。</p>
        <p>具体展示内容包括：</p>
        <ul>
          <li>带有 <code>Entity</code> 标签的节点</li>
          <li>带有 <code>RELATION</code> 类型的关系边</li>
        </ul>
        <p>注意：</p>
        <ul>
          <li>这里仅展示用户上传的实体和关系，不包含知识库中自动创建的图谱。</li>
          <li>查询逻辑基于 <code>graphbase.py</code> 中的 <code>get_sample_nodes</code> 方法实现。</li>
        </ul>
      </div>
      <div class="info-content" v-else>
        <p>本页面展示的是 LightRAG 知识库生成的图谱信息。</p>
        <p>数据来源于选定的知识库实例。</p>
        <p>支持通过实体名称进行模糊搜索，输入 "*" 可查看采样全图。</p>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, h } from 'vue';
import { message } from 'ant-design-vue';
import { useConfigStore } from '@/stores/config';
import { UploadOutlined, SyncOutlined, GlobalOutlined, InfoCircleOutlined, SearchOutlined, ReloadOutlined, LoadingOutlined, HighlightOutlined } from '@ant-design/icons-vue';
import HeaderComponent from '@/components/HeaderComponent.vue';
import { neo4jApi, unifiedApi } from '@/apis/graph_api';
import { useUserStore } from '@/stores/user';
import GraphCanvas from '@/components/GraphCanvas.vue';
import GraphInfoPanel from '@/components/GraphInfoPanel.vue';
import LightRAGInfoPanel from '@/components/LightRAGInfoPanel.vue';
import GraphDetailPanel from '@/components/GraphDetailPanel.vue';
import UploadModal from '@/components/FileUploadModal.vue';
import { useGraph } from '@/composables/useGraph';

const configStore = useConfigStore();
const cur_embed_model = computed(() => configStore.config?.embed_model);
const modelMatched = computed(() => !graphInfo?.value?.embed_model_name || graphInfo.value.embed_model_name === cur_embed_model.value)

const graphRef = ref(null)
const graphInfo = ref(null)
const fileList = ref([]);
const sampleNodeCount = ref(100);

const graph = reactive(useGraph(graphRef));

const state = reactive({
  loadingGraphInfo: false,
  loadingDatabases: false,
  searchInput: '',
  searchLoading: false,
  showModal: false,
  showInfoModal: false,
  processing: false,
  indexing: false,
  showPage: true,
  selectedDbId: 'neo4j',
  dbOptions: [],
  lightragStats: null,
})

const isNeo4j = computed(() => state.selectedDbId === 'neo4j');

// 计算未索引节点数量
const unindexedCount = computed(() => {
  return graphInfo.value?.unindexed_node_count || 0;
});

const loadDatabases = async () => {
  state.loadingDatabases = true;
  try {
    const res = await unifiedApi.getGraphs();
    if (res.success && res.data) {
      state.dbOptions = res.data.map(db => ({
        label: `${db.name} (${db.type})`,
        value: db.id,
        type: db.type
      }));

      // If no selection or invalid selection, select first
      if (!state.selectedDbId || !state.dbOptions.find(o => o.value === state.selectedDbId)) {
        if (state.dbOptions.length > 0) {
          state.selectedDbId = state.dbOptions[0].value;
        }
      }
    }
  } catch (error) {
    console.error('Failed to load databases:', error);
  } finally {
    state.loadingDatabases = false;
  }
};

const handleDbChange = () => {
  // Clear current data
  graph.clearGraph();
  state.searchInput = '';
  state.lightragStats = null;

  if (isNeo4j.value) {
    loadGraphInfo();
  } else {
    // Also load stats for LightRAG
    loadLightRAGStats();
  }
  loadSampleNodes();
};

const loadLightRAGStats = () => {
  unifiedApi.getStats(state.selectedDbId).then(res => {
    if(res.success) {
      state.lightragStats = res.data;
    }
  }).catch(e => console.error(e));
};

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
  graph.fetching = true

  unifiedApi.getSubgraph({
    db_id: state.selectedDbId,
    node_label: '*',
    max_nodes: sampleNodeCount.value
  })
    .then((data) => {
      // Normalize data structure if needed
      const result = data.data;
      graph.updateGraphData(result.nodes, result.edges);
      console.log(graph.graphData)
    })
    .catch((error) => {
      console.error(error)
      message.error(error.message || '加载节点失败');
    })
    .finally(() => graph.fetching = false)
}

const onSearch = () => {
  if (state.searchLoading) {
    message.error('请稍后再试')
    return
  }

  if (isNeo4j.value && graphInfo?.value?.embed_model_name !== cur_embed_model.value) {
    // 可选：提示模型不一致
  }

  if (!state.searchInput && isNeo4j.value) {
    message.error('请输入要查询的实体')
    return
  }

  state.searchLoading = true

  unifiedApi.getSubgraph({
    db_id: state.selectedDbId,
    node_label: state.searchInput || '*',
    max_nodes: sampleNodeCount.value
  })
    .then((data) => {
      const result = data.data;
      if (!result || !result.nodes || !result.edges) {
        throw new Error('返回数据格式不正确');
      }
      graph.updateGraphData(result.nodes, result.edges);
      if (graph.graphData.nodes.length === 0) {
        message.info('未找到相关实体')
      }
      console.log(data)
      console.log(graph.graphData)
    })
    .catch((error) => {
      console.error('查询错误:', error);
      message.error(`查询出错：${error.message || '未知错误'}`);
    })
    .finally(() => state.searchLoading = false)
};

onMounted(async () => {
  await loadDatabases();
  loadGraphInfo(); // Load default (Neo4j) info
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

const exportGraphData = () => {
  const dataStr = JSON.stringify({
    nodes: graph.graphData.nodes,
    edges: graph.graphData.edges,
    graphInfo: isNeo4j.value ? graphInfo.value : state.lightragStats,
    source: state.selectedDbId,
    exportTime: new Date().toISOString()
  }, null, 2);

  const dataBlob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(dataBlob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `graph-data-${state.selectedDbId}-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  message.success('图谱数据已导出');
};

const getAuthHeaders = () => {
  const userStore = useUserStore();
  return userStore.getAuthHeaders();
};

const openLink = (url) => {
  window.open(url, '_blank')
}

const getDatabaseName = () => {
  const selectedDb = state.dbOptions.find(db => db.value === state.selectedDbId);
  return selectedDb ? selectedDb.label : state.selectedDbId;
};

</script>

<style lang="less" scoped>
@graph-header-height: 55px;

.graph-container {
  padding: 0;
  background-color: var(--gray-0);

  .header-container {
    height: @graph-header-height;
  }
}

.db-selector {
  display: flex;
  align-items: center;
  margin-right: 20px;

  .label {
    margin-right: 8px;
    font-weight: 500;
    color: var(--color-text-secondary);
  }
}

.status-wrapper {
  display: flex;
  align-items: center;
  margin-right: 16px;
  font-size: 14px;
  color: var(--color-text-secondary);
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
    background-color: var(--color-warning-500);
    animation: pulse 1.5s infinite ease-in-out;
  }

  &.open {
    background-color: var(--color-success-500);
  }

  &.closed {
    background-color: var(--color-error-500);
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


.upload {
  margin-bottom: 20px;

  .upload-dragger {
    margin: 0px;
  }
}

.container-outter {
  width: 100%;
  height: calc(100vh - @graph-header-height);
  overflow: hidden;
  background: var(--gray-10);

  .actions,
  .footer {
    display: flex;
    justify-content: space-between;
    margin: 20px 0;
    padding: 0 24px;
    width: 100%;
  }

  .tags {
    display: flex;
    gap: 8px;
  }
}

.actions {
  top: 0;

  .actions-left, .actions-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  :deep(.ant-input) {
    padding: 2px 10px;
  }

  button {
    height: 37px;
    box-shadow: none;
  }
}
</style>