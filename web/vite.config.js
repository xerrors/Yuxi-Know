import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  // 定义代理
  server: {
    proxy: {
      '^/api': {
        target: 'http://127.0.0.1:5000', // 5000端口是flask的Debug模式默认端口, 8000是非Debug模式默认端口
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    },
    watch: {
      ignored: ['**/node_modules/**', '**/dist/**'],
    },
  }
})
