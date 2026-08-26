import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：开发环境默认经代理转发到本地 Flask，可被 .env 覆盖
const proxyTarget = process.env.VITE_DEV_PROXY_TARGET || 'http://localhost:8081'

// 通用代理选项：SSE 流式需关闭代理层压缩，避免压缩后的 chunked 流导致浏览器 fetch 卡死/中止（net::ERR_ABORTED）
const _proxy = {
  target: proxyTarget,
  changeOrigin: true,
  compress: false,
}

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
      '/health': _proxy,
      '/api': _proxy,
    },
  },
})