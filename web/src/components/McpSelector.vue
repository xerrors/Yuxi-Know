<template>
  <a-modal
    v-model:open="mcpsModalOpen"
    :bodyStyle="{
      height: 'calc(100vh - 180px)',
      maxHeight: '800px',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }"
    :footer="null"
    :maskClosable="false"
    :width="1400"
    centered
    class="mcps-modal"
    title="MCP工具管理"
  >
    <div class="mcps-modal-content">
      <!-- 左侧：已选择的MCP工具列表 -->
      <div :class="{ 'full-width': rightPanelCollapsed }" class="mcps-left-panel">
        <div class="panel-header">
          <h3>已选择</h3>
          <div class="panel-header-right">
            <a-button
              v-if="selectedMcpTools.length > 0"
              class="clear-btn"
              size="small"
              type="text"
              @click="clearAllSelectedMcpTools"
            >
              <template #icon><ClearOutlined class="btn-icon" /></template>
              清空
            </a-button>
            <!-- 添加/收起按钮 -->
            <a-button
              class="toggle-right-panel-btn"
              size="small"
              type="link"
              @click="toggleRightPanel"
            >
              <template #icon>
                <PlusOutlined v-if="rightPanelCollapsed" class="btn-icon" />
                <CloseOutlined v-else class="btn-icon" />
              </template>
              {{ rightPanelCollapsed ? '添加' : '收起' }}
            </a-button>
          </div>
        </div>
        <div class="selected-tools-scroll-container">
          <div class="selected-tools-list">
            <div
              v-for="(tool, index) in selectedMcpTools"
              :key="`${tool.mcpId}-${tool.toolId}`"
              class="selected-tool-card"
            >
              <div class="tool-card-content">
                <div class="tool-card-header">
                  <div class="tool-title">
                    <span class="mcp-name">{{ tool.mcpName }}</span>
                    <span class="tool-separator">-</span>
                    <span class="tool-name">{{ tool.toolName }}</span>
                    <a-tooltip :title="`ID：${tool.toolId}`">
                      <InfoCircleOutlined class="tool-id-icon" />
                    </a-tooltip>
                  </div>
                  <div class="tool-actions">
                    <div class="tool-status">
                      <a-switch v-model:checked="tool.enabled" size="small" />
                      <span class="status-label">{{ tool.enabled ? '启用' : '禁用' }}</span>
                    </div>
                    <a-button danger size="small" type="text" @click="removeSelectedMcpTool(index)">
                      <template #icon><DeleteOutlined /></template>
                    </a-button>
                  </div>
                </div>
                <div class="tool-description-container">
                  <div :title="tool.toolDescription" class="tool-description">
                    {{ tool.toolDescription }}
                  </div>
                  <a-button
                    class="view-detail-btn"
                    size="small"
                    type="link"
                    @click="
                      showToolDescription({
                        id: tool.mcpId,
                        description: tool.toolDescription,
                        mcpName: tool.mcpName,
                        name: tool.toolName,
                        server: tool.mcpName,
                        parameters: tool.parameters || [],
                        argsSchema: tool.argsSchema || null
                      })
                    "
                  >
                    查看详情
                  </a-button>
                </div>
              </div>
            </div>

            <div v-if="selectedMcpTools.length === 0" class="empty-state">
              <div class="empty-text">暂无MCP工具</div>
              <div class="empty-hint">从右侧选择MCP工具添加到此处</div>
            </div>
          </div>
        </div>

        <div class="panel-footer">
          <div class="footer-left">
            <a-space size="small">
              <span class="stats-total">共 {{ selectedMcpTools.length }} 个</span>
              <span class="stats-enabled">{{ enabledToolsCount }} 个启用</span>
            </a-space>
          </div>
          <div class="footer-right">
            <a-space>
              <a-button @click="cancelMcpsSelection">取消</a-button>
              <a-button type="primary" @click="confirmMcpsSelection">确认</a-button>
            </a-space>
          </div>
        </div>
      </div>

      <!-- 右侧：MCP工具选择器 -->
      <div :class="{ collapsed: rightPanelCollapsed }" class="mcps-right-panel">
        <div class="panel-header">
          <h3>未选择</h3>
          <a-button class="refresh-btn" size="small" type="link" @click="refreshMcpTools">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
        </div>

        <div class="selector-search">
          <a-input
            v-model:value="mcpToolsSearchText"
            allow-clear
            class="search-input"
            placeholder="搜索MCP名称或工具名称..."
            size="small"
          >
            <template #prefix>
              <SearchOutlined class="search-icon" />
            </template>
          </a-input>
        </div>

        <div class="mcps-selector">
          <div class="mcps-tabs">
            <a-tabs v-model:activeKey="activeTab" class="mcp-tabs">
              <a-tab-pane key="by-mcp" tab="按MCP浏览">
                <div class="mcp-list-container">
                  <a-collapse
                    v-model:activeKey="expandedMcpIds"
                    class="mcp-collapse"
                    ghost
                    @change="handleCollapseChange"
                  >
                    <a-collapse-panel v-for="mcp in filteredMcps" :key="mcp.id">
                      <template #header>
                        <div class="custom-collapse-header">
                          <span class="mcp-header-name">{{ mcp.name }}</span>
                          <span :title="mcp.description" class="mcp-header-desp">
                            {{ mcp.description }}
                          </span>
                        </div>
                      </template>
                      <template #extra>
                        <span class="mcp-tools-count"> {{ getMcpToolsCount(mcp) }} 个工具 </span>
                      </template>

                      <div v-if="!mcp.tools">
                        <a-spin size="small" />
                        <span class="loading-text">加载工具中...</span>
                      </div>

                      <div v-else>
                        <!-- 为工具列表添加滚动容器 -->
                        <div class="tools-scroll-container">
                          <div class="tools-list">
                            <div
                              v-for="tool in getFilteredMcpTools(mcp)"
                              :key="tool.id"
                              :class="{
                                selected: isToolSelected(mcp.id, tool.id),
                                disabled: isToolDisabled(mcp.id, tool.id)
                              }"
                              class="tool-select-item"
                              @click="toggleToolSelection(mcp.id, tool)"
                            >
                              <div class="tool-select-content">
                                <div class="tool-select-header">
                                  <div class="tool-select-name">
                                    <span class="tool-name-text">{{ tool.name }}</span>
                                    <a-tooltip :title="`ID：${tool.id}`">
                                      <InfoCircleOutlined class="tool-id-icon-small" />
                                    </a-tooltip>
                                  </div>
                                  <div class="tool-select-actions">
                                    <a-button
                                      v-if="tool.description"
                                      class="view-detail-btn"
                                      size="small"
                                      type="link"
                                      @click.stop="
                                        showToolDescription({ ...tool, mcpName: mcp.name })
                                      "
                                    >
                                      详情
                                    </a-button>
                                  </div>
                                  <div class="tool-select-indicator">
                                    <CheckCircleOutlined
                                      v-if="isToolSelected(mcp.id, tool.id)"
                                      class="selected-icon"
                                    />
                                    <PlusCircleOutlined
                                      v-else-if="!isToolDisabled(mcp.id, tool.id)"
                                      class="available-icon"
                                    />
                                    <MinusCircleOutlined v-else class="disabled-icon" />
                                  </div>
                                </div>
                                <div :title="tool.description" class="tool-select-description">
                                  {{ tool.description || '暂无描述' }}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div v-if="getMcpToolsCount(mcp) === 0" class="no-tools">
                          <span class="no-tools-text">此MCP暂无可用工具</span>
                        </div>
                      </div>
                    </a-collapse-panel>
                  </a-collapse>
                </div>
              </a-tab-pane>

              <a-tab-pane key="all-tools" tab="全部工具">
                <div class="all-tools-container">
                  <div class="tools-grid">
                    <template v-for="mcp in filteredMcps" :key="mcp.id">
                      <div
                        v-for="tool in getFilteredMcpTools(mcp)"
                        :key="tool.id"
                        :class="{
                          selected: isToolSelected(mcp.id, tool.id),
                          disabled: isToolDisabled(mcp.id, tool.id)
                        }"
                        class="tool-select-item"
                        @click="toggleToolSelection(mcp.id, tool)"
                      >
                        <div class="tool-select-content">
                          <div class="tool-select-header">
                            <div class="tool-mcp-tag">{{ mcp.name }}</div>
                            <div class="tool-select-name">
                              <span class="tool-name-text">{{ tool.name }}</span>
                              <a-tooltip :title="`ID：${tool.id}`">
                                <InfoCircleOutlined class="tool-id-icon-small" />
                              </a-tooltip>
                            </div>
                            <div class="tool-select-actions">
                              <a-button
                                v-if="tool.description && tool.description.length > 60"
                                class="view-detail-btn"
                                size="small"
                                type="link"
                                @click.stop="showToolDescription({ ...tool, mcpName: mcp.name })"
                              >
                                详情
                              </a-button>
                            </div>
                            <div class="tool-select-indicator">
                              <CheckCircleOutlined
                                v-if="isToolSelected(mcp.id, tool.id)"
                                class="selected-icon"
                              />
                              <PlusCircleOutlined
                                v-else-if="!isToolDisabled(mcp.id, tool.id)"
                                class="available-icon"
                              />
                              <MinusCircleOutlined v-else class="disabled-icon" />
                            </div>
                          </div>
                          <div :title="tool.description" class="tool-select-description">
                            {{ tool.description || '暂无描述' }}
                          </div>
                        </div>
                      </div>
                    </template>
                  </div>
                </div>
              </a-tab-pane>
            </a-tabs>
          </div>

          <div v-if="filteredMcps.length === 0 && !mcpToolsSearchText" class="empty-search">
            <SearchOutlined class="empty-search-icon" />
            <div class="empty-search-text">未找到匹配的MCP或工具</div>
          </div>
        </div>

        <div class="panel-footer">
          <div class="footer-left">
            <a-tag v-if="selectedTempTools.length > 0" color="blue">
              已选 {{ selectedTempTools.length }} 个
            </a-tag>
            <span v-else class="selection-hint">选择工具添加到左侧</span>
          </div>
          <div class="footer-right">
            <a-space>
              <a-button :disabled="selectedTempTools.length === 0" @click="clearTempSelection">
                清空
              </a-button>
              <a-button
                :disabled="selectedTempTools.length === 0"
                type="primary"
                @click="addSelectedTools"
              >
                添加
              </a-button>
            </a-space>
          </div>
        </div>
      </div>
    </div>
  </a-modal>

  <a-modal
    v-model:open="toolDetailModalOpen"
    :footer="null"
    :maskClosable="true"
    :width="700"
    centered
    class="tool-detail-modal"
    title="工具详情"
  >
    <div v-if="selectedToolDetail" class="tool-detail-content">
      <div class="tool-detail-header">
        <div class="tool-detail-title">
          <span class="mcp-name">{{ selectedToolDetail.mcpName }}</span>
          <span class="tool-separator">/</span>
          <span class="tool-name">{{ selectedToolDetail.name }}</span>
        </div>
      </div>

      <div class="tool-detail-main">
        <!-- 描述部分 -->
        <div class="tool-detail-section">
          <div class="section-title">
            <span class="title-text">描述</span>
          </div>
          <div class="description-content">
            {{ selectedToolDetail.description || '暂无描述' }}
          </div>
        </div>

        <!-- 参数部分 -->
        <div class="tool-detail-section">
          <div class="section-title">
            <span class="title-text">参数</span>
            <span v-if="selectedToolDetail.parameters" class="title-count"
              >({{ selectedToolDetail.parameters.length }})</span
            >
          </div>

          <!-- Loading 状态 -->
          <div v-if="selectedToolDetail.loading" class="parameters-loading">
            <a-spin size="small" />
            <span class="loading-text">加载参数中...</span>
          </div>

          <!-- 有参数的情况 -->
          <div
            v-else-if="selectedToolDetail.parameters && selectedToolDetail.parameters.length > 0"
            class="parameters-content"
          >
            <div class="parameters-table">
              <div class="table-header">
                <div class="header-cell param-name-cell">参数名</div>
                <div class="header-cell param-type-cell">类型</div>
                <div class="header-cell param-desc-cell">描述</div>
              </div>
              <div class="table-body">
                <div
                  v-for="(param, index) in selectedToolDetail.parameters"
                  :key="index"
                  class="table-row"
                >
                  <div class="row-cell param-name-cell">
                    <span class="param-name">
                      {{ param.name }}
                      <span v-if="param.required" class="required-star">*</span>
                    </span>
                  </div>
                  <div class="row-cell param-type-cell">
                    <span class="type-tag">{{ param.type }}</span>
                  </div>
                  <div class="row-cell param-desc-cell">
                    {{ param.description || '-' }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 没有参数的情况 -->
          <div v-else class="no-parameters">此工具无需参数</div>
        </div>
      </div>

      <div class="tool-detail-footer">
        <a-button type="primary" @click="toolDetailModalOpen = false">关闭</a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  CheckCircleOutlined,
  ClearOutlined,
  CloseOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  MinusCircleOutlined,
  PlusCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useAgentStore } from '@/stores/agent'
