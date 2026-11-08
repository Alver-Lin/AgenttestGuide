import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue'],
          ui: ['ant-design-vue'],
          markdown: ['marked', 'dompurify'],
        },
      },
    },
  },
  server: {
    port: 5317,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8317', changeOrigin: true } },
  },
})
