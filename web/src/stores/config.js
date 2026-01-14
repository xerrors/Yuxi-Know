import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { configApi } from '@/apis/system_api'

export const useCounterStore = defineStore('counter', () => {
  const count = ref(0)
  const doubleCount = computed(() => count.value * 2)
  function increment() {
    count.value++
  }

  return { count, doubleCount, increment }
})

export const useConfigStore = defineStore('config', () => {
  const config = ref({})
  function setConfig(newConfig) {
    config.value = newConfig
  }

  function setConfigValue(key, value) {
    config.value[key] = value
    configApi.updateConfigBatch({ [key]: value }).then((data) => {
      console.debug('Success:', data)
      setConfig(data)
    })
  }

  function setConfigValues(items) {
    // 更新本地配置
    for (const key in items) {
      config.value[key] = items[key]
    }

    // 发送到服务器
    configApi.updateConfigBatch(items).then((data) => {
      console.debug('Success:', data)
      setConfig(data)
    })
  }

  function refreshConfig() {
    configApi.getConfig().then((data) => {
      console.log('config', data)
      setConfig(data)
    })
  }

  return { config, setConfig, setConfigValue, refreshConfig, setConfigValues }
})
