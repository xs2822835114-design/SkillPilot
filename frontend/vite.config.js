import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：开发环境默认经代理转发到本地 Flask，可被 .env 覆盖
const proxyTarget = process.env.VITE_DEV_PROXY_TARGET || 'http://localhost:8081'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    // 仅本地开发代理；构建产物由网关统一路由到后端
    proxy: {
      '/health': { target: proxyTarget, changeOrigin: true },
      '/api': { target: proxyTarget, changeOrigin: true },
    },
  },
})