<template>
  <a-modal
    v-model:open="modalVisible"
    :title="server?.name || 'MCP 服务器详情'"
    width="800px"
    :footer="null"
    @cancel="handleClose"
    class="mcp-detail-modal"
  >
    <div class="detail-container" v-if="server">
      <!-- 头部状态 -->
      <div class="detail-header">
        <div class="server-info">
          <span class="server-icon">{{ server.icon || '🔌' }}</span>
          <div class="server-meta">
            <h3 class="server-name">{{ server.name }}</h3>
            <span class="server-status" :class="{ enabled: server.enabled }">
              {{ server.enabled ? '已启用' : '已禁用' }}
            </span>
          </div>
        </div>
        <div class="header-actions">
          <a-button @click="handleTestConnection" :loading="testLoading">
            <template #icon><ApiOutlined /></template>
            测试连接
          </a-button>
        </div>
      </div>

      <!-- Tab 导航 -->
      <a-tabs v-model:activeKey="activeTab" class="detail-tabs">
        <a-tab-pane key="general" tab="通用">
          <div class="tab-content">
            <div class="info-grid">
              <div class="info-item">
                <label>传输类型</label>
                <span>
                  <a-tag :color="getTransportColor(server.transport)">
                    {{ server.transport }}
                  </a-tag>
                </span>
              </div>

              <!-- HTTP 类型显示 URL -->
              <template v-if="server.transport === 'streamable_http' || server.transport === 'sse'">
                <div class="info-item">
                  <label>服务器 URL</label>
                  <span class="url-text">{{ server.url || '-' }}</span>
                </div>
                <div
                  class="info-item"
                  v-if="server.headers && Object.keys(server.headers).length > 0"
                >
                  <label>请求头</label>
                  <pre class="headers-pre">{{ JSON.stringify(server.headers, null, 2) }}</pre>
                </div>
                <div class="info-item" v-if="server.timeout">
                  <label>HTTP 超时</label>
                  <span>{{ server.timeout }} 秒</span>
                </div>
                <div class="info-item" v-if="server.sse_read_timeout">
                  <label>SSE 读取超时</label>
                  <span>{{ server.sse_read_timeout }} 秒</span>
                </div>
              </template>

              <!-- StdIO 类型显示 command/args -->
              <template v-if="server.transport === 'stdio'">
                <div class="info-item">
                  <label>命令</label>
                  <span class="command-text">{{ server.command || '-' }}</span>
                </div>
                <div class="info-item" v-if="server.args && server.args.length > 0">
                  <label>参数</label>
                  <span>
                    <a-tag v-for="(arg, index) in server.args" :key="index" size="small">
                      {{ arg }}
                    </a-tag>
                  </span>
                </div>
              </template>

              <div class="info-item" v-if="server.description">
                <label>描述</label>
                <span>{{ server.description }}</span>
              </div>
              <div class="info-item" v-if="server.tags && server.tags.length > 0">
                <label>标签</label>
                <span>
                  <a-tag v-for="tag in server.tags" :key="tag">{{ tag }}</a-tag>
                </span>
              </div>
              <div class="info-item">
                <label>创建时间</label>
                <span>{{ formatTime(server.created_at) }}</span>
              </div>
              <div class="info-item">
                <label>更新时间</label>
                <span>{{ formatTime(server.updated_at) }}</span>
              </div>
              <div class="info-item">
                <label>创建人</label>
                <span>{{ server.created_by }}</span>
              </div>
            </div>
          </div>
        </a-tab-pane>

        <a-tab-pane key="tools" :tab="`工具 (${tools.length})`">
          <div class="tab-content tools-tab">
            <!-- 工具栏 -->
            <div class="tools-toolbar">
              <a-input-search
                v-model:value="toolSearchText"
                placeholder="搜索工具..."
                style="width: 240px"
                allowClear
              />
              <a-button @click="handleRefreshTools" :loading="toolsLoading">
                <template #icon><ReloadOutlined /></template>
                刷新工具
              </a-button>
            </div>

            <!-- 工具列表 -->
            <a-spin :spinning="toolsLoading">
              <div v-if="filteredTools.length === 0" class="empty-tools">
                <a-empty :description="toolsError || '暂无工具'" />
              </div>
              <div v-else class="tools-list">
                <div
                  v-for="tool in filteredTools"
                  :key="tool.name"
                  class="tool-card"
                  :class="{ disabled: !tool.enabled }"
                >
                  <div class="tool-header">
                    <div class="tool-info">
                      <span class="tool-name">{{ tool.name }}</span>
                      <a-tooltip :title="`ID: ${tool.id}`">
                        <InfoCircleOutlined class="info-icon" />
                      </a-tooltip>
                    </div>
                    <div class="tool-actions">
                      <a-switch
                        :checked="tool.enabled"
                        @change="handleToggleTool(tool)"
                        :loading="toggleToolLoading === tool.name"
                        size="small"
                      />
                      <a-tooltip title="复制工具名称">
                        <a-button type="text" size="small" @click="copyToolName(tool.name)">
                          <CopyOutlined />
                        </a-button>
                      </a-tooltip>
                    </div>
                  </div>
                  <div class="tool-description" v-if="tool.description">
                    {{ tool.description }}
                  </div>
                  <a-collapse
                    v-if="tool.parameters && Object.keys(tool.parameters).length > 0"
                    ghost
                  >
                    <a-collapse-panel key="params" header="参数">
                      <div class="params-list">
                        <div
                          v-for="(param, paramName) in tool.parameters"
                          :key="paramName"
                          class="param-item"
                        >
                          <div class="param-header">
                            <span class="param-name">{{ paramName }}</span>
                            <span class="param-required" v-if="tool.required?.includes(paramName)"
                              >必填</span
                            >
                            <span class="param-type">{{ param.type || 'any' }}</span>
                          </div>
                          <div class="param-desc" v-if="param.description">
                            {{ param.description }}
                          </div>
                        </div>
                      </div>
                    </a-collapse-panel>
                  </a-collapse>
                </div>
              </div>
            </a-spin>
          </div>
        </a-tab-pane>

        <a-tab-pane key="prompts" tab="提示">
          <div class="tab-content empty-tab">
            <a-empty description="提示功能即将推出">
              <template #image>
                <span style="font-size: 48px">📝</span>
              </template>
            </a-empty>
          </div>
        </a-tab-pane>

        <a-tab-pane key="resources" tab="资源">
          <div class="tab-content empty-tab">
            <a-empty description="资源功能即将推出">
              <template #image>
                <span style="font-size: 48px">📦</span>
              </template>
            </a-empty>
          </div>
        </a-tab-pane>
      </a-tabs>
    </div>
  </a-modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { notification } from 'ant-design-vue'
