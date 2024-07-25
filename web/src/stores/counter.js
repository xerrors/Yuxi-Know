import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

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
    fetch('/api/config', {
      method: 'POST',
      body: JSON.stringify(config.value),
    })
    .then(response => response.json())
    .then(data => {
      console.log('Success:', data)
    })
  }

  return { config, setConfig, setConfigValue }
})