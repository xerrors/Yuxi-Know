<template>
  <div v-if="server.auth_mode === 'oauth'" class="mcp-personal-connection" @click.stop>
    <span role="status">{{ mcpConnectionLabel(server.connection_status) }}</span>
    <a-button :loading="busy" :disabled="!server.enabled" @click="connect">
      {{ server.connection_status === 'connected' ? '重新连接' : '连接' }}
    </a-button>
    <a-button v-if="server.connection_status !== 'disconnected'" :disabled="busy" @click="disconnect">断开</a-button>
    <p v-if="error" role="alert">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { mcpApi } from '@/apis/mcp_api'
import { mcpConnectionLabel } from '@/modules/extensions/model/mcpOAuth'

const props = defineProps({ server: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const busy = ref(false)
const error = ref('')

async function connect() {
  busy.value = true
  error.value = ''
  try {
    const result = await mcpApi.connect(props.server.slug)
    window.location.assign(result.authorization_url)
  } catch (err) {
    error.value = err.message || '连接失败，请重试'
  } finally {
    busy.value = false
  }
}

async function disconnect() {
  busy.value = true
  error.value = ''
  try {
    await mcpApi.disconnect(props.server.slug)
    emit('changed')
  } catch (err) {
    error.value = err.message || '断开失败，请重试'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.mcp-personal-connection { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; margin-inline-start: auto; }
.mcp-personal-connection > span { color: var(--gray-700); font-size: 13px; }
@media (max-width: 600px) { .mcp-personal-connection :deep(.ant-btn) { min-height: 44px; } }
.mcp-personal-connection > p { color: var(--color-error-600); flex-basis: 100%; margin: 0; text-align: end; }
</style>
