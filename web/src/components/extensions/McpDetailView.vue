<template>
  <div class="mcp-detail extension-detail-page">
    <div v-if="loading" class="loading-bar-wrapper">
      <div class="loading-bar"></div>
    </div>
    <div class="detail-top-bar">
      <button class="detail-back-btn" @click="goBack">
        <ArrowLeft :size="16" />
        <span>返回</span>
      </button>
      <div class="detail-title-area">
        <span class="detail-icon">{{ server?.icon || '🔌' }}</span>
        <div class="detail-title-text">
          <h2>{{ server?.name || name }}</h2>
          <span class="detail-subtitle">{{ server?.transport || '' }}</span>
        </div>
      </div>
      <div class="detail-actions">
        <a-space :size="8">
          <button
            type="button"
            @click="handleTestServer"
            :disabled="testLoading"
            class="lucide-icon-btn extension-panel-action extension-panel-action-secondary"
          >
            <Zap :size="14" v-if="!testLoading" />
            <span>测试</span>
          </button>
          <button
            type="button"
            @click="showEditModal"
            class="lucide-icon-btn extension-panel-action extension-panel-action-secondary"
          >
            <Pencil :size="14" />
            <span>编辑</span>
          </button>
          <button
            type="button"
            @click="handleDangerAction"
            :class="[
              'lucide-icon-btn',
              'extension-panel-action',
              server?.enabled === false
                ? 'extension-panel-action-primary'
                : 'extension-panel-action-danger'
            ]"
          >
            <Plus v-if="server?.enabled === false" :size="14" />
            <Trash2 v-else :size="14" />
            <span>{{ actionLabel }}</span>
          </button>
        </a-space>
      </div>
    </div>

    <div class="detail-content-wrapper">
      <a-spin :spinning="loading">
        <div v-if="server" class="detail-content-inner">
          <a-tabs v-model:activeKey="detailTab" class="detail-tabs">
            <a-tab-pane key="general">
              <template #tab>
                <span class="tab-title"><Settings2 :size="14" />信息</span>
              </template>
              <div class="tab-content">
                <div class="info-grid">
                  <div class="info-item" v-if="server.description">
                    <label>描述</label>
                    <span>{{ server.description }}</span>
                  </div>
                  <div class="info-item">
                    <label>传输类型</label>
                    <span>
                      <a-tag :color="getTransportColor(server.transport)">{{
                        server.transport
                      }}</a-tag>
                    </span>
                  </div>
                  <div
                    class="info-item"
                    v-if="Array.isArray(server.tags) && server.tags.length > 0"
                  >
                    <label>标签</label>
                    <span>
                      <a-tag v-for="tag in server.tags" :key="tag">{{ tag }}</a-tag>
                    </span>
                  </div>
                  <template
                    v-if="server.transport === 'streamable_http' || server.transport === 'sse'"
                  >
                    <div class="info-item" v-if="server.url">
                      <label>MCP URL</label>
                      <span class="code-inline text-break-all">{{ server.url }}</span>
                    </div>
                    <div
                      class="info-item"
                      v-if="server.headers && Object.keys(server.headers).length > 0"
                    >
                      <label>请求头</label>
                      <pre class="code-pre">{{ JSON.stringify(server.headers, null, 2) }}</pre>
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
                  <template v-if="server.transport === 'stdio'">
                    <div class="info-item" v-if="server.command">
                      <label>命令</label>
                      <span class="code-inline">{{ server.command }}</span>
                    </div>
                    <div class="info-item" v-if="server.args && server.args.length > 0">
                      <label>参数</label>
                      <span>
                        <a-tag v-for="(arg, index) in server.args" :key="index" size="small">{{
                          arg
                        }}</a-tag>
                      </span>
                    </div>
                    <div class="info-item" v-if="server.env && Object.keys(server.env).length > 0">
                      <label>环境变量</label>
                      <pre class="code-pre">{{ JSON.stringify(server.env, null, 2) }}</pre>
                    </div>
                  </template>
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

            <a-tab-pane key="tools">
              <template #tab>
                <span class="tab-title"><Wrench :size="14" />工具 ({{ tools.length }})</span>
              </template>
              <div class="tab-content tools-tab">
                <div class="tools-toolbar">
                  <a-input-search
                    v-model:value="toolSearchText"
                    placeholder="搜索工具..."
                    style="width: 200px"
                    allowClear
                  />
                  <a-button @click="fetchTools" :loading="toolsLoading" class="lucide-icon-btn">
                    <RotateCw :size="14" />
                    <span>刷新</span>
                  </a-button>
                </div>
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
                            <Info :size="14" class="info-icon" />
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
                            <a-button
                              type="text"
                              size="small"
                              @click="copyToolName(tool.name)"
                              class="lucide-icon-btn"
                            >
                              <Copy :size="14" />
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
                                <span
                                  class="param-required"
                                  v-if="tool.required?.includes(paramName)"
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
          </a-tabs>
        </div>
        <div v-else-if="!loading" class="detail-empty">
          <a-empty description="未找到 MCP 服务器" />
        </div>
      </a-spin>
    </div>

    <McpFormModal
      v-model:open="formModalVisible"
      :edit-mode="editMode"
      :edit-data="editData"
      @submitted="handleFormSubmitted"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeft,
  Zap,
  Pencil,
  Trash2,
  Plus,
  RotateCw,
  Info,
  Copy,
  Settings2,
  Wrench
} from 'lucide-vue-next'
import { mcpApi } from '@/apis/mcp_api'
import { formatFullDateTime } from '@/utils/time'
import McpFormModal from './McpFormModal.vue'

