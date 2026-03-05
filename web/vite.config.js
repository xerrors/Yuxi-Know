import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      proxy: {
        '^/api': {
          // 生产环境
          target: env.VITE_API_URL || 'http://8.148.22.98/',
          // 颖哥本地环境，用于测试
          // target: env.VITE_API_URL || 'https://r4x8gzlef8.fy.takin.cc/',
          changeOrigin: true
        }
      },
      watch: {
        usePolling: true,
        ignored: ['**/node_modules/**', '**/dist/**']
      },
      host: '0.0.0.0'
    }
  }
})



