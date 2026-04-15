import { defineConfig } from 'vite'

export default defineConfig({
  // Load .env from the project root (one level up from frontend/)
  envDir: '../',
  server: {
    proxy: {
      // Forward all /ask/* requests to the Flask API during development
      '/ask': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
  test: {
    environmentMatchGlobs: [
      ['convex/**/*.test.ts', 'edge-runtime'],
      ['tests/**/*.test.js', 'jsdom'],
    ],
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.test.js', 'convex/**/*.test.ts'],
  },
})
