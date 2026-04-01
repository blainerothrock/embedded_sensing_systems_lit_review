import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:5001',
      '/pdfs': 'http://127.0.0.1:5001',
    },
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
  },
})
