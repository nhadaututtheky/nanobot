import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/ws': {
        target: 'ws://localhost:18790',
        ws: true,
      },
      '/ai-gateway': {
        target: 'http://localhost:8317/v0/management',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/ai-gateway/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react-dom') || id.includes('react-router')) return 'vendor-react'
            if (id.includes('@tanstack/react-query')) return 'vendor-query'
            if (id.includes('recharts') || id.includes('d3-')) return 'vendor-recharts'
            if (id.includes('framer-motion')) return 'vendor-motion'
            if (id.includes('@radix-ui') || id.includes('radix-ui') || id.includes('cmdk')) return 'vendor-radix'
            if (id.includes('react-hook-form') || id.includes('@hookform') || id.includes('zod')) return 'vendor-forms'
            if (id.includes('lucide-react')) return 'vendor-icons'
            if (id.includes('class-variance-authority') || id.includes('clsx') || id.includes('tailwind-merge')) return 'vendor-utils'
          }
        },
      },
    },
  },
})
