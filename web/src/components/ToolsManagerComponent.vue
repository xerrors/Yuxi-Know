<template>
  <div class="tools-manager-container extension-page-root">
    <div v-if="loading" class="loading-bar-wrapper">
      <div class="loading-bar"></div>
    </div>
    <div class="layout-wrapper" :class="{ 'content-loading': loading }">
      <!-- 左侧：工具列表 -->
      <div class="sidebar-list">
        <div class="sidebar-toolbar">
          <div class="search-box">
            <a-input
              v-model:value="searchQuery"
              placeholder="搜索工具..."
              allow-clear
              class="search-input"
            >
              <template #prefix><Search :size="14" class="text-muted" /></template>
            </a-input>
          </div>

          <a-tooltip title="刷新工具">
            <a-button class="sidebar-tool" :disabled="loading" @click="fetchTools">
              <RotateCw :size="14" />
            </a-button>
          </a-tooltip>

          <a-tooltip :title="`当前分类：${currentCategoryLabel}`">
            <a-dropdown trigger="click">
              <a-button
                class="sidebar-tool category-trigger"
                :class="{ active: !!selectedCategory }"
              >
                <SlidersHorizontal :size="14" />
              </a-button>
              <template #overlay>
                <a-menu :selectedKeys="[selectedCategory || 'all']" @click="handleCategorySelect">
                  <a-menu-item key="all">全部分类</a-menu-item>
                  <a-menu-item v-for="cat in categories" :key="cat">
                    {{ categoryLabels[cat] || cat }}
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </a-tooltip>
        </div>

        <div class="list-container">
          <div v-if="filteredTools.length === 0" class="empty-text">
            <a-empty :image="false" description="无匹配工具" />
          </div>
          <template v-for="(tool, index) in filteredTools" :key="tool.id">
            <div
              class="list-item"
              :class="{ active: currentTool?.id === tool.id }"
              @click="selectTool(tool)"
            >
              <div class="item-header">
                <component
                  :is="getToolIcon(tool.id)"
                  v-if="getToolIcon(tool.id)"
                  :size="16"
                  class="item-icon"
                />
                <span class="item-name">{{ tool.name }}</span>
              </div>
              <div class="item-details item-details-inline">
                <span class="item-category item-meta">{{
                  categoryLabels[tool.category] || tool.category
                }}</span>
                <div class="item-tags">
                  <a-tag v-for="tag in tool.tags" :key="tag" size="small" class="tool-tag">{{
                    tag
                  }}</a-tag>
                </div>
              </div>
            </div>
            <div v-if="index < filteredTools.length - 1" class="list-separator"></div>
          </template>
        </div>
      </div>

      <!-- 右侧：详情面板 -->
      <div class="main-panel">
        <div v-if="!currentTool" class="unselected-state">
          <div class="hint-box">
            <Wrench :size="40" class="text-muted" />
            <p>请在左侧选择工具查看详情</p>
          </div>
        </div>

        <template v-else>
          <div class="panel-top-bar">
            <div class="panel-title-stack">
              <h2>{{ currentTool.name }}</h2>
              <code class="panel-title-meta">{{ currentTool.id }}</code>
            </div>
          </div>

          <div class="detail-section-container">
            <div class="detail-section">
              <div class="section-header">
                <FileText :size="14" />
                <span>描述</span>
              </div>
              <div class="section-content description">
                {{ currentTool.description || '无描述' }}
              </div>
            </div>

            <div class="detail-section" v-if="currentTool.config_guide">
              <div class="section-header">
                <FileText :size="14" />
                <span>配置说明</span>
              </div>
              <div class="section-content description config-guide">
                {{ currentTool.config_guide }}
              </div>
            </div>

            <div class="detail-section">
              <div class="section-header">
                <Tag :size="14" />
                <span>分类</span>
              </div>
              <div class="section-content">
                <a-tag :color="categoryColors[currentTool.category] || 'default'">
                  {{ categoryLabels[currentTool.category] || currentTool.category }}
                </a-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="section-header">
                <Tags :size="14" />
                <span>标签</span>
              </div>
              <div class="section-content">
                <a-tag v-for="tag in currentTool.tags" :key="tag">{{ tag }}</a-tag>
                <span v-if="!currentTool.tags?.length" class="text-muted">无</span>
              </div>
            </div>

            <div class="detail-section" v-if="currentTool.args?.length">
              <div class="section-header">
                <List :size="14" />
                <span>参数</span>
              </div>
              <div class="section-content">
                <a-table
                  :dataSource="currentTool.args"
                  :columns="argColumns"
                  size="small"
                  :pagination="false"
                  bordered
                  class="args-table"
                />
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  Search,
  Wrench,
  Tag,
  Tags,
  FileText,
  List,
  SlidersHorizontal,
  RotateCw
} from 'lucide-vue-next'
import { toolApi } from '@/apis/tool_api'
import { getToolIcon } from '@/components/ToolCallingResult/toolRegistry'

const loading = ref(false)
const searchQuery = ref('')
const selectedCategory = ref('')

const tools = ref([])
const currentTool = ref(null)

const categories = ['buildin', 'mysql', 'debug']
const categoryLabels = {
  buildin: '内置工具',
  mysql: 'MySQL',
  debug: '调试'
}
const categoryColors = {
  buildin: 'blue',
  mysql: 'green',
  debug: 'orange'
}

const argColumns = [
  { title: '参数名', dataIndex: 'name', key: 'name' },
  { title: '类型', dataIndex: 'type', key: 'type', width: 80 },
  { title: '描述', dataIndex: 'description', key: 'description' }
]

const filteredTools = computed(() => {
  let result = tools.value
  if (selectedCategory.value) {
    result = result.filter((t) => t.category === selectedCategory.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        t.description?.toLowerCase().includes(q) ||
        t.config_guide?.toLowerCase().includes(q)
    )
  }
  return result
})

const currentCategoryLabel = computed(
  () =>
    categoryLabels[selectedCategory.value] ||
    (selectedCategory.value ? selectedCategory.value : '全部分类')
)

const fetchTools = async () => {
  loading.value = true
  try {
    const result = await toolApi.getTools()
    tools.value = result?.data || []
    // 默认选中第一个工具
    if (!currentTool.value && tools.value.length > 0) {
      currentTool.value = tools.value[0]
    }
  } catch {
    message.error('加载工具失败')
  } finally {
    loading.value = false
  }
}

const selectTool = (record) => {
  currentTool.value = record
}

const handleCategorySelect = ({ key }) => {
  selectedCategory.value = key === 'all' ? '' : key
}

onMounted(fetchTools)

// 暴露方法给父组件
defineExpose({
  fetchTools
})
</script>

<style scoped lang="less">
@import '@/assets/css/extensions.less';

.list-item {
  .item-details {
    .item-tags {
      display: flex;
      gap: 2px;
      flex-wrap: wrap;
      max-width: 100px;
      justify-content: flex-end;
      .tool-tag {
        color: var(--gray-500);
        font-size: 11px;
        padding: 0 4px;
        margin: 0;
        border: none;
      }
    }
  }
}

.args-table {
  :deep(.ant-table) {
    font-size: 12px;
  }
}

.config-guide {
  white-space: pre-line;
}
</style>
