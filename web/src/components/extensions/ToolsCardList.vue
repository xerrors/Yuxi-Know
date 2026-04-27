<template>
  <div class="tools-cards-page extension-page-root">
    <PageShoulder search-placeholder="搜索工具..." v-model:search="searchQuery">
      <template #filters>
        <a-dropdown trigger="click">
          <a-button
            class="lucide-icon-btn"
            :class="{ active: !!selectedCategory }"
            style="margin-left: 4px"
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
      </template>
      <template #actions>
        <a-tooltip title="刷新工具">
          <a-button class="lucide-icon-btn" :disabled="loading" @click="fetchTools">
            <RefreshCw :size="14" />
          </a-button>
        </a-tooltip>
      </template>
    </PageShoulder>

    <div v-if="filteredTools.length === 0" class="extension-card-grid-empty-state">
      <a-empty :image="false" :description="searchQuery ? '无匹配工具' : '暂无工具'" />
    </div>

    <ExtensionCardGrid v-else>
      <InfoCard
        v-for="tool in filteredTools"
        :key="tool.id"
        :title="tool.name"
        :subtitle="tool.id"
        :description="tool.description || '无描述'"
        :default-icon="getToolIcon(tool.id) || WrenchIcon"
        :tags="toolTags(tool)"
        @click="selectTool(tool)"
      >
      </InfoCard>
    </ExtensionCardGrid>

    <a-modal
      v-model:open="detailVisible"
      :title="currentTool?.name || '工具详情'"
      :footer="null"
      width="640px"
    >
      <template v-if="currentTool">
        <div class="tool-detail-content detail-section-container">
          <div class="detail-section">
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
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Wrench, RefreshCw, SlidersHorizontal, FileText, Tag, Tags, List } from 'lucide-vue-next'
import { toolApi } from '@/apis/tool_api'
import { getToolIcon } from '@/components/ToolCallingResult/toolRegistry'
import ExtensionCardGrid from './ExtensionCardGrid.vue'
import InfoCard from '@/components/shared/InfoCard.vue'
import PageShoulder from '@/components/shared/PageShoulder.vue'

const WrenchIcon = Wrench

const loading = ref(false)
const searchQuery = ref('')
const selectedCategory = ref('')
const tools = ref([])
const currentTool = ref(null)
const detailVisible = ref(false)

const categories = ['buildin', 'mysql', 'debug']
const categoryLabels = { buildin: '内置工具', mysql: 'MySQL', debug: '调试' }
const categoryColors = { buildin: 'blue', mysql: 'green', debug: 'orange' }

const toolTags = (tool) => {
  const tags = []
  if (tool.category) {
    tags.push({
      name: categoryLabels[tool.category] || tool.category,
      color: categoryColors[tool.category] || 'blue'
    })
  }
  ;(tool.tags || []).slice(0, 2).forEach((t) => tags.push(t))
  return tags
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

const selectTool = (tool) => {
  currentTool.value = tool
  detailVisible.value = true
}

const handleCategorySelect = ({ key }) => {
  selectedCategory.value = key === 'all' ? '' : key
}

const fetchTools = async () => {
  loading.value = true
  try {
    const result = await toolApi.getTools()
    tools.value = result?.data || []
  } catch {
    message.error('加载工具失败')
  } finally {
    loading.value = false
  }
}

onMounted(fetchTools)

defineExpose({ fetchTools, loading })
</script>

<style lang="less" scoped>
@import '@/assets/css/extensions.less';

.tool-detail-content {
  max-height: 70vh;
  overflow-y: auto;
  padding: 0;
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