const route = useRoute()
const router = useRouter()
const name = computed(() => decodeURIComponent(route.params.name))

const loading = ref(false)
const server = ref(null)
const detailTab = ref('general')
const testLoading = ref(null)

const tools = ref([])
const toolsLoading = ref(false)
const toolsError = ref(null)
const toolSearchText = ref('')
const toggleToolLoading = ref(null)

const formModalVisible = ref(false)
const editMode = ref(false)
const editData = ref(null)

const actionLabel = computed(() => {
  if (server.value?.enabled === false) return '添加'
  return server.value?.created_by === 'system' ? '移除' : '删除'
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

const goBack = () => {
  router.push({ path: '/extensions', query: { tab: 'mcp' } })
}

const formatTime = (timeStr) => formatFullDateTime(timeStr)

const getTransportColor = (transport) => {
  const colors = { sse: 'orange', stdio: 'green', streamable_http: 'blue' }
  return colors[transport] || 'blue'
}

const fetchServer = async () => {
  try {
    loading.value = true
    const result = await mcpApi.getMcpServer(name.value)
    if (result.success) {
      server.value = result.data
    } else {
      message.error(result.message || '获取 MCP 详情失败')
    }
  } catch (err) {
    message.error(err.message || '获取 MCP 详情失败')
  } finally {
    loading.value = false
  }
}

const fetchTools = async () => {
  if (!server.value) return
  try {
    toolsLoading.value = true
    toolsError.value = null
    const result = await mcpApi.getMcpServerTools(server.value.name)
    if (result.success) {
      tools.value = result.data || []
    } else {
      toolsError.value = result.message || '获取工具列表失败'
      tools.value = []
    }
  } catch (err) {
    toolsError.value = err.message || '获取工具列表失败'
    tools.value = []
  } finally {
    toolsLoading.value = false
  }
}

const handleToggleTool = async (tool) => {
  if (!server.value) return
  try {
    toggleToolLoading.value = tool.name
    const result = await mcpApi.toggleMcpServerTool(server.value.name, tool.name)
    if (result.success) {
      message.success(result.message)
      const targetTool = tools.value.find((t) => t.name === tool.name)
      if (targetTool) targetTool.enabled = result.enabled
    } else {
      message.error(result.message || '操作失败')
    }
  } catch (err) {
    message.error(err.message || '操作失败')
  } finally {
    toggleToolLoading.value = null
  }
}

const copyToolName = async (toolName) => {
  try {
    await navigator.clipboard.writeText(toolName)
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败')
  }
}

const handleTestServer = async () => {
  if (!server.value) return
  try {
    testLoading.value = server.value.name
    const result = await mcpApi.testMcpServer(server.value.name)
    if (result.success) {
      message.success(result.message)
    } else {
      message.warning(result.message || '连接失败')
    }
  } catch (err) {
    message.error(err.message || '测试失败')
  } finally {
    testLoading.value = null
  }
}

const showEditModal = () => {
  editMode.value = true
  editData.value = { ...server.value }
  formModalVisible.value = true
}

const handleDangerAction = async () => {
  if (!server.value) return
  if (server.value.enabled === false) {
    await handleSetServerEnabled(server.value, true)
    return
  }
  if (server.value.created_by === 'system') {
    await handleSetServerEnabled(server.value, false)
    return
  }
  confirmDeleteServer(server.value)
}

const handleSetServerEnabled = async (srv, enabled) => {
  try {
    const result = await mcpApi.updateMcpServerStatus(srv.name, enabled)
    if (result.success) {
      message.success(result.message || `MCP 已${enabled ? '添加' : '移除'}`)
      await fetchServer()
    } else {
      message.error(result.message || '操作失败')
    }
  } catch (err) {
    message.error(err.message || '操作失败')
  }
}

const confirmDeleteServer = (srv) => {
  Modal.confirm({
    title: '确认删除 MCP',
    content: `确定要删除 MCP "${srv.name}" 吗？此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const result = await mcpApi.deleteMcpServer(srv.name)
        if (result.success) {
          message.success('MCP 删除成功')
          router.push({ path: '/extensions', query: { tab: 'mcp' } })
        } else {
          message.error(result.message || '删除失败')
        }
      } catch (err) {
        message.error(err.message || '删除失败')
      }
    }
  })
}

const handleFormSubmitted = async () => {
  formModalVisible.value = false
  await fetchServer()
}

watch(detailTab, (tab) => {
  if (tab === 'tools' && server.value) {
    fetchTools()
  }
})

onMounted(() => {
  fetchServer()
})
</script>

<style lang="less" scoped>
@import '@/assets/css/extensions.less';
@import '@/assets/css/extension-detail.less';


/* 工具列表样式 */
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
              font-family: @mono-font;
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
              font-family: @mono-font;
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


.mcp-detail {
  .detail-content-wrapper {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    background-color: var(--gray-10);
  }

  .detail-content-inner {
    max-width: 900px;
    margin: 0 auto;
    padding: 16px var(--page-padding);
  }
}
</style>
