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
        <div class="status-wrapper">
          <div class="status-indicator" :class="graphStatusClass"></div>
          <span class="status-text">{{ graphStatusText }}</span>
        </div>
        <a-button type="default" @click="openLink('http://localhost:7474/')" :icon="h(GlobalOutlined)">
          Neo4j 浏览器
        </a-button>
        <a-button type="primary" @click="state.showModal = true" ><UploadOutlined/> 上传文件</a-button>
        <a-button v-if="unindexedCount > 0" type="primary" @click="indexNodes" :loading="state.indexing">
          <SyncOutlined/> 为{{ unindexedCount }}个节点添加索引
        </a-button>
      </template>
    </HeaderComponent>

    <div class="container-outter">
      <div class="main" id="container" ref="container" v-show="graphData.nodes.length > 0">
        <div class="actions">
          <div class="actions-left">
            <a-input
              v-model:value="state.searchInput"
              placeholder="输入要查询的实体"
              style="width: 300px"
              @keydown.enter="onSearch"
            >
              <template #suffix>
                <component :is="state.searchLoading ? LoadingOutlined : SearchOutlined" @click="onSearch" />
              </template>
            </a-input>
          </div>
          <div class="actions-right">
            <a-button type="default" @click="state.showInfoModal = true" :icon="h(InfoCircleOutlined)">
              说明
            </a-button>
            <a-input
              v-model:value="sampleNodeCount"
              placeholder="查询三元组数量"
              style="width: 100px"
              @keydown.enter="loadSampleNodes"
              :loading="state.fetching"
            >
              <template #suffix>
                <component :is="state.fetching ? LoadingOutlined : ReloadOutlined" @click="loadSampleNodes" />
              </template>
            </a-input>
          </div>
        </div>
        <div class="footer">
          <div class="tags">
            <a-tag :bordered="false" v-for="tag in graphTags" :key="tag.key" :color="tag.type">{{ tag.text }}</a-tag>
          </div>
        </div>
      </div>
      <a-empty v-show="graphData.nodes.length === 0" style="padding: 4rem 0;"/>
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
import { UploadOutlined, SyncOutlined, GlobalOutlined, InfoCircleOutlined, SearchOutlined, ReloadOutlined, LoadingOutlined } from '@ant-design/icons-vue';
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
        id: String(node.id),
        data: {
          label: node.name,
          degree: degree, // 存储度数信息
        },
      }
    }),
    edges: graphData.edges.map((edge, index) => {
      return {
        id: `edge-${index}`,
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
      // 优化布局性能参数
      alphaDecay: 0.1, // 增加衰减率，加快收敛速度
      alphaMin: 0.01, // 提高最小alpha值，更早停止模拟
      velocityDecay: 0.7, // 增加速度衰减，减少震荡
      iterations: 100, // 限制最大迭代次数
      // 力的配置
      force: {
        // 中心力 - 将节点拉向中心
        center: {
          x: 0.5,
          y: 0.5,
          strength: 0.1
        },
        // 排斥力 - 节点间相互排斥
        charge: {
          strength: -400, // 负值表示排斥力
          distanceMax: 400 // 限制力的作用距离
        },
        // 链接力 - 连接的节点相互吸引
        link: {
          distance: 100, // 理想链接距离
          strength: 0.8 // 链接强度
        }
      },
      collide: {
        radius: 40,
        strength: 0.8, // 增加碰撞强度，减少重叠
        iterations: 3 // 限制碰撞检测迭代次数
      },
    },
    node: {
      type: 'circle',
      style: {
        labelText: (d) => d.data.label,
        // 使用节点度数来决定大小
        size: (d) => {
          const degree = d.data.degree || 0;
          return Math.min(15 + degree * 5, 50);
        },
        // 现代化默认样式
        fillOpacity: 0.8,
        opacity: 0.8,
        stroke: '#ffffff',
        lineWidth: 1.5,
        shadowColor: '#94a3b8',
        shadowBlur: 4,
        'label-text-fill': '#334155',
      },
      palette: {
        field: 'label',
        color: [
          '#60a5fa', // sky-400
          '#34d399', // emerald-400
          '#f59e0b', // amber-500
          '#f472b6', // pink-400
          '#22d3ee', // cyan-400
          '#a78bfa', // violet-400
          '#f97316', // orange-500
          '#4ade80', // green-400
          '#f43f5e', // rose-500
          '#2dd4bf', // teal-400
        ],
      },
      state: {
        hidden: {
          opacity: 0.15,
          'label-text-opacity': 0,
        },
        focus: {
          opacity: 1,
          stroke: '#2563eb', // blue-600
          lineWidth: 2.5,
          shadowColor: '#60a5fa',
          shadowBlur: 16,
        },
      },
    },
    edge: {
      type: 'line',
      style: {
        labelText: (d) => d.data.label,
        labelBackground: '#ffffff',
        stroke: '#94a3b8',
        opacity: 0.6,
        lineWidth: 1.2,
        endArrow: true,
        'label-text-fill': '#334155',
      },
      state: {
        hidden: {
          opacity: 0.15,
          'label-text-opacity': 0,
        },
        focus: {
          opacity: 0.95,
          stroke: '#2563eb',
          lineWidth: 2,
          'label-text-opacity': 1,
        },
      },
    },
    behaviors: ['drag-element', 'zoom-canvas', 'drag-canvas'],
  });

  let activeNodeId = null;

  const getGraphItemIds = () => {
    const { nodes, edges } = graphInstance.getData();
    const nodeIds = nodes.map(node => node.id);
    const edgeIds = edges.map(edge => edge.id);
    return { nodeIds, edgeIds };
  };

  // 从事件对象中尽可能稳健地获取被点击元素的 id
  const getClickedElementId = (e) => {
    return e?.id || e?.data?.id || e?.target?.id || null;
  };

  const resetStyles = async () => {
    const { nodeIds, edgeIds } = getGraphItemIds();
    const allElementIds = [...nodeIds, ...edgeIds];
    const updates = {};
    allElementIds.forEach(id => {
        updates[id] = [];
    });

    if (allElementIds.length > 0) {
      await graphInstance.setElementState(updates);
    }
    activeNodeId = null;
    await graphInstance.draw();
  };

  graphInstance.on('node:click', async (e) => {
    const clickedNodeId = getClickedElementId(e);
    if (!clickedNodeId) return;

    if (activeNodeId === clickedNodeId) {
      await resetStyles();
      return;
    }

    activeNodeId = clickedNodeId;

    const { nodeIds: allNodeIds, edgeIds: allEdgeIds } = getGraphItemIds();
    const { edges: allEdges } = graphInstance.getData();

    const updates = {};

    // 1. All nodes and edges are hidden by default
    allNodeIds.forEach(id => updates[id] = ['hidden']);
    allEdgeIds.forEach(id => updates[id] = ['hidden']);

    // 2. Find neighbors and related edges
    const neighborSet = new Set();
    const relatedEdgeIds = [];
    allEdges.forEach((edge) => {
      if (edge.source === clickedNodeId) {
        neighborSet.add(edge.target);
        relatedEdgeIds.push(edge.id);
      } else if (edge.target === clickedNodeId) {
        neighborSet.add(edge.source);
        relatedEdgeIds.push(edge.id);
      }
    });
    const neighborNodeIds = Array.from(neighborSet);

    // 3. Set 'focus' state for the clicked node, its neighbors, and related edges.
    // This will overwrite the 'hidden' state.
    updates[clickedNodeId] = ['focus'];
    neighborNodeIds.forEach(id => updates[id] = ['focus']);
    relatedEdgeIds.forEach(id => updates[id] = ['focus']);

    // 4. Apply all state changes at once
    await graphInstance.setElementState(updates);
    await graphInstance.draw();
  });

  // 专门监听画布空白处的点击事件来重置样式
  graphInstance.on('canvas:click', resetStyles);
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

