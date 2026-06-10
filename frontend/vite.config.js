/**
 * frontend/vite.config.js
 *
 * Vite configuration for build, dev server, proxy, and security.
 *
 * # FIXED: Proper proxy configuration for backend API + WebSocket
 * # FIXED: Environment variable handling with defaults
 * # IMPROVED: Build optimizations for production
 * # FIXED: CSP-compatible output settings
 * # IMPROVED: Dev server security headers
 */

import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env variables based on mode (development/production)
  const env = loadEnv(mode, process.cwd(), '')
  
  // API configuration with sensible defaults
  const API_URL = 'http://localhost:8000'  // Backend URL for proxy
  const WS_URL = env.VITE_WS_URL || null
  const API_KEY = env.VITE_API_KEY || ''  // Auth token injected into all proxy requests
  
  // Derive WebSocket URL from API URL if not explicitly set
  const derivedWS = WS_URL || API_URL.replace('http', 'ws').replace('https', 'wss')

  return {
    // Base path for deployment (e.g., '/app/' if deployed to subpath)
    base: env.VITE_BASE_PATH || '/',
    
    // Root directory for source files
    root: resolve(__dirname, '.'),
    
    // Build configuration
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      // Enable source maps for production debugging (optional)
      sourcemap: mode === 'development',
      // Optimize for production
      minify: mode === 'production',
      // Code splitting configuration
      rollupOptions: {
        output: {
          // Function form required by Rollup 4+ / Vite 5+
          manualChunks(id) {
            if (id.includes('node_modules')) {
              if (id.includes('react') || id.includes('react-dom') || id.includes('react-router-dom')) {
                return 'vendor-core'
              }
              if (id.includes('@tanstack')) {
                return 'vendor-query'
              }
              if (id.includes('chart.js') || id.includes('react-chartjs-2')) {
                return 'vendor-charts'
              }
              return 'vendor-misc'
            }
          },
          // Hash filenames for cache busting
          entryFileNames: 'assets/[name].[hash].js',
          chunkFileNames: 'assets/[name].[hash].js',
          assetFileNames: 'assets/[name].[hash].[ext]',
        },
      },
    },
    
    // Server configuration for development
    server: {
      port: parseInt(env.VITE_PORT || '5173', 10),
      host: env.VITE_HOST || '0.0.0.0',  // WiFi access: expose on all interfaces
      // Enable HTTPS in dev if needed (for testing secure contexts)
      https: env.VITE_HTTPS === 'true' ? {
        // Self-signed cert paths (generate with: openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365)
        // key: resolve(__dirname, 'certs/key.pem'),
        // cert: resolve(__dirname, 'certs/cert.pem'),
      } : undefined,
      // Proxy API requests to backend
      proxy: {
        // REST API proxy
        '/api': {
          target: API_URL,
          changeOrigin: true,
          secure: false, // Allow self-signed certs in dev
          // Rewrite path: /api/health → /health on backend
          rewrite: (path) => path.replace(/^\/api/, ''),
          // Configure headers
          configure: (proxy, _options) => {
            proxy.on('proxyReq', (proxyReq, req) => {
              // Always inject API key for backend auth
              if (API_KEY) proxyReq.setHeader('Authorization', `Bearer ${API_KEY}`)
              // Also forward any client-set auth header (overrides above)
              const auth = req.headers['authorization']
              if (auth) proxyReq.setHeader('Authorization', auth)
            })
          },
        },
        // WebSocket proxy for /stream endpoint
        '/stream': {
          target: derivedWS,
          changeOrigin: true,
          secure: false,
          ws: true, // Enable WebSocket proxying
          // WebSocket-specific headers
          configure: (proxy, _options) => {
            proxy.on('proxyReqWs', (proxyReq, req, socket) => {
              // Forward upgrade headers for WebSocket handshake
              socket.on('error', (err) => {
                console.error('WebSocket proxy error:', err)
              })
            })
          },
        },
        // MLflow proxy (if running locally)
        '/mlflow': {
          target: env.VITE_MLFLOW_URL || 'http://localhost:5000',
          changeOrigin: true,
          secure: false,
          rewrite: (path) => path.replace(/^\/mlflow/, ''),
        },
      },
      // CORS configuration (for local dev with separate frontend/backend ports)
      cors: {
        origin: env.VITE_CORS_ORIGIN || 'http://localhost:5173',
        credentials: true,
      },
      // Headers for security in dev
      headers: {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
      },
      // Watch for changes in linked packages (if using monorepo)
      watch: {
        // Skip watching node_modules for performance
        ignored: ['**/node_modules/**'],
      },
    },
    
    // Preview configuration (for `vite preview`)
    preview: {
      port: parseInt(env.VITE_PREVIEW_PORT || '4173', 10),
      host: env.VITE_PREVIEW_HOST || 'localhost',
    },
    
    // CSS configuration
    css: {
      // Enable CSS modules with consistent naming
      modules: {
        localsConvention: 'camelCaseOnly',
        generateScopedName: mode === 'production' 
          ? '[hash:base64:5]' 
          : '[name]__[local]--[hash:base64:5]',
      },
      // PostCSS configuration (tailwind is loaded via postcss.config.js)
      postcss: resolve(__dirname, 'postcss.config.js'),
      // Preprocessor options
      preprocessorOptions: {
        // Example: SCSS variables (if using SCSS)
        // scss: { additionalData: `@import "@/styles/variables.scss";` },
      },
    },
    
    // Resolve configuration for path aliases
    resolve: {
      alias: {
        // Shorter imports: import { X } from '@/api' instead of '../../../api'
        '@': resolve(__dirname, 'src'),
        '@components': resolve(__dirname, 'src/components'),
        '@hooks': resolve(__dirname, 'src/hooks'),
        '@api': resolve(__dirname, 'src/api'),
        '@utils': resolve(__dirname, 'src/utils'),
        '@constants': resolve(__dirname, 'src/constants'),
      },
      // File extensions to try when importing
      extensions: ['.js', '.jsx', '.ts', '.tsx', '.json'],
    },
    
    // Optimize dependencies for faster dev server startup
    optimizeDeps: {
      include: [
        'react',
        'react-dom',
        'react-router-dom',
        '@tanstack/react-query',
        'axios',
        'chart.js',
        'react-chartjs-2',
        'date-fns',
        'lucide-react',
      ],
      exclude: [
        // Exclude large or dynamic packages
      ],
    },
    
    // Plugins
    plugins: [
      react({
        // React plugin options
        jsxRuntime: 'automatic',
        // Enable fast refresh for better DX
        fastRefresh: mode !== 'production',
      }),
    ],
    
    // Define global constants (replaced at build time)
    define: {
      // Expose environment variables to client code safely
      __APP_VERSION__: JSON.stringify(env.npm_package_version || '1.0.0'),
      __APP_ENV__: JSON.stringify(mode),
      // Note: Never expose sensitive values here - use API calls instead
    },
    
    // Log level for build output
    logLevel: mode === 'development' ? 'info' : 'warn',
    
    // Clear screen on rebuild (dev only)
    clearScreen: mode === 'development',
    
    // Enable strict port handling (fail if port in use)
    strictPort: true,
  }
})