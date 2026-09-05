import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // frontend/ and frontend-trial/ are separate npm projects (no workspace/
      // hoisting), each with its own node_modules/react + react-dom. Node/Vite
      // resolve bare `react` specifiers relative to the IMPORTING file, so
      // CarePlanView.tsx/MedicalTerm.tsx (physically under ../frontend/src,
      // pulled in only via the @main alias below) would otherwise resolve to
      // frontend/node_modules/react — a second React instance with its own
      // unset hook dispatcher. Any hook call inside that shared surface (e.g.
      // MedicalTerm's useState, ResultCard's useState in CarePlanView) then
      // throws "Cannot read properties of null (reading 'useState')", and
      // with no error boundary anywhere in the app that blanks the entire
      // page. These two aliases pin every `react`/`react-dom` import —
      // regardless of which physical directory the importing file lives in —
      // to frontend-trial's own single copy, so there is only ever one
      // dispatcher. Must stay ABOVE @main so Vite's alias resolution (which
      // matches in order) doesn't need @main's subtree to escape it anyway;
      // order doesn't strictly matter here since the keys don't overlap, but
      // keep react/react-dom first for visibility as the load-bearing entries.
      'react': path.resolve(__dirname, 'node_modules/react'),
      'react-dom': path.resolve(__dirname, 'node_modules/react-dom'),
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