import { storeToRefs } from 'pinia'

// Store 管理
const agentStore = useAgentStore()
const { availableMcps, selectedMcpToolsConfig, agentConfig } = storeToRefs(agentStore)

// MCP工具相关状态
const activeTab = ref('by-mcp')
const mcpToolsSearchText = ref('')
const selectedMcpTools = ref([])
const selectedTempTools = ref([])
const expandedMcpIds = ref([])
const toolDetailModalOpen = ref(false)
const selectedToolDetail = ref(null)
const mcpsModalOpen = ref(false)
const validMcps = ref([])

// 显示工具详情（直接从工具对象获取数据）
const showToolDescription = (tool) => {
  selectedToolDetail.value = {
    ...tool,
    parameters: tool.parameters || [], // 直接从工具对象获取
    loading: false // 无需 loading
  }
  toolDetailModalOpen.value = true
}

const props = defineProps({
  agentId: {
    type: String,
    required: true
  }
})

async function fetchValidMcps() {
  try {
    // 获取智能体配置中启用的 MCP 服务器 ID 列表
    const configuredMcpIds = agentConfig.value?.mcps || []
    
    // 过滤：只保留配置中启用的 MCP 服务器
    if (availableMcps.value && configuredMcpIds.length > 0) {
      const filteredMcps = {}
      Object.entries(availableMcps.value).forEach(([key, mcp]) => {
        // 只保留配置中启用的 MCP
        if (configuredMcpIds.includes(mcp.id)) {
          filteredMcps[key] = mcp
        }
      })
      validMcps.value = filteredMcps
    } else {
      // 如果没有配置任何 MCP，则显示空列表
      validMcps.value = {}
    }
  } catch (err) {
    console.error('Failed to fetch mcps:', err)
    throw err
  } finally {
  }
}

