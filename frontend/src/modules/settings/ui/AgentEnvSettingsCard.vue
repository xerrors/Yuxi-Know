<template>
  <div class="agent-env-settings">
    <UserSandboxSettingsCard ref="sandboxSettings" />
    <div class="header-section">
      <div class="header-content">
        <div class="section-title">环境变量</div>
        <p class="section-description">管理账户级环境变量，保存后对新启动的运行生效。</p>
      </div>
      <div class="header-actions">
        <a-button
          class="refresh-btn lucide-icon-btn"
          :loading="loading"
          title="刷新"
          @click="loadAgentEnv"
        >
          <template #icon><RefreshCw :size="16" :class="{ spin: loading }" /></template>
        </a-button>
        <a-button
          :loading="verifying"
          :disabled="loading || saving || hasUnsavedChanges || !savedEnvKeys.length"
          @click="verifyAgentEnv"
        >
          验证配置
        </a-button>
        <a-button type="primary" :loading="saving" :disabled="loading" @click="saveAgentEnv">
          保存配置
        </a-button>
      </div>
    </div>

    <div class="env-tip">
      <Info :size="14" class="tip-icon" />
      <span>当前运行保持启动时的配置。验证读取最新保存值，并自动创建或恢复环境。</span>
    </div>

    <div class="env-verification" aria-live="polite">
      <p v-if="hasUnsavedChanges">配置尚未保存，保存后可执行生效验证。</p>
      <p v-else-if="savedEnvKeys.length && !verification && !verificationError">
        配置已保存，尚未完成生效验证。
      </p>
      <a-alert v-if="verificationError" type="error" :message="verificationError" show-icon />
      <template v-if="verification">
        <p>
          验证时间：{{
            new Date(verification.verified_at).toLocaleString('zh-CN', { hour12: false })
          }}。结果仅适用于本次命令进程。
        </p>
      </template>
    </div>

    <a-spin :spinning="loading">
      <McpEnvEditor
        :key="editorRevision"
        :modelValue="draftEnv"
        :locked-keys="savedEnvKeys"
        :key-verification="verificationByKey"
        conceal-locked-values
        @update:modelValue="updateDraftEnv"
      />
    </a-spin>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Info, RefreshCw } from '@lucide/vue'
import { agentEnvApi } from '@/apis/agent_env_api'
import McpEnvEditor from '@/modules/agents/ui/McpEnvEditor.vue'
import UserSandboxSettingsCard from './UserSandboxSettingsCard.vue'

const ENV_KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/
const MAX_ENV_COUNT = 200
const MAX_ENV_KEY_LENGTH = 128
const MAX_ENV_VALUE_LENGTH = 32768

const loading = ref(false)
const sandboxSettings = ref(null)
const saving = ref(false)
const verifying = ref(false)
const verification = ref(null)
const verificationError = ref('')
const savedUpdatedAt = ref(null)
let verificationRevision = 0
const draftEnv = ref({})
const lastSavedEnv = ref({})
const editorRevision = ref(0)

const normalizeEnv = (env) => {
  if (!env || typeof env !== 'object' || Array.isArray(env)) {
    return {}
  }
  return Object.fromEntries(
    Object.entries(env)
      .map(([key, value]) => [key.trim(), value == null ? '' : String(value)])
      .filter(([key]) => key)
  )
}

const isSameEnv = (left, right) => {
  const leftEntries = Object.entries(left)
  const rightEntries = Object.entries(right)
  if (leftEntries.length !== rightEntries.length) return false
  return leftEntries.every(([key, value]) => right[key] === value)
}

const savedEnvKeys = computed(() => Object.keys(lastSavedEnv.value || {}))
const hasUnsavedChanges = computed(() => !isSameEnv(draftEnv.value, lastSavedEnv.value))
const verificationByKey = computed(
  () => new Map((verification.value?.variables || []).map(({ key, matches }) => [key, matches]))
)

function invalidateVerification() {
  verificationRevision += 1
  verification.value = null
  verificationError.value = ''
  return verificationRevision
}

