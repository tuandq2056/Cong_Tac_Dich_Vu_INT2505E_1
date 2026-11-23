import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const gateway = process.env.VITE_GATEWAY_URL ?? 'http://localhost:8080'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': gateway,
      '/ws': { target: gateway.replace('http', 'ws'), ws: true },
      '/healthz': gateway,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
})
