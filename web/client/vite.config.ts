import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  define: {
    // Replace process.env with browser-safe values
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'production'),
    'process.env': JSON.stringify({ NODE_ENV: process.env.NODE_ENV || 'production' })
  },
  build: {
    outDir: 'dist',
    lib: {
      entry: resolve(__dirname, 'ts/main.ts'),
      name: 'AirportExplorer',
      fileName: 'main',
      formats: ['iife']
    },
    rollupOptions: {
      external: ['leaflet'], // Leaflet is loaded from CDN
      output: {
        globals: {
          leaflet: 'L' // Leaflet is exposed as global L
        }
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'ts')
    }
  },
  server: {
    port: 3001,
    host: true,
    allowedHosts: ['ovh.zhaoqian.me', 'localhost', '127.0.0.1', 'flyfun.downle.eu.org'],
    hmr: {
      // Disable full page reload - only update modules
      overlay: true,
      // Prevent automatic full page reload
      protocol: 'ws'
    },
    // Watch options to reduce unnecessary reloads
    watch: {
      ignored: ['**/node_modules/**', '**/dist/**']
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy, _options) => {
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            // Forward the original host and protocol to the backend
            const host = req.headers.host || 'localhost:3001';
            const proto = req.headers['x-forwarded-proto'] || (req.connection.encrypted ? 'https' : 'http');

            proxyReq.setHeader('X-Forwarded-Host', host);
            proxyReq.setHeader('X-Forwarded-Proto', proto);
          });
        }
      }
    }
  },
  // Enable HMR for TypeScript files
  optimizeDeps: {
    exclude: []
  }
});

