<template>
  <ActionDropdown
    upward
    v-if="selectedAgentId"
    v-model:open="agentDropdownOpen"
    v-model:search="agentSearchKeyword"
    search-placeholder="搜索智能体"
    :disabled="isCreatingThread"
  >
    <template #trigger>
      <ActionTrigger
        data-session-agent-picker
        :label="currentAgentLabel"
        :open="agentDropdownOpen"
        :disabled="isCreatingThread"
        :collapse-label="currentAgentOption?.isDefault"
      >
        <template #icon>
          <FallbackAvatar
            v-if="currentAgentOption"
            :src="currentAgentOption.icon"
            :name="currentAgentOption.label"
            :seed="currentAgentOption.value || currentAgentOption.label"
            kind="agent"
            :size="20"
            shape="rounded"
            alt=""
          />
        </template>
      </ActionTrigger>
    </template>
    <div v-if="!filteredAgentOptions.length" class="agent-switch-empty" role="status">
      暂无匹配智能体
    </div>
    <button
      v-for="agent in filteredAgentOptions"
      :key="agent.value"
      type="button"
      class="config-dropdown-item"
      :class="{
        selected: agent.value === selectedAgentId,
        disabled: hasActiveThread && agent.value !== selectedAgentId
      }"
      @click="handleAgentSwitch(agent.value, hasActiveThread, isCreatingThread)"
    >
      <FallbackAvatar
        class="config-dropdown-item-icon-image"
        :src="agent.icon"
        :name="agent.label"
        :seed="agent.value || agent.label"
        kind="agent"
        :size="24"
        shape="rounded"
        :alt="`${agent.label}图标`"
      />
      <span class="config-dropdown-item-label" :title="agent.label">{{ agent.label }}</span>
      <span v-if="agent.isBuiltin" class="config-dropdown-item-badge">内置</span>
      <Check v-if="agent.value === selectedAgentId" :size="14" class="config-dropdown-item-check" />
    </button>
    <template #footer>
      <div v-if="hasActiveThread" class="config-dropdown-hint">
        当前对话已绑定智能体，新对话可切换。
      </div>

      <div class="config-dropdown-divider"></div>

      <div class="config-dropdown-actions">
        <button type="button" class="config-dropdown-item action-item" @click="openAgentManagement">
          <Settings2 :size="15" class="config-dropdown-item-icon" />
          <span class="config-dropdown-item-label">编辑智能体</span>
        </button>
        <button type="button" class="config-dropdown-item action-item" @click="openCreateAgent">
          <Plus :size="15" class="config-dropdown-item-icon" />
          <span class="config-dropdown-item-label">新建智能体</span>
        </button>
      </div>
    </template>
  </ActionDropdown>
  <component
    :is="AgentEditModal"
    v-if="AgentEditModal"
    ref="agentEditModalRef"
    :backend-options="agentBackendOptions"
    @saved="handleAgentSaved"
  />
</template>

<script setup>
import { computed, nextTick, ref, shallowRef } from 'vue'
import { message } from 'ant-design-vue'
import { Settings2, Check, Plus } from '@lucide/vue'
import { storeToRefs } from 'pinia'
import { agentApi } from '@/apis/agent_api'
import ActionDropdown from '@/shared/ui/ActionDropdown.vue'
import ActionTrigger from '@/shared/ui/ActionTrigger.vue'
import FallbackAvatar from '@/shared/ui/FallbackAvatar.vue'
import { isBuiltinAgent, useAgentStore } from '@/modules/agents/model/agent'
import { normalizeAgentBackendOption } from '@/modules/agents/model/agentConfigUtils'

const AgentEditModal = shallowRef(null)
const props = defineProps({
  agentId: { type: String, default: '' },
  hasActiveThread: Boolean,
  isCreatingThread: Boolean,
  startNewSession: { type: Function, required: true }
})
const agentStore = useAgentStore()
const { agents, selectedAgentId: defaultAgentId, isLoadingConfig } = storeToRefs(agentStore)
const selectedAgentId = computed(() => props.agentId || defaultAgentId.value)
const agentEditModalRef = ref(null)
const agentQuickSwitchOptions = computed(() =>
  (agents.value || [])
    .filter((agent) => agent.can_run)
    .map((agent) => ({
      label: agent.name || agent.agent_id,
      value: agent.agent_id,
      icon: agent.icon || '',
      isBuiltin: isBuiltinAgent(agent),
      isDefault: agent.is_default
    }))
)

const currentAgentOption = computed(() =>
  agentQuickSwitchOptions.value.find((agent) => agent.value === selectedAgentId.value)
)

const currentAgentLabel = computed(() => {
  if (isLoadingConfig.value) return '加载中...'
  return currentAgentOption.value?.label || '智能体'
})

const agentSearchKeyword = ref('')
const filteredAgentOptions = computed(() => {
  const keyword = agentSearchKeyword.value.trim().toLocaleLowerCase()
  return agentQuickSwitchOptions.value.filter((agent) =>
    agent.label.toLocaleLowerCase().includes(keyword)
  )
})

const agentDropdownOpen = ref(false)
const agentBackendOptions = ref([])
const agentBackendsLoaded = ref(false)

/** 编辑弹窗与后端选项只在用户打开时加载。 */
const loadAgentBackends = async () => {
  if (agentBackendsLoaded.value) return
  const [response, { default: Editor }] = await Promise.all([
    agentApi.getAgentBackends(),
    import('./AgentEditModal.vue')
  ])
  agentBackendOptions.value = (response.backends || []).filter((backend) => backend.can_create).map(normalizeAgentBackendOption)
  AgentEditModal.value = Editor
  agentBackendsLoaded.value = true
  await nextTick()
}

const handleAgentSwitch = async (agentId, hasActiveThread, isCreatingThread) => {
  if (!agentId || agentId === selectedAgentId.value) return
  if (isCreatingThread) {
    message.info('正在创建新对话，请稍候')
    return
  }
  if (hasActiveThread) {
    message.info('当前对话已绑定智能体，请新建对话后切换')
    return
  }
  try {
    await agentStore.selectAgent(agentId)
    agentDropdownOpen.value = false
  } catch (error) {
    console.error('切换智能体出错:', error)
    message.error('切换智能体失败')
  }
}

const handleAgentSaved = async ({ mode } = {}) => {
  if (mode === 'create') {
    await props.startNewSession()
  }

  await agentStore.fetchAgents()
  if (selectedAgentId.value) {
    await agentStore.fetchAgentDetail(selectedAgentId.value, true)
  }
}

const openCreateAgent = async () => {
  agentDropdownOpen.value = false
  try {
    await loadAgentBackends()
    agentEditModalRef.value?.openCreate()
  } catch (error) {
    message.error(error.message || '打开新建智能体弹窗失败')
  }
}

const openAgentManagement = async () => {
  agentDropdownOpen.value = false
  if (!selectedAgentId.value) {
    message.warning('请先选择智能体')
    return
  }
  try {
    await loadAgentBackends()
    await agentEditModalRef.value?.openEdit(selectedAgentId.value)
  } catch (error) {
    message.error(error.message || '打开智能体配置失败')
  }
}
</script>

<style scoped>
.agent-switch-empty {
  padding: 20px 8px;
  color: var(--gray-500);
  text-align: center;
  font-size: 13px;
}
</style>
