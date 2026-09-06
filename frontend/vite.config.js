import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API is proxied rather than called cross-origin so the frontend has one
// origin in development and in a built deployment, and no CORS list has to be
// kept in step with wherever the app happens to be served from.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
