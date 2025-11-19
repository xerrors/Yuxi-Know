import { ref, watch } from 'vue'
import { defineStore } from 'pinia'

export const useThemeStore = defineStore('theme', () => {
  // 从 localStorage 读取保存的主题，默认为浅色
  const isDark = ref(localStorage.getItem('theme') === 'dark')

  // 浅色主题配置
  const lightTheme = {
    token: {
      fontFamily: "'HarmonyOS Sans SC', Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;",
      colorPrimary: '#1c7796',
      colorPrimaryBg: '#d6eef1',
      colorInfo: '#0058d4',
      colorSuccess: '#45b30e',
      colorError: '#c73234',
      colorBgBase: '#ffffff',
      colorBgContainer: '#ffffff',
      colorText: '#000000',
      colorTextSecondary: '#666666',
      borderRadius: 8,
      wireframe: false,
    },
  }

  // 深色主题配置
  const darkTheme = {
    token: {
      fontFamily: "'HarmonyOS Sans SC', Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;",
      colorPrimary: '#4a9fb8',
      colorPrimaryBg: '#1a3a42',
      colorInfo: '#3d8fff',
      colorSuccess: '#52c41a',
      colorError: '#ff4d4f',
      colorBgBase: '#141414',
      colorBgContainer: '#1f1f1f',
      colorBgElevated: '#262626',
      colorText: 'rgba(255, 255, 255, 0.85)',
      colorTextSecondary: 'rgba(255, 255, 255, 0.65)',
      colorBorder: '#434343',
      borderRadius: 8,
      wireframe: false,
    },
  }

  // 当前主题配置
  const currentTheme = ref(isDark.value ? darkTheme : lightTheme)

  // 切换主题
  function toggleTheme() {
    isDark.value = !isDark.value
    currentTheme.value = isDark.value ? darkTheme : lightTheme
    localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
    updateDocumentTheme()
  }

  // 设置主题
  function setTheme(dark) {
    isDark.value = dark
    currentTheme.value = dark ? darkTheme : lightTheme
    localStorage.setItem('theme', dark ? 'dark' : 'light')
    updateDocumentTheme()
  }

  // 更新 document 的主题类
  function updateDocumentTheme() {
    if (isDark.value) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  // 初始化时设置主题
  updateDocumentTheme()

  return {
    isDark,
    currentTheme,
    toggleTheme,
    setTheme,
  }
})
