/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
    },
  },
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
