import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ['helene-unreconnoitred-overslowly.ngrok-free.dev'],
    proxy: {
      '/simplify': 'http://localhost:8082',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