// 获取过滤后的MCP工具（根据搜索文本）
const getFilteredMcpTools = (mcp) => {
  if (!mcp || !mcp.id) return []

  // 直接从 mcp 的 tools 数组获取工具，不再需要加载
  const tools = mcp.tools || []

  // 如果没有搜索文本，返回所有工具
  if (!mcpToolsSearchText.value) {
    return tools
  }

  const searchLower = mcpToolsSearchText.value.toLowerCase()

  // 过滤工具：按工具名称、描述、ID搜索
  return tools.filter((tool) => {
    return (
      tool.name.toLowerCase().includes(searchLower) ||
      tool.description?.toLowerCase().includes(searchLower) ||
      tool.id.toLowerCase().includes(searchLower)
    )
  })
}

// 计算属性
const filteredMcps = computed(() => {
  const mcpsList = validMcps.value ? Object.values(validMcps.value) : []

  // 如果没有搜索文本，直接返回所有MCP
  if (!mcpToolsSearchText.value) {
    return mcpsList
  }

  const searchLower = mcpToolsSearchText.value.toLowerCase()

  // 返回过滤后的MCP列表
  return mcpsList.filter((mcp) => {
    // 1. 检查MCP本身是否匹配（名称或描述）
    const mcpNameMatch = mcp.name.toLowerCase().includes(searchLower)
    const mcpDescMatch = mcp.description?.toLowerCase().includes(searchLower)

    // 2. 检查MCP下的工具是否匹配（无论工具是否已加载）
    let toolMatch = false

    // 如果有工具，检查工具是否匹配
    if (mcp.tools) {
      toolMatch = mcp.tools.some((tool) => {
        return (
          tool.name.toLowerCase().includes(searchLower) ||
          tool.description?.toLowerCase().includes(searchLower) ||
          tool.id.toLowerCase().includes(searchLower)
        )
      })
    }

    // 3. 只要有任何一个匹配条件满足，就保留这个MCP
    return mcpNameMatch || mcpDescMatch || toolMatch
  })
})