import {
  ApiOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  CopyOutlined
} from '@ant-design/icons-vue'
import { mcpApi } from '@/apis/mcp_api'
import { formatDateTime } from '@/utils/time'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  server: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:visible', 'update'])

// 状态
const activeTab = ref('general')
const tools = ref([])
const toolsLoading = ref(false)
const toolsError = ref(null)
const toolSearchText = ref('')
const testLoading = ref(false)
const toggleToolLoading = ref(null)

// 计算属性
const modalVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
})

const filteredTools = computed(() => {
  if (!toolSearchText.value) return tools.value
  const search = toolSearchText.value.toLowerCase()
  return tools.value.filter(
    (t) =>
      t.name.toLowerCase().includes(search) ||
      (t.description && t.description.toLowerCase().includes(search))
  )
})

// 监听服务器变化，加载工具列表
watch(
  () => props.server,
  (newServer) => {
    if (newServer) {
      activeTab.value = 'general'
      fetchTools()
    }
  },
  { immediate: true }
)

// 获取工具列表
const fetchTools = async () => {
  if (!props.server) return

  try {
    toolsLoading.value = true
    toolsError.value = null
    const result = await mcpApi.getMcpServerTools(props.server.name)
    if (result.success) {
      tools.value = result.data || []
    } else {
      toolsError.value = result.message || '获取工具列表失败'
      tools.value = []
    }
  } catch (err) {
    console.error('获取工具列表失败:', err)
    toolsError.value = err.message || '获取工具列表失败'
    tools.value = []
  } finally {
    toolsLoading.value = false
  }
}

// 刷新工具列表
const handleRefreshTools = async () => {
  if (!props.server) return

  try {
    toolsLoading.value = true
    const result = await mcpApi.refreshMcpServerTools(props.server.name)
    if (result.success) {
      notification.success({ message: result.message })
      await fetchTools()
    } else {
      notification.error({ message: result.message || '刷新失败' })
    }
  } catch (err) {
    console.error('刷新工具列表失败:', err)
    notification.error({ message: err.message || '刷新失败' })
  } finally {
    toolsLoading.value = false
  }
}

// 测试连接
const handleTestConnection = async () => {
  if (!props.server) return

  try {
    testLoading.value = true
    const result = await mcpApi.testMcpServer(props.server.name)
    if (result.success) {
      notification.success({ message: result.message })
    } else {
      notification.warning({ message: result.message || '连接失败' })
    }
  } catch (err) {
    console.error('测试连接失败:', err)
    notification.error({ message: err.message || '测试失败' })
  } finally {
    testLoading.value = false
  }
}

// 切换工具启用状态
const handleToggleTool = async (tool) => {
  if (!props.server) return

  try {
    toggleToolLoading.value = tool.name
    const result = await mcpApi.toggleMcpServerTool(props.server.name, tool.name)
    if (result.success) {
      notification.success({ message: result.message })
      // 更新本地状态
      const targetTool = tools.value.find((t) => t.name === tool.name)
      if (targetTool) {
        targetTool.enabled = result.enabled
      }
      emit('update')
    } else {
      notification.error({ message: result.message || '操作失败' })
    }
  } catch (err) {
    console.error('切换工具状态失败:', err)
    notification.error({ message: err.message || '操作失败' })
  } finally {
    toggleToolLoading.value = null
  }
}

