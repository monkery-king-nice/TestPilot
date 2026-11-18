import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// TestPilot 前端构建配置。
// 开发代理：前端通过 /api 访问，代理到后端 127.0.0.1:8000（见 docs/api-alpha.md）。
// 演示服务（郭泽强）默认 127.0.0.1:8010，由后端执行器访问，前端不直连。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false
  }
})
