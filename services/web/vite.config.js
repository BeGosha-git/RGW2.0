import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'build',
    assetsDir: 'assets',
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      // WebSocket proxy for terminal dev mode
      // In production the frontend connects directly to ws://host:8765
      '/ws-terminal': {
        target: 'ws://localhost:8765',
        ws: true,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ws-terminal/, ''),
      },
    }
  }
})
