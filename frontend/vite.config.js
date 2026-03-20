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
})