// 新增：将图谱信息拆分为多条标签用于展示
const graphTags = computed(() => {
  const tags = [];
  const dbName = graphInfo.value?.graph_name;
  const entityCount = graphInfo.value?.entity_count;
  const relationCount = graphInfo.value?.relationship_count;

  if (dbName) tags.push({ key: 'name', text: `图谱 ${dbName}`, type: 'blue' });
  if (typeof entityCount === 'number') tags.push({ key: 'entities', text: `实体 ${graphData.nodes.length} of ${entityCount}`, type: 'success' });
  if (typeof relationCount === 'number') tags.push({ key: 'relations', text: `关系 ${graphData.edges.length} of ${relationCount}`, type: 'purple' });
  if (unindexedCount.value > 0) tags.push({ key: 'unindexed', text: `未索引 ${unindexedCount.value}`, type: 'warning' });

  return tags;
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
@graph-header-height: 55px;

.graph-container {
  padding: 0;

  .header-container {
    height: @graph-header-height;
  }
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
  background: var(--gray-50);

  #container {
    width: 100%;
    height: 100%;
  }

  .actions,
  .footer {
    position: absolute;
    display: flex;
    justify-content: space-between;
    margin: 20px 0;
    padding: 0 24px;
    width: 100%;
    z-index: 999;
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

.footer {
  position: relative;
}

.footer {
  bottom: 0;
  z-index: 2; // 显示在画布之上
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
