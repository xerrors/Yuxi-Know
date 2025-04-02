<template>
  <div class="refs" v-if="showRefs">
    <div class="tags">
      <!-- <span class="item btn" @click="likeThisResponse(msg)"><LikeOutlined /></span> -->
      <!-- <span class="item btn" @click="dislikeThisResponse(msg)"><DislikeOutlined /></span> -->
      <span v-if="msg.meta?.server_model_name" class="item"><BulbOutlined /> {{ msg.meta.server_model_name }}</span>
      <span
        v-if="showKey('copy')"
        class="item btn" @click="copyText(msg.content)" title="复制"><CopyOutlined /></span>
      <span
        v-if="showKey('regenerate')"
        class="item btn" @click="regenerateMessage()" title="重新生成"><ReloadOutlined /></span>
      <span
        v-if="showKey('subGraph') && hasSubGraphData(msg)"
        class="item btn"
        @click="openSubGraph(msg)"
      >
        <DeploymentUnitOutlined /> 关系图
      </span>
      <span
        class="item btn"
        @click="showWebResult(msg)"
        v-if="showKey('webSearch') && msg.refs?.web_search.results.length > 0"
      >
        <GlobalOutlined /> 网页搜索 {{ msg.refs.web_search?.results.length }}
      </span>
      <span class="filetag item btn"
        v-for="(results, filename) in msg.groupedResults"
        :key="filename"
        @click="toggleDrawer(filename)"
      >
        <FileTextOutlined /> {{ filename }}
        <a-drawer
          v-model:open="openDetail[filename]"
          :title="filename"
          width="700"
          :contentWrapperStyle="{ maxWidth: '100%'}"
          placement="right"
          class="retrieval-detail"
          rootClassName="root"
        >
          <div class="fileinfo">
            <p><FileOutlined /> {{ results[0].file.type }}</p>
            <p><ClockCircleOutlined /> {{ formatDate(results[0].file.created_at) }}</p>
          </div>
          <div class="results-list">
            <div v-for="res in results" :key="res.id" class="result-item">
              <div class="result-meta">
                <div class="score-info">
                  <span>
                    <strong>相似度：</strong>
                    <a-progress :percent="getPercent(res.distance)"/>
                  </span>
                  <span v-if="res.rerank_score">
                    <strong>重排序：</strong>
                    <a-progress :percent="getPercent(res.rerank_score)"/>
                  </span>
                </div>
                <div class="result-id">ID: #{{ res.id }}</div>
              </div>
              <div class="result-text">{{ res.entity.text }}</div>
            </div>
          </div>
        </a-drawer>
      </span>
    </div>
    <a-modal
      v-model:open="subGraphVisible"
      title="相关实体与关系"
      :width="800"
      :footer="null"
    >
      <GraphContainer :graphData="subGraphData" />
    </a-modal>
    <a-drawer
      v-model:open="webResultVisible"
      title="网页搜索结果"
      width="700"
      :contentWrapperStyle="{ maxWidth: '100%'}"
      placement="right"
      class="web-result-detail"
      rootClassName="root"
    >
      <div class="results-list">
        <div v-for="result in webResults" :key="result.url" class="result-item">
          <div class="result-meta">
            <div class="score-info">
              <span>
                <strong>相关度：</strong>
                <a-progress :percent="getPercent(result.score)"/>
              </span>
            </div>
            <div class="result-url">
              <a :href="result.url" target="_blank">{{ result.url }}</a>
            </div>
          </div>
          <div class="result-content">
            <h3 class="result-title">{{ result.title }}</h3>
            <div class="result-text">{{ result.content }}</div>
          </div>
        </div>
      </div>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { useClipboard } from '@vueuse/core'
