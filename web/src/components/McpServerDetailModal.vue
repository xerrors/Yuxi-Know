<template>
  <a-modal
    v-model:open="modalVisible"
    :footer="null"
    :title="server?.name || 'MCP 服务器详情'"
    class="mcp-detail-modal"
    width="800px"
    @cancel="handleClose"
  >
    <div v-if="server" class="detail-container">
      <!-- 头部状态 -->
      <div class="detail-header">
        <div class="server-info">
          <span class="server-icon">{{ server.icon || '🔌' }}</span>
          <div class="server-meta">
            <h3 class="server-name">{{ server.name }}</h3>
            <span :class="{ enabled: server.enabled }" class="server-status">
              {{ server.enabled ? '已启用' : '已禁用' }}
            </span>
          </div>
        </div>
        <div class="header-actions">
          <a-button :loading="testLoading" @click="handleTestConnection">
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
                  v-if="server.headers && Object.keys(server.headers).length > 0"
                  class="info-item"
                >
                  <label>请求头</label>
                  <pre class="headers-pre">{{ JSON.stringify(server.headers, null, 2) }}</pre>
                </div>
                <div v-if="server.timeout" class="info-item">
                  <label>HTTP 超时</label>
                  <span>{{ server.timeout }} 秒</span>
                </div>
                <div v-if="server.sse_read_timeout" class="info-item">
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
                <div v-if="server.args && server.args.length > 0" class="info-item">
                  <label>参数</label>
                  <span>
                    <a-tag v-for="(arg, index) in server.args" :key="index" size="small">
                      {{ arg }}
                    </a-tag>
                  </span>
                </div>
              </template>

              <div v-if="server.description" class="info-item">
                <label>描述</label>
                <span>{{ server.description }}</span>
              </div>
              <div v-if="server.tags && server.tags.length > 0" class="info-item">
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
                allowClear
                placeholder="搜索工具..."
                style="width: 240px"
              />
              <a-button :loading="toolsLoading" @click="handleRefreshTools">
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
                  :class="{ disabled: !tool.enabled }"
                  class="tool-card"
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
                        :disabled="processingTools.has(tool.name)"
                        :loading="toggleToolLoading === tool.name"
                        size="small"
                        @change="handleToggleTool(tool)"
                      />
                      <a-tooltip title="复制工具名称">
                        <a-button size="small" type="text" @click="copyToolName(tool.name)">
                          <CopyOutlined />
                        </a-button>
                      </a-tooltip>
                    </div>
                  </div>
                  <a-tooltip
                    v-if="tool.description"
                    :title="tool.description.length > 100 ? tool.description : ''"
                    overlayClassName="tool-description-tooltip"
                    placement="topLeft"
                  >
                    <div class="tool-description">
                      {{ tool.description }}
                    </div>
                  </a-tooltip>
                  <a-collapse
                    v-if="tool.parameters && Object.keys(tool.parameters).length > 0"
                    ghost
                  >
                    <a-collapse-panel key="params" header="参数">
                      <div class="params-list">
                        <div
                          v-for="(param, paramName) in tool.parameters"
                          :key="paramName"
                          class="param-row-new"
                        >
                          <div class="param-left">
                            <span class="param-name-text">{{ paramName }}</span>
                            <span
                              v-if="tool.required?.includes(paramName)"
                              class="param-required-mark"
                              >*</span
                            >
                          </div>
                          <div class="param-right">
                            <div class="param-type-line">
                              <span
                                :style="{ background: getTypeColor(param.type) }"
                                class="type-dot"
                              ></span>
                              <span class="param-type-text">{{ param.type || 'any' }}</span>
                            </div>
                            <a-tooltip
                              v-if="param.description"
                              :title="param.description.length > 80 ? param.description : ''"
                              overlayClassName="tool-description-tooltip"
                              placement="topLeft"
                            >
                              <div class="param-desc-text">
                                {{ param.description }}
                              </div>
                            </a-tooltip>
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
import { computed, reactive, ref, watch } from 'vue'
import { notification } from 'ant-design-vue'
import {
  ApiOutlined,
  CopyOutlined,
  InfoCircleOutlined,
  ReloadOutlined
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

const emit = defineEmits(['update:visible', 'update', 'toolToggled'])

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

// 监听服务器变化，只有当真正切换服务器（Name 变化）时才加载工具列表
watch(
  () => props.server?.name,
  (newName, oldName) => {
    if (newName && newName !== oldName) {
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
// 使用 Reactive Set 存储处理状态，控制 UI 禁用
const processingTools = reactive(new Set())
// 使用原生 Set 作为逻辑同步锁（完全绕过 Vue 响应式系统，确保绝对同步拦截）
const logicLock = new Set()

// 切换工具启用状态
const handleToggleTool = async (tool) => {
  if (!props.server) return

  // 1. 逻辑同步锁拦截（最优先、最快、无开销）
  if (logicLock.has(tool.name)) {
    return
  }

  try {
    // 2. 上双重锁
    logicLock.add(tool.name) // 立即生效的逻辑锁
    processingTools.add(tool.name) // 触发 UI 更新的响应式锁
    toggleToolLoading.value = tool.name

    const result = await mcpApi.toggleMcpServerTool(props.server.name, tool.name)
    if (result.success) {
      notification.success({ message: result.message })
      // 更新本地状态
      const targetTool = tools.value.find((t) => t.name === tool.name)
      if (targetTool) {
        targetTool.enabled = result.enabled
      }
      // 触发父组件更新
      emit('toolToggled', {
        serverName: props.server.name,
        toolName: tool.name,
        enabled: result.enabled
      })
    } else {
      notification.error({ message: result.message || '操作失败' })
    }
  } catch (err) {
    console.error('切换工具状态失败:', err)
    notification.error({ message: err.message || '操作失败' })
  } finally {
    // 3. 强制冷却解锁（至少等待 300ms 确保 UI 稳定和防止极速连击）
    setTimeout(() => {
      logicLock.delete(tool.name)
      processingTools.delete(tool.name)
      toggleToolLoading.value = null
    }, 300)
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

// 根据参数类型返回对应的颜色
const getTypeColor = (type) => {
  if (!type) return '#8c8c8c' // 默认灰色

  const typeMap = {
    string: '#52c41a', // 绿色
    number: '#1890ff', // 蓝色
    integer: '#1890ff', // 蓝色
    boolean: '#fa8c16', // 橙色
    object: '#722ed1', // 紫色
    array: '#f5222d', // 红色
    null: '#8c8c8c', // 灰色
    any: '#8c8c8c' // 灰色
  }

  return typeMap[type.toLowerCase()] || '#1890ff' // 默认蓝色
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
          line-height: 1.5;
          margin-bottom: 8px;
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
          text-overflow: ellipsis;
          cursor: help;

          &:hover {
            color: var(--gray-700);
          }
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

          .param-row-new {
            display: grid;
            grid-template-columns: 180px 1fr;
            gap: 24px;
            padding: 12px 16px;
            background: var(--gray-50);
            border: 1px solid var(--gray-150);
            border-radius: 6px;

            .param-left {
              display: flex;
              align-items: flex-start;
              gap: 4px;
              padding-right: 24px;
              border-right: 1px solid var(--gray-200);

              .param-name-text {
                font-weight: 500;
                font-size: 13px;
                color: var(--gray-900);
                font-family: 'Monaco', 'Consolas', monospace;
              }

              .param-required-mark {
                color: var(--color-error-500);
                font-size: 14px;
                font-weight: 600;
              }
            }

            .param-right {
              display: flex;
              flex-direction: column;
              gap: 6px;

              .param-type-line {
                display: flex;
                align-items: center;
                gap: 6px;

                .type-dot {
                  width: 8px;
                  height: 8px;
                  border-radius: 50%;
                  flex-shrink: 0;
                }

                .param-type-text {
                  font-size: 12px;
                  color: var(--color-primary);
                  font-family: 'Monaco', 'Consolas', monospace;
                  font-weight: 500;
                  padding: 2px 8px;
                  background: var(--color-primary-50);
                  border: 1px solid var(--color-primary-200);
                  border-radius: 4px;
                }
              }

              .param-desc-text {
                font-size: 13px;
                color: var(--gray-600);
                line-height: 1.5;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
                text-overflow: ellipsis;
                cursor: help;

                &:hover {
                  color: var(--gray-700);
                }
              }
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

<style lang="less">
// 工具描述 Tooltip 样式（不使用 scoped，因为 Tooltip 渲染在 body 下）
.tool-description-tooltip {
  max-width: 600px !important;

  .ant-tooltip-inner {
    max-width: 600px;
    max-height: 400px;
    overflow-y: auto;
    text-align: left;
    line-height: 1.6;
  }
}
</style>
