import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  envDir: '../',
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/ask': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
  test: {
    environmentMatchGlobs: [
      ['convex/**/*.test.ts', 'edge-runtime'],
      ['tests/**/*.test.ts', 'jsdom'],
    ],
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.test.ts', 'convex/**/*.test.ts'],
  },
})
