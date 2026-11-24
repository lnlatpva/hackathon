import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const apiTarget = process.env.VITE_API_PROXY || 'http://127.0.0.1:8000'
const apiProxy = { target: apiTarget, changeOrigin: true }

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': apiProxy,
      '/docs': apiProxy,
      '/openapi.json': apiProxy,
      '/health': apiProxy,
    },
  },
  test: { environment: 'node', include: ['src/tests/**/*.test.ts'] },
})
