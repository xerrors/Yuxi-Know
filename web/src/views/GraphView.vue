<template>
  <div class="graph-container">
    <div class="info">
      <h1>Neo4j 图数据库</h1>
      <p>基于 Neo4j 构建的图数据库。</p>
      </div>
    <div class="actions">
      <div class="actions-left">
        <a-button @click="state.showModal = true">上传文件</a-button>
        <a-modal v-model:open="state.showModal" title="上传文件" @ok="handleUpload">
          <div class="upload">
            <a-upload-dragger
              class="upload-dragger"
              v-model:fileList="fileList"
              name="file"
              :max-count="1"
              :disabled="state.precessing"
              action="/api/database/upload"
              @change="handleFileUpload"
              @drop="handleDrop"
            >
              <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
              <p class="ant-upload-hint">
                目前仅支持上传文本文件，如 .pdf, .txt, .md。且同名文件无法重复添加。
              </p>
            </a-upload-dragger>
          </div>
          <a-button
            type="primary"
            @click="addDocumentByFile"
            :loading="state.precessing"
            :disabled="fileList.length === 0"
            style="margin: 0px 20px 20px 0;"
          >
            添加到图数据库
          </a-button>
          <a-button @click="handleRefresh" :loading="state.refrashing">刷新状态</a-button>
        </a-modal>
      </div>
      <div class="action-right">
        <input
          v-model="state.searchInput"
          placeholder="输入要查询的实体"
          style="width: 200px"
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
    <div class="main" id="container"></div>

  </div>
</template>

<script setup>
import { Graph } from "@antv/g6";
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from "ant-design-vue";

let graphInstance
const fileList = ref([]);
const subgraph = reactive({
  nodes: [
    { id: '1', name: 'node1' },
    { id: '2', name: 'node2' },
    { id: '3', name: 'node3' },
    { id: '4', name: 'node4' },
    { id: '5', name: 'node5' },
  ],
  edges: [
    { id: 'e1', source_id: '1', target_id: '2', type: 'edge1' },
    { id: 'e2', source_id: '1', target_id: '3', type: 'edge2' },
    { id: 'e3', source_id: '2', target_id: '4', type: 'edge3' },
    { id: 'e4', source_id: '2', target_id: '5', type: 'edge4' },
  ],
});

const state = reactive({
  searchInput: '',
  searchLoading: false,
  showModal: false,
  precessing: false,
})

const getCurWidth = () => document.getElementById("container").offsetWidth
const getCurHeight = () => document.getElementById("container").offsetHeight

const graphData = computed(() => {
  return {
    nodes: subgraph.nodes.map(node => {
      return {
        id: node.id,
        data: {
          label: node.name
        },
      }
    }),
    edges: subgraph.edges.map(edge => {
      return {
        source: edge.source_id,
        target: edge.target_id,
        data: {
          label: edge.type
        }
      }
    }),
  }
})

const addDocumentByFile = () => {
  state.precessing = true
  const files = fileList.value.filter(file => file.status === 'done').map(file => file.response.file_path)
  fetch('/api/database/graph/add', {
    method: 'POST',
    body: JSON.stringify({
      file_path: files[0]
    }),
  })
  // .then(response => response.json())
  //   .then((data) => {
  //     message.success(data.message);
  //   })
  //   .catch((error) => {
  //     message.error(error.message);
  //   })
  //   .finally(() => state.precessing = false)
};

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
      subgraph.nodes = data.result.nodes
      subgraph.edges = data.result.edges
      console.log(data)
      console.log(subgraph)
      randerGraph()
    })
    .catch((error) => {
      message.error(error.message);
    })
    .finally(() => state.searchLoading = false)
};

const randerGraph = () => {
  graphInstance.setData(graphData.value);
  graphInstance.render();
}




onMounted(() => {
  graphInstance = new Graph({
    container: document.getElementById("container"),
    width: getCurWidth(),
    height: getCurHeight(),
    autoFit: true,
    autoResize: true,
    layout: {
      type: 'force-atlas2',
      preventOverlap: true,
      kr: 100,
    },
    node: {
      type: 'circle',
      style: {
        labelText: (d) => d.data.label,
        size: 40,
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
      },
    },
    behaviors: ['drag-element'],
  });
  graphInstance.setData(graphData.value);
  graphInstance.render();
  window.addEventListener('resize', randerGraph);
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
  padding: 20px;
}

.actions {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;

  input {
    margin-right: 10px;
    border-radius: 8px;
    padding: 4px 12px;
    border: 2px solid #d9d9d9;
    outline: none;
    height: 42px;

    &:focus {
      border-color: var(--main-color);
    }
  }

  button {
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
  height: 400px;
}





</style>
