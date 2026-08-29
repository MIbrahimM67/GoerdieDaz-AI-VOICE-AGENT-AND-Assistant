import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy REST API calls to FastAPI backend
      '/auth': 'http://localhost:8000',
      '/personas': 'http://localhost:8000',
      '/session': 'http://localhost:8000',
      '/memory': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
      '/core': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      // Proxy WebSocket connections
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