const enabledToolsCount = computed(() => {
  return selectedMcpTools.value.filter((tool) => tool.enabled).length
})

// 获取MCP的工具（直接从mcp的tools数组获取，无需缓存）
const getMcpTools = (mcp) => {
  if (!mcp || !mcp.id) return []
  return mcp.tools || []
}

const getMcpToolsCount = (mcp) => {
  return getMcpTools(mcp).length
}

// 方法
const isToolSelected = (mcpId, toolId) => {
  return selectedTempTools.value.some((t) => t.mcpId === mcpId && t.toolId === toolId)
}

const isToolDisabled = (mcpId, toolId) => {
  return selectedMcpTools.value.some((t) => t.mcpId === mcpId && t.toolId === toolId)
}

const toggleToolSelection = (mcpId, tool) => {
  if (isToolDisabled(mcpId, tool.id)) {
    // 已添加到左侧的工具不能再次选择
    return
  }

  const existingIndex = selectedTempTools.value.findIndex(
    (t) => t.mcpId === mcpId && t.toolId === tool.id
  )

  if (existingIndex > -1) {
    // 取消选择
    selectedTempTools.value.splice(existingIndex, 1)
  } else {
    // 添加选择（包含参数信息）
    selectedTempTools.value.push({
      mcpId,
      mcpName: getMcpNameById(mcpId),
      toolId: tool.id,
      toolName: tool.name,
      toolDescription: tool.description || '暂无描述',
      parameters: tool.parameters || [], // 复制参数信息
      enabled: true
    })
  }
}

const addSelectedTools = () => {
  const newTools = [...selectedMcpTools.value]

  selectedTempTools.value.forEach((newTool) => {
    const exists = newTools.some(
      (existingTool) =>
        existingTool.mcpId === newTool.mcpId && existingTool.toolId === newTool.toolId
    )

    if (!exists) {
      newTools.push({ ...newTool })
    }
  })

  selectedMcpTools.value = newTools
  selectedTempTools.value = []
}

const clearTempSelection = () => {
  selectedTempTools.value = []
}

const removeSelectedMcpTool = (index) => {
  selectedMcpTools.value.splice(index, 1)
}

const clearAllSelectedMcpTools = () => {
  selectedMcpTools.value = []
}

const openMcpsModal = async () => {
  try {
    await fetchValidMcps()

    // 获取有效的MCP服务器ID集合
    const validMcpIds = new Set()
    if (validMcps.value) {
      Object.values(validMcps.value).forEach((mcp) => {
        if (mcp && mcp.id) {
          validMcpIds.add(mcp.id)
        }
      })
    }

    // 初始化已选择的MCP工具，同时过滤掉无效的MCP工具
    const initialSelectedTools = selectedMcpToolsConfig.value
      ? [...selectedMcpToolsConfig.value]
      : []

    // 过滤掉那些MCP不在有效列表中的工具
    const filteredSelectedTools = initialSelectedTools
      .filter((tool) => {
        return tool.mcpId && validMcpIds.has(tool.mcpId)
      })
      .map((tool) => ({ ...tool }))

    // 如果过滤后有变化，更新Vuex
    if (filteredSelectedTools.length !== initialSelectedTools.length) {
      // 更新Vuex中的配置
      agentStore.updateMcpToolsConfig([...filteredSelectedTools])

      // 可以给用户一个提示
      const removedCount = initialSelectedTools.length - filteredSelectedTools.length
      if (removedCount > 0) {
        message.warning(`已移除 ${removedCount} 个无效的MCP工具，因为所属的MCP服务器已不可用`)
      }
    }

    // 设置本地状态
    selectedMcpTools.value = filteredSelectedTools

    // 从validMcps中补充参数信息到已选择的工具
    filteredSelectedTools.forEach((tool, index) => {
      const mcp = validMcps.value[tool.mcpId]
      if (mcp && mcp.tools) {
        const mcpTool = mcp.tools.find((t) => t.id === tool.toolId)
        if (mcpTool) {
          // 从mcp补充 parameters
          selectedMcpTools.value[index] = {
            ...tool,
            parameters: mcpTool.parameters || []
          }
        }
      }
    })

    // 重置临时状态
    selectedTempTools.value = []
    mcpToolsSearchText.value = ''
    expandedMcpIds.value = []
    activeTab.value = 'by-mcp'

    mcpsModalOpen.value = true
  } catch (error) {
    console.error('打开MCP工具管理弹窗失败:', error)
    message.error('打开MCP工具管理弹窗失败')
  }
}

