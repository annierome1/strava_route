import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/route':  { target: 'http://localhost:8000', changeOrigin: true },
      '/routes': { target: 'http://localhost:8000', changeOrigin: true },
      '/dna':    { target: 'http://localhost:8000', changeOrigin: true },
      '/irl':    { target: 'http://localhost:8000', changeOrigin: true },
      '/config': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
  },
})