import { message } from 'ant-design-vue'
import {
  GlobalOutlined,
  FileTextOutlined,
  CopyOutlined,
  DeploymentUnitOutlined,
  BulbOutlined,
  FileOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import GraphContainer from './GraphContainer.vue'  // 导入 GraphContainer 组件


const emit = defineEmits(['retry']);
const props = defineProps({
  message: Object,
  showRefs: {
    type: [Array, Boolean],
    default: () => false
  }
})

const msg = ref(props.message)

// 使用 useClipboard 实现复制功能
const { copy, isSupported } = useClipboard()

const showKey = (key) => {
  if (props.showRefs === true) {
    return true
  }
  return props.showRefs.includes(key)
}

// 定义 copy 方法
const copyText = async (text) => {
  if (isSupported) {
    try {
      await copy(text)
      message.success('文本已复制到剪贴板')
    } catch (error) {
      console.error('复制失败:', error)
      message.error('复制失败，请手动复制')
    }
  } else {
    console.warn('浏览器不支持自动复制')
    message.warning('浏览器不支持自动复制，请手动复制')
  }
}

// 其他方法
const likeThisResponse = (msg) => {
  console.log('Like this response:', msg)
}

const dislikeThisResponse = (msg) => {
  console.log('Dislike this response:', msg)
}

// 使用 reactive 创建一个响应式对象来存储每个文件的抽屉状态
const openDetail = reactive({})

// 初始化 openDetail 对象
for (const filename in msg.value.groupedResults) {
  openDetail[filename] = false
}

const toggleDrawer = (filename) => {
  openDetail[filename] = !openDetail[filename]
}

const showRefs = computed(() => (msg.value.role=='received' || msg.value.role=='assistant') && msg.value.status=='finished')

const subGraphVisible = ref(false)
const subGraphData = ref(null)


const openSubGraph = (msg) => {
  if (hasSubGraphData(msg)) {
    subGraphData.value = msg.refs.graph_base.results
    subGraphVisible.value = true
  } else {
    console.error('无法获取子图数据')
  }
}

const closeSubGraph = () => {
  subGraphVisible.value = false
}

// 添加网页搜索结果相关变量
const webResultVisible = ref(false)
const webResults = ref(null)

// 添加显示网页搜索结果的方法
const showWebResult = (msg) => {
  if (msg.refs?.web_search) {
    webResults.value = msg.refs?.web_search.results
    webResultVisible.value = true
  } else {
    console.error('无法获取网页搜索结果')
  }
}

const hasSubGraphData = (msg) => {
  return msg.refs &&
         msg.refs.graph_base &&
         msg.refs.graph_base.results.nodes.length > 0;
}

// 添加日期格式化函数
const formatDate = (timestamp) => {
  return new Date(timestamp * 1000).toLocaleString()
}

// 添加百分比计算函数
const getPercent = (value) => {
  return parseFloat((value * 100).toFixed(2))
}

// 添加重新生成方法
const regenerateMessage = () => {
  emit('retry')
}
</script>

<style lang="less" scoped>
.refs {
  display: flex;
  margin-bottom: 20px;
  color: var(--gray-500);
  font-size: 13px;
  gap: 10px;

  .item {
    background: var(--gray-100);
    color: var(--gray-700);
    padding: 2px 8px;
    border-radius: 8px;
    font-size: 13px;
    user-select: none;

    &.btn {
      cursor: pointer;
      &:hover {
        background: var(--gray-200);
      }
      &:active {
        background: var(--gray-300);
      }
    }
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;

    .filetag {
      display: flex;
      align-items: center;
      gap: 5px;
    }
  }
}

.retrieval-detail {
  .fileinfo {
    display: flex;
    justify-content: space-between;
    padding: 12px 16px;
    background-color: #f5f5f5;
    border-radius: 4px;
    margin-bottom: 16px;

    p {
      margin: 0;
      color: #666;
    }
  }

  .score-info {
    display: flex;
    flex-wrap: wrap;
    gap: 2rem;
    margin-bottom: 8px;

    span {
      display: flex;
      align-items: center;

      strong {
        margin-right: 8px;
        white-space: nowrap;
        color: #666;
      }

      .ant-progress {
        width: 170px;
        margin-bottom: 0;
        margin-inline: 10px;

        .ant-progress-bg {
          background-color: #666;
        }
      }
    }
  }

  .result-id {
    font-size: 12px;
    color: #999;
    margin-bottom: 8px;
  }

  .result-text {
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
    background-color: #f9f9f9;
    padding: 12px;
    border-radius: 4px;
    border: 1px solid #e8e8e8;
  }
}

.results-list {
  .result-item {
    border-bottom: 1px solid #f0f0f0;
    padding: 16px 0;

    &:last-child {
      border-bottom: none;
    }
  }

  .result-meta {
    margin-bottom: 12px;
  }
}

.web-result-detail {
  .results-list {
    .result-item {
      border-bottom: 1px solid #f0f0f0;
      padding: 16px 0;

      &:last-child {
        border-bottom: none;
      }
    }

    .result-meta {
      margin-bottom: 12px;

      .score-info {
        display: flex;
        flex-wrap: wrap;
        gap: 2rem;
        margin-bottom: 8px;

        span {
          display: flex;
          align-items: center;

          strong {
            margin-right: 8px;
            white-space: nowrap;
            color: #666;
          }

          .ant-progress {
            width: 170px;
            margin-bottom: 0;
            margin-inline: 10px;

            .ant-progress-bg {
              background-color: #666;
            }
          }
        }
      }

      .result-url {
        font-size: 12px;
        color: #1677FF;
        margin-bottom: 8px;
        word-break: break-all;
      }
    }

    .result-content {
      .result-title {
        font-size: 16px;
        font-weight: bold;
        margin-bottom: 8px;
        color: #333;
      }

      .result-text {
        font-size: 14px;
        line-height: 1.6;
        white-space: pre-wrap;
        word-break: break-word;
        background-color: #f9f9f9;
        padding: 12px;
        border-radius: 4px;
        border: 1px solid #e8e8e8;
      }
    }
  }
}
</style>