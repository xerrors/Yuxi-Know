<template>
  <div class="user-config-settings">
    <a-spin :spinning="loading">
      <div class="config-panel">
        <div class="config-row">
          <div class="config-meta">
            <div class="config-title-line">
              <span class="settings-form-label">是否启用 Memory</span>
              <button type="button" class="memory-view-button" @click="viewMemory">查看 Memory</button>
            </div>
          </div>
          <a-switch :checked="draftEnableMemory" @change="handleMemoryChange" />
        </div>
      </div>
    </a-spin>
  </div>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { userConfigApi } from '@/apis/user_config_api'

const loading = ref(false)
const saving = ref(false)
const draftEnableMemory = ref(false)
const savedEnableMemory = ref(false)
const router = useRouter()
const settingsModal = inject('settingsModal')

/** 打开个人 Memory 文件并收起账户设置。 */
const viewMemory = async () => {
  await router.push({ path: '/workspace', query: { open: '/agents/MEMORY.md' } })
  settingsModal.closeSettingsModal()
}

const applyResponse = (res) => {
  draftEnableMemory.value = res.enable_memory
  savedEnableMemory.value = res.enable_memory
}

const loadUserConfig = async () => {
  loading.value = true
  try {
    const res = await userConfigApi.get()
    applyResponse(res)
  } catch (error) {
    message.error(error.message || '加载用户配置失败')
  } finally {
    loading.value = false
  }
}

const handleMemoryChange = (val) => {
  draftEnableMemory.value = Boolean(val)
  saveUserConfig()
}

const saveUserConfig = async () => {
  saving.value = true
  try {
    const res = await userConfigApi.update({ enable_memory: draftEnableMemory.value })
    applyResponse(res)
    message.success('用户配置已保存')
  } catch (error) {
    message.error(error.message || '保存用户配置失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadUserConfig)

defineExpose({ refresh: loadUserConfig })
</script>

<style lang="less" scoped>
.user-config-settings {
  .config-panel {
    border-top: 1px solid var(--gray-150);
  }

  .config-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    padding: 16px 0 0;

    @media (max-width: 560px) {
      align-items: flex-start;
      flex-direction: column;
    }
  }

  .config-meta {
    min-width: 0;
  }

  .config-title-line {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .memory-view-button {
    border: 1px solid var(--gray-150);
    border-radius: 999px;
    background: var(--gray-0);
    color: var(--color-text-secondary);
    padding: 3px 10px;
    font: inherit;
    font-size: 12px;
    line-height: 20px;
    cursor: pointer;

    &:hover {
      background: var(--gray-50);
      color: var(--main-color);
    }

    &:focus-visible {
      outline: 2px solid var(--main-color);
      outline-offset: 2px;
    }
  }
}
</style>