const confirmMcpsSelection = () => {
  agentStore.updateMcpToolsConfig([...selectedMcpTools.value])
  mcpsModalOpen.value = false
  resetMcpModal()
}

const cancelMcpsSelection = () => {
  mcpsModalOpen.value = false
  resetMcpModal()
}

const resetMcpModal = () => {
  selectedMcpTools.value = []
  selectedTempTools.value = []
  mcpToolsSearchText.value = ''
  expandedMcpIds.value = []
  activeTab.value = 'by-mcp'
}
const getMcpNameById = (mcpId) => {
  const mcpsList = validMcps.value ? Object.values(validMcps.value) : []
  const mcp = mcpsList.find((t) => t.id === mcpId)
  return mcp ? mcp.name : mcpId
}

const rightPanelCollapsed = ref(true)

const toggleRightPanel = () => {
  rightPanelCollapsed.value = !rightPanelCollapsed.value
}

// 刷新MCP工具（重新获取validMcps数据）
const refreshMcpTools = async () => {
  try {
    await fetchValidMcps()
    message.success('工具刷新成功')
  } catch (error) {
    console.error('刷新MCP工具失败:', error)
    message.error('刷新工具失败')
  }
}

// 使用 defineExpose 暴露方法给父组件
defineExpose({
  openMcpsModal,
  confirmMcpsSelection,
  cancelMcpsSelection,
  getSelectedTools: () => [...selectedMcpTools.value]
})
</script>
<style lang="less" scoped>
.mcps-modal {
  :deep(.ant-modal-content) {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  :deep(.ant-modal-body) {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .mcps-modal-content {
    display: flex;
    gap: 16px;
    height: 100%;
    flex: 1;
    overflow: hidden;

    // 左侧面板：已选择的工具
    .mcps-left-panel {
      width: 55%;
      display: flex;
      flex-direction: column;
      background: var(--gray-50);
      border-radius: 8px;
      border: 1px solid var(--gray-200);
      transition: width 0.3s ease;
      min-width: 250px;

      &.full-width {
        width: 100%;
      }

      .panel-header {
        padding: 12px 16px;
        border-bottom: 1px solid var(--gray-200);
        background: var(--gray-0);
        flex-shrink: 0;
        display: flex;
        justify-content: space-between;
        align-items: center;

        h3 {
          margin: 0;
          font-size: 14px;
          font-weight: 600;
          color: var(--gray-900);
        }

        .panel-header-right {
          display: flex;
          align-items: center;
          gap: 8px;

          .clear-btn {
            display: flex;
            align-items: center;
            gap: 4px;
            color: #ff4d4f;

            .btn-icon {
              font-size: 12px;
            }

            &:hover {
              color: #ff7875 !important;
              background-color: #fff2f0;
            }
          }

          .toggle-right-panel-btn {
            display: flex;
            align-items: center;
            gap: 4px;
            color: var(--main-color);

            .btn-icon {
              font-size: 12px;
            }

            &:hover {
              color: var(--main-color-dark);
            }
          }
        }

        .refresh-btn {
          display: flex;
          align-items: center;
          gap: 4px;
          color: var(--main-color);

          &:hover {
            color: var(--main-color-dark);
          }
        }
      }
      /* 新增：专门的滚动容器 */
      .selected-tools-scroll-container {
        flex: 1;
        overflow-y: auto;
        overflow-x: hidden;
      }

      .selected-tools-list {
        padding: 16px;

        .selected-tool-card {
          background: var(--gray-0);
          border: 1px solid var(--gray-200);
          border-radius: 8px;
          padding: 16px;
          margin-bottom: 12px;
          transition: all 0.2s ease;

          &:hover {
            border-color: var(--gray-300);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
          }

          .tool-card-content {
            .tool-card-header {
              display: flex;
              justify-content: space-between;
              align-items: flex-start;
              margin-bottom: 12px;

              .tool-title {
                flex: 1;
                display: flex;
                align-items: center;
                gap: 4px;
                flex-wrap: wrap;

                .mcp-name {
                  font-size: 14px;
                  font-weight: 600;
                  color: var(--main-color);
                  background: var(--main-50);
                  padding: 2px 6px;
                  border-radius: 4px;
                }

                .tool-separator {
                  color: var(--gray-400);
                  margin: 0 4px;
                }

                .tool-name {
                  font-size: 14px;
                  font-weight: 500;
                  color: var(--gray-900);
                }

                .tool-id-icon {
                  font-size: 12px;
                  color: var(--gray-400);
                  margin-left: 8px;
                  cursor: help;

                  &:hover {
                    color: var(--gray-600);
                  }
                }
              }

              .tool-actions {
                display: flex;
                align-items: center;
                gap: 16px;

                .tool-status {
                  display: flex;
                  align-items: center;
                  gap: 8px;

                  .status-label {
                    font-size: 12px;
                    color: var(--gray-600);
                    min-width: 32px;
                  }
                }
              }
            }

            .tool-description-container {
              margin-bottom: 8px;
              position: relative;

              .tool-description {
                font-size: 13px;
                color: var(--gray-600);
                line-height: 1.4;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
                text-overflow: ellipsis;
                margin-bottom: 4px;
              }

              .view-detail-btn {
                padding: 0;
                height: auto;
                font-size: 12px;
                color: var(--main-color);

                &:hover {
                  color: var(--main-color-dark);
                }
              }
            }

            .tool-meta {
              display: flex;
              flex-direction: column;
              gap: 4px;
              font-size: 11px;
              color: var(--gray-500);
              font-family: monospace;

              .tool-id,
              .tool-mcp-id {
                background: var(--gray-100);
                padding: 2px 6px;
                border-radius: 4px;
                display: inline-block;
                max-width: fit-content;
              }
            }
          }
        }

        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: var(--gray-400);
          text-align: center;

          .empty-icon {
            font-size: 64px;
            margin-bottom: 16px;
            opacity: 0.6;
          }

          .empty-text {
            font-size: 16px;
            font-weight: 500;
            color: var(--gray-500);
            margin-bottom: 8px;
          }

          .empty-hint {
            font-size: 14px;
            color: var(--gray-400);
          }
        }
      }

      .panel-footer {
        padding: 16px 20px;
        border-top: 1px solid var(--gray-200);
        background: var(--gray-0);
        flex-shrink: 0;
        display: flex;
        justify-content: space-between;
        align-items: center;

        .footer-left {
          display: flex;
          align-items: center;

          .stats-total {
            font-size: 14px;
            color: var(--gray-700);
            font-weight: 500;
          }

          .stats-enabled {
            font-size: 14px;
            color: var(--main-color);
            font-weight: 500;
            margin-left: 4px;
          }

          .selection-hint {
            font-size: 14px;
            color: var(--gray-400);
          }
        }

        .footer-right {
          display: flex;
          align-items: center;
        }
      }
    }
    // 右侧面板收起/展开按钮
    .panel-toggle-btn {
      position: absolute;
      right: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 24px;
      height: 60px;
      background: var(--gray-100);
      border: 1px solid var(--gray-200);
      border-left: none;
      border-radius: 0 8px 8px 0;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      z-index: 10;
      color: var(--gray-600);
      transition: all 0.2s ease;

      &:hover {
        background: var(--gray-200);
        color: var(--gray-800);
      }
    }
    // 右侧面板：工具选择器
    .mcps-right-panel {
      width: 45%;
      display: flex;
      flex-direction: column;
      background: var(--gray-50);
      border-radius: 8px;
      border: 1px solid var(--gray-200);
      transition: all 0.3s ease;
      transform: translateX(0);
      min-width: 0;

      // 收起状态
      &.collapsed {
        width: 0;
        opacity: 0;
        transform: translateX(100%);
        overflow: hidden;
        border: none;
      }
      .panel-header {
        padding: 12px 16px;
        border-bottom: 1px solid var(--gray-200);
        background: var(--gray-0);
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-shrink: 0;

        h3 {
          margin: 0;
          font-size: 14px;
          font-weight: 600;
          color: var(--gray-900);
        }

        .refresh-btn {
          display: flex;
          align-items: center;
          gap: 4px;
          color: var(--main-color);

          &:hover {
            color: var(--main-color-dark);
          }
        }
      }

      .selector-search {
        padding: 12px;
        border-bottom: 1px solid var(--gray-200);
        background: var(--gray-0);
        flex-shrink: 0;

        .search-input {
          border-radius: 6px;
          font-size: 14px;

          .search-icon {
            color: var(--gray-500);
            font-size: 14px;
          }
        }
      }

      .mcps-selector {
        flex: 1;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        background: var(--gray-0);

        .empty-search {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          text-align: center;
          width: 100%;
          z-index: 10;

          .empty-search-icon {
            font-size: 48px;
            color: var(--gray-400);
            margin-bottom: 16px;
          }

          .empty-search-text {
            font-size: 14px;
            color: var(--gray-500);
          }
        }

        .mcps-tabs {
          flex: 1;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          min-height: 0; /* 重要！ */

          :deep(.mcp-tabs) {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;

            .ant-tabs-nav {
              margin: 0;
              padding: 4px 20px !important;
              min-height: 36px !important;
              flex-shrink: 0;

              .ant-tabs-tab {
                padding: 4px 16px !important;
                margin: 0 8px 0 0 !important;
              }
            }

            .ant-tabs-content-holder {
              flex: 1;
              overflow: hidden;
            }

            .ant-tabs-content {
              height: 100%;
            }

            .ant-tabs-tabpane {
              height: 100%;
              overflow: hidden;
            }
          }

          .mcp-list-container {
            height: 100%;
            overflow-y: auto;
            padding: 0 20px;
            background: var(--gray-50);

            .mcp-collapse {
              :deep(.ant-collapse-item) {
                border-bottom: 1px solid var(--gray-200);
                // 自定义折叠面板标题样式
                .custom-collapse-header {
                  display: flex;
                  align-items: center;
                  gap: 12px;
                  width: 100%;
                  padding-right: 8px;

                  .mcp-header-name {
                    font-weight: 500;
                    flex-shrink: 0;
                    color: var(--main-color);
                    background: var(--main-50);
                    padding: 2px 6px;
                    border-radius: 4px;
                  }

                  .mcp-header-desp {
                    font-size: 13px;
                    color: var(--gray-600);
                    flex: 1;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                    font-weight: normal;

                    &:hover {
                      color: var(--gray-700);
                    }
                  }
                }
                .ant-collapse-header {
                  padding: 12px 0;
                  font-weight: 500;
                  font-size: 15px;
                  display: flex;
                  align-items: center;
                  background-color: var(--gray-0);

                  .mcp-tools-count {
                    font-size: 12px;
                    color: var(--gray-500);
                    margin-left: auto;
                    margin-right: 8px;
                    font-weight: normal;
                  }

                  .mcp-tools-desp {
                    font-size: 14px;
                    color: var(--gray-500);
                    margin-right: 8px;
                    font-weight: normal;
                  }
                }

                .ant-collapse-content-box {
                  padding: 0;
                }
              }
            }
          }

          .all-tools-container {
            height: 100%;
            overflow-y: auto;
            padding: 0 20px;
            background: var(--gray-50);

            .tools-grid {
              display: grid;
              grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
              gap: 12px;
              padding: 8px 0;
            }
          }

          .mcp-info {
            padding: 12px 16px;
            background: var(--gray-50);
            border-radius: 6px;
            margin-bottom: 16px;

            .mcp-description {
              font-size: 13px;
              color: var(--gray-700);
              line-height: 1.4;
              margin-bottom: 4px;
            }
          }

          .loading-tools {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: var(--gray-500);

            .loading-text {
              margin-left: 8px;
              font-size: 13px;
            }
          }

          .loading-all-tools {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--gray-500);

            .loading-text {
              margin-top: 12px;
              font-size: 14px;
            }
          }

          .tools-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 12px;
            padding: 8px 0;
          }

          .tool-select-item {
            padding: 12px;
            border: 1px solid var(--gray-200);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            background: var(--gray-0);

            &:hover {
              border-color: var(--main-color);
              background: var(--gray-25);

              .tool-select-content .tool-select-indicator .available-icon {
                color: var(--main-color);
              }
            }

            &.selected {
              border-color: var(--main-color);
              background: var(--main-10);

              .tool-select-content {
                .tool-select-name {
                  color: var(--main-color);
                  font-weight: 500;
                }

                .selected-icon {
                  color: var(--main-color);
                }
              }
            }

            &.disabled {
              opacity: 0.6;
              cursor: not-allowed;
              background: var(--gray-100);

              &:hover {
                border-color: var(--gray-300);
                background: var(--gray-100);
              }

              .tool-select-content {
                .tool-select-name {
                  color: var(--gray-500);
                }

                .tool-mcp-tag {
                  background: var(--gray-200);
                  color: var(--gray-500);
                }

                .disabled-icon {
                  color: var(--gray-400);
                }
              }
            }

            .tool-select-content {
              .tool-select-header {
                display: flex;
                align-items: center;
                margin-bottom: 8px;
                gap: 8px;

                .tool-mcp-tag {
                  font-size: 11px;
                  background: var(--gray-100);
                  color: var(--gray-600);
                  padding: 1px 6px;
                  border-radius: 4px;
                  font-weight: 500;
                  flex-shrink: 0;
                }

                .tool-name-text {
                  flex: 1;
                  font-size: 14px;
                  font-weight: 500;
                  color: var(--gray-900);
                  line-height: 1.3;
                  min-width: 0; // 允许文本截断
                  overflow: hidden;
                  text-overflow: ellipsis;
                  white-space: nowrap;
                }

                .tool-id-icon-small {
                  font-size: 12px;
                  color: var(--gray-400);
                  margin-left: 6px;
                  flex-shrink: 0;
                  cursor: help;

                  &:hover {
                    color: var(--gray-600);
                  }
                }

                .tool-select-indicator {
                  font-size: 16px;
                  flex-shrink: 0;

                  .selected-icon {
                    color: var(--main-color);
                  }

                  .available-icon {
                    color: var(--gray-400);
                  }

                  .disabled-icon {
                    color: var(--gray-400);
                  }
                }
              }

              .tool-select-description {
                font-size: 12px;
                color: var(--gray-600);
                line-height: 1.4;
                margin-bottom: 8px;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
                text-overflow: ellipsis;
                min-height: 36px; // 保证两行高度
              }

              .tool-select-actions {
                display: flex;
                justify-content: space-between;
                align-items: center;

                .view-detail-btn {
                  padding: 0;
                  height: auto;
                  font-size: 11px;
                  color: var(--main-color);

                  &:hover {
                    color: var(--main-color-dark);
                  }
                }
              }
            }
          }

          .no-tools {
            padding: 24px 16px;
            text-align: center;
            background: var(--gray-50);
            border-radius: 6px;

            .no-tools-text {
              font-size: 13px;
              color: var(--gray-500);
            }
          }
        }
      }

      .panel-footer {
        padding: 16px 20px;
        border-top: 1px solid var(--gray-200);
        background: var(--gray-0);
        flex-shrink: 0;
        display: flex;
        justify-content: space-between;
        align-items: center;

        .footer-left {
          display: flex;
          align-items: center;
        }

        .footer-right {
          display: flex;
          align-items: center;
        }
      }
    }
  }
}