const updateDraftEnv = (value) => {
  const nextEnv = normalizeEnv(value)
  if (isSameEnv(draftEnv.value, nextEnv)) return
  draftEnv.value = nextEnv
  invalidateVerification()
}

const validateEnv = (env) => {
  const entries = Object.entries(env)
  if (entries.length > MAX_ENV_COUNT) {
    message.error(`环境变量数量上限为 ${MAX_ENV_COUNT} 个`)
    return false
  }

  for (const [key, value] of entries) {
    if (key.length > MAX_ENV_KEY_LENGTH) {
      message.error(`变量名长度上限为 ${MAX_ENV_KEY_LENGTH} 个字符`)
      return false
    }
    if (!ENV_KEY_PATTERN.test(key)) {
      message.error(`变量名 ${key} 格式无效`)
      return false
    }
    if (value.length > MAX_ENV_VALUE_LENGTH) {
      message.error(`变量 ${key} 的值超过长度上限`)
      return false
    }
  }
  return true
}

const loadAgentEnv = async () => {
  invalidateVerification()
  loading.value = true
  try {
    const res = await agentEnvApi.get()
    const env = normalizeEnv(res.env)
    draftEnv.value = env
    lastSavedEnv.value = env
    savedUpdatedAt.value = res.updated_at
    editorRevision.value += 1
  } catch (error) {
    message.error(error.message || '环境变量读取失败')
  } finally {
    loading.value = false
  }
}

const saveAgentEnv = async () => {
  const env = normalizeEnv(draftEnv.value)
  if (!validateEnv(env)) return
  if (isSameEnv(env, lastSavedEnv.value)) {
    message.info('配置无变更')
    return
  }

  saving.value = true
  invalidateVerification()
  try {
    const res = await agentEnvApi.update(env)
    draftEnv.value = env
    lastSavedEnv.value = env
    savedUpdatedAt.value = res.updated_at
    editorRevision.value += 1
    message.success('配置已保存，将在新启动的运行中生效')
  } catch (error) {
    message.error(error.message || '环境变量保存失败')
  } finally {
    saving.value = false
  }
}

const verifyAgentEnv = async () => {
  const revision = invalidateVerification()
  verifying.value = true
  try {
    const result = await agentEnvApi.verify()
    if (revision !== verificationRevision || hasUnsavedChanges.value) return
    if (result.updated_at !== savedUpdatedAt.value) {
      verificationError.value = '配置已更新，请刷新后重新验证。'
      return
    }
    verification.value = result
  } catch (error) {
    if (revision === verificationRevision && !hasUnsavedChanges.value) {
      verificationError.value = error.message || '生效验证失败，请检查环境状态'
    }
  } finally {
    verifying.value = false
    await sandboxSettings.value?.refresh()
  }
}

onMounted(loadAgentEnv)
</script>

<style lang="less" scoped>
.agent-env-settings {
  padding-top: 12px;

  .header-section {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 16px;
    margin-bottom: 14px;

    @media (max-width: 760px) {
      align-items: stretch;
      flex-direction: column;
    }
  }

  .header-content {
    flex: 1;
    min-width: 0;

    .section-title {
      font-size: 16px;
      font-weight: 500;
      color: var(--gray-900);
      line-height: 1.4;
      margin: 0 0 6px;
    }

    .section-description {
      font-size: 14px;
      color: var(--gray-600);
      line-height: 1.4;
      margin: 0;
    }
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
    flex-wrap: wrap;

    .refresh-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: 6px;
      transition: all 0.2s ease;

      &:hover {
        background: var(--gray-25);
      }

      .spin {
        animation: spin 1s linear infinite;
      }
    }
  }

  .env-tip {
    margin-bottom: 14px;
    padding: 8px 12px;
    border-radius: 6px;
    background: var(--gray-50);
    border: 1px solid var(--gray-150);
    color: var(--gray-600);
    font-size: 12px;
    line-height: 18px;
    display: flex;
    align-items: center;
    gap: 8px;

    .tip-icon {
      color: var(--gray-400);
      flex-shrink: 0;
    }
  }

  .env-verification {
    color: var(--gray-600);
    font-size: 12px;
    margin-bottom: 14px;
  }
}

:deep(.spin) {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}
</style>