// 复制工具名称
const copyToolName = async (name) => {
  try {
    await navigator.clipboard.writeText(name)
    notification.success({ message: '已复制到剪贴板' })
  } catch {
    notification.error({ message: '复制失败' })
  }
}

// 格式化时间
const formatTime = (timeStr) => formatDateTime(timeStr)

// 获取传输类型颜色
const getTransportColor = (transport) => {
  const colors = {
    sse: 'orange',
    stdio: 'green',
    streamable_http: 'blue'
  }
  return colors[transport] || 'blue'
}

// 关闭弹框
const handleClose = () => {
  emit('update:visible', false)
}
</script>

<style lang="less" scoped>
.mcp-detail-modal {
  :deep(.ant-modal-body) {
    padding: 0;
  }
}

.detail-container {
  .detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    border-bottom: 1px solid var(--gray-150);
    background: var(--gray-25);

    .server-info {
      display: flex;
      align-items: center;
      gap: 12px;

      .server-icon {
        font-size: 32px;
      }

      .server-meta {
        .server-name {
          margin: 0 0 4px 0;
          font-size: 18px;
          font-weight: 600;
          color: var(--gray-900);
        }

        .server-status {
          font-size: 12px;
          color: var(--gray-600);
          padding: 2px 8px;
          background: var(--gray-100);
          border-radius: 4px;

          &.enabled {
            background: var(--color-success-50);
            color: var(--color-success-600);
          }
        }
      }
    }
  }

  .detail-tabs {
    :deep(.ant-tabs-nav) {
      padding: 0 24px;
      margin-bottom: 0;
    }

    .tab-content {
      padding: 20px 24px;
      min-height: 300px;
      max-height: 500px;
      overflow-y: auto;
    }
  }

  .info-grid {
    display: grid;
    gap: 16px;

    .info-item {
      display: flex;
      flex-direction: column;
      gap: 4px;

      label {
        font-size: 12px;
        color: var(--gray-500);
        font-weight: 500;
      }

      span {
        font-size: 14px;
        color: var(--gray-900);
      }

      .url-text {
        font-family: 'Monaco', 'Consolas', monospace;
        font-size: 13px;
        word-break: break-all;
        background: var(--gray-50);
        padding: 8px 12px;
        border-radius: 4px;
      }

      .command-text {
        font-family: 'Monaco', 'Consolas', monospace;
        font-size: 13px;
        background: var(--gray-50);
        padding: 8px 12px;
        border-radius: 4px;
      }

      .headers-pre {
        font-family: 'Monaco', 'Consolas', monospace;
        font-size: 12px;
        background: var(--gray-50);
        padding: 12px;
        border-radius: 4px;
        margin: 0;
        overflow-x: auto;
      }
    }
  }

  .tools-tab {
    .tools-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .empty-tools {
      padding: 40px 0;
    }

    .tools-list {
      display: flex;
      flex-direction: column;
      gap: 12px;

      .tool-card {
        background: var(--gray-0);
        border: 1px solid var(--gray-150);
        border-radius: 8px;
        padding: 12px 16px;
        transition: all 0.2s ease;

        &:hover {
          border-color: var(--gray-200);
        }

        &.disabled {
          opacity: 0.6;
        }

        .tool-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;

          .tool-info {
            display: flex;
            align-items: center;
            gap: 8px;

            .tool-name {
              font-weight: 600;
              font-size: 14px;
              color: var(--gray-900);
            }

            .info-icon {
              color: var(--gray-400);
              cursor: pointer;

              &:hover {
                color: var(--gray-600);
              }
            }
          }

          .tool-actions {
            display: flex;
            align-items: center;
            gap: 8px;
          }
        }

        .tool-description {
          font-size: 13px;
          color: var(--gray-600);
          line-height: 1.4;
          margin-bottom: 8px;
        }

        :deep(.ant-collapse) {
          background: transparent;
          border: none;

          .ant-collapse-header {
            padding: 8px 0;
            font-size: 13px;
            color: var(--gray-600);
          }

          .ant-collapse-content-box {
            padding: 0;
          }
        }

        .params-list {
          display: flex;
          flex-direction: column;
          gap: 8px;

          .param-item {
            background: var(--gray-50);
            padding: 8px 12px;
            border-radius: 4px;

            .param-header {
              display: flex;
              align-items: center;
              gap: 8px;
              margin-bottom: 4px;

              .param-name {
                font-weight: 500;
                font-size: 13px;
                color: var(--gray-900);
                font-family: 'Monaco', 'Consolas', monospace;
              }

              .param-required {
                font-size: 11px;
                color: var(--color-error-500);
                background: var(--color-error-50);
                padding: 1px 6px;
                border-radius: 3px;
              }

              .param-type {
                font-size: 11px;
                color: var(--gray-500);
                background: var(--gray-100);
                padding: 1px 6px;
                border-radius: 3px;
                font-family: 'Monaco', 'Consolas', monospace;
              }
            }

            .param-desc {
              font-size: 12px;
              color: var(--gray-600);
              line-height: 1.4;
            }
          }
        }
      }
    }
  }

  .empty-tab {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 200px;
  }
}
</style>
