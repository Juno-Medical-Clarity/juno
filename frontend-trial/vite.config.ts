import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // D3's shared surface: CarePlanView, MedicalTerm (its dependency),
      // buildPdfHtml, and types/. Nothing else in ../frontend/src should be
      // imported through this alias — see PRD §4.4 for why the boundary is
      // enforced by convention (code review), not by tooling.
      '@main': path.resolve(__dirname, '../frontend/src'),
    },
  },
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
    port: 5174,        // pinned, not left to Vite's auto-increment — backend/app.py's
    strictPort: true,   // CORS list (SP4) hard-codes localhost:5174 for this dev
                        // server; strictPort makes a collision fail loudly instead
                        // of silently drifting to 5175 and breaking CORS.
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