// 工具详情弹窗样式
.tool-detail-modal {
  .ant-modal-content {
    border-radius: 12px;
    overflow: hidden;
  }

  .ant-modal-header {
    border-bottom: 1px solid var(--gray-200);
    border-radius: 12px 12px 0 0;
    padding: 20px 24px 16px;

    .ant-modal-title {
      font-size: 18px;
      font-weight: 600;
      color: var(--gray-900);
    }
  }

  .ant-modal-body {
    padding: 0;
  }

  .tool-detail-content {
    display: flex;
    flex-direction: column;
    height: 100%;

    .tool-detail-header {
      padding: 0 12px;
      margin-bottom: 20px;

      .tool-detail-title {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 16px 0;
        border-bottom: 1px solid var(--gray-200);

        .mcp-name {
          font-size: 16px;
          font-weight: 500;
          color: var(--main-color);
        }

        .tool-separator {
          color: var(--gray-400);
        }

        .tool-name {
          font-size: 16px;
          font-weight: 600;
          color: var(--gray-900);
        }
      }
    }

    .tool-detail-main {
      padding: 0 12px;
      flex: 1;
      overflow-y: visible;

      .tool-detail-section {
        margin-bottom: 24px;

        .parameters-loading {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 40px;
          background: var(--gray-0);
          border-radius: 8px;
          border: 1px solid var(--gray-200);
          min-height: 100px;

          .loading-text {
            margin-left: 8px;
            color: var(--gray-600);
            font-size: 14px;
          }

          .ant-spin {
            color: var(--main-color);
          }
        }

        .section-title {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
          font-weight: 600;
          color: var(--gray-900);

          .title-text {
            font-size: 15px;
          }

          .title-count {
            font-size: 13px;
            color: var(--gray-500);
            font-weight: normal;
          }
        }

        .description-content {
          font-size: 14px;
          line-height: 1.7;
          color: var(--gray-900);
          padding: 16px;
          background: var(--gray-0);
          border: 1px solid var(--gray-200);
          border-radius: 8px;
          max-height: 260px;
          overflow-y: auto;
          white-space: pre-wrap;
          word-break: break-word;
        }

        .no-parameters {
          padding: 16px;
          background: var(--gray-100);
          border-radius: 8px;
          border: 1px solid var(--gray-200);
          text-align: center;
          color: var(--gray-600);
          font-size: 14px;
        }

        .parameters-content {
          max-height: 260px;
          overflow-y: auto;
          border: 1px solid var(--gray-200);
          border-radius: 8px;
          background: var(--gray-0);

          .parameters-table {
            width: 100%;

            .table-header {
              display: flex;
              background: var(--gray-100);
              border-bottom: 1px solid var(--gray-200);
              position: sticky;
              top: 0;
              z-index: 1;

              .header-cell {
                padding: 12px 16px;
                font-size: 13px;
                font-weight: 600;
                color: var(--gray-700);
                border-right: 1px solid var(--gray-200);

                &:last-child {
                  border-right: none;
                }
              }

              .param-name-cell {
                width: 28%;
                min-width: 120px;
              }

              .param-type-cell {
                width: 15%;
                min-width: 80px;
              }

              .param-desc-cell {
                flex: 1;
              }
            }

            .table-body {
              .table-row {
                display: flex;
                border-bottom: 1px solid var(--gray-200);

                &:last-child {
                  border-bottom: none;
                }

                &:hover {
                  background: var(--gray-100);
                }

                .row-cell {
                  padding: 12px 16px;
                  font-size: 13px;
                  color: var(--gray-900);
                  border-right: 1px solid var(--gray-200);

                  &:last-child {
                    border-right: none;
                  }
                }

                .param-name-cell {
                  width: 28%;
                  min-width: 120px;

                  .param-name {
                    font-weight: 500;
                    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;

                    .required-star {
                      color: #ff4d4f;
                      margin-left: 2px;
                    }
                  }
                }

                .param-type-cell {
                  width: 15%;
                  min-width: 80px;

                  .type-tag {
                    display: inline-block;
                    padding: 2px 8px;
                    border-radius: 4px;
                    background: var(--main-50);
                    color: var(--main-color);
                    font-size: 12px;
                    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
                  }
                }

                .param-desc-cell {
                  flex: 1;
                  line-height: 1.5;
                  color: var(--gray-700);
                }
              }
            }
          }
        }
      }
    }

    .tool-detail-footer {
      padding: 16px 24px;
      border-top: 1px solid var(--gray-200);
      text-align: right;
      margin-top: 8px;

      .ant-btn {
        min-width: 80px;
        height: 32px;
        padding: 0 16px;
        border-radius: 6px;
      }
    }
  }
}
</style>