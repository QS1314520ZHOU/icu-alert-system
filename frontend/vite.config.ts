import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
  const createProxyEntry = () => ({
    target: backendTarget,
    changeOrigin: true,
    ws: true,
    configure: (proxy: any) => {
      proxy.on('error', (err: Error, req: any) => {
        const url = req?.url || '(unknown url)'
        console.error(`[vite-proxy] ${url} -> ${backendTarget} failed: ${err.message}`)
      })
    },
  })

  console.info(`[vite] proxying /api and /health to ${backendTarget}`)

  return {
    assetsInclude: ['**/*.glb', '**/*.gltf', '**/*.svg'],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./tests/setup.ts'],
      coverage: {
        reporter: ['text', 'html'],
        include: ['src/components/HumanBody/**/*.{ts,vue}', 'src/stores/humanBodyAlarmStore.ts'],
        exclude: ['src/components/HumanBody/composables/useThreeScene.ts', 'src/components/HumanBody/composables/useOrganPicker.ts', 'src/components/HumanBody/composables/useAlarmHighlight.ts', 'src/components/HumanBody/composables/useCameraFocus.ts'],
      },
    },
    resolve: {
      // In restricted Windows environments, Vite's safe realpath optimization may attempt
      // to spawn `net use` and fail with EPERM. Preserving symlinks avoids that path.
      preserveSymlinks: true,
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            if (id.includes('vue-router')) {
              return 'vendor-router'
            }
            if (id.includes('pinia')) {
              return 'vendor-pinia'
            }
            if (id.includes('axios')) {
              return 'vendor-axios'
            }
            if (id.includes('/vue/') || id.includes('\\vue\\') || id.includes('@vue')) {
              return 'vendor-vue'
            }
          },
        },
      },
    },
    plugins: [
      vue(),
      VitePWA({
        registerType: 'autoUpdate',
        injectRegister: 'auto',
        includeAssets: ['vite.svg'],
        manifest: {
          name: 'ICU智能协同工作台',
          short_name: 'ICU协同',
          description: '重症监护预警、交班、查房与质控协同平台',
          theme_color: '#0e1728',
          background_color: '#0a0a14',
          display: 'standalone',
          start_url: '/',
          icons: [
            {
              src: '/vite.svg',
              sizes: '192x192',
              type: 'image/svg+xml',
            },
            {
              src: '/vite.svg',
              sizes: '512x512',
              type: 'image/svg+xml',
            },
          ],
        },
        workbox: {
          clientsClaim: true,
          skipWaiting: true,
          cleanupOutdatedCaches: true,
          globPatterns: ['**/*.{js,css,html,svg,png,ico}'],
          maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
          runtimeCaching: [
            {
              urlPattern: ({ request }) => request.mode === 'navigate',
              handler: 'NetworkFirst',
              options: {
                cacheName: 'pages-cache',
                expiration: {
                  maxEntries: 20,
                  maxAgeSeconds: 7 * 24 * 60 * 60,
                },
              },
            },
            {
              urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
              handler: 'NetworkFirst',
              options: {
                cacheName: 'api-cache',
                networkTimeoutSeconds: 4,
                expiration: {
                  maxEntries: 60,
                  maxAgeSeconds: 30 * 60,
                },
              },
            },
          ],
        },
      }),
    ],
    server: {
      host: '::',
      port: 5173,
      // 允许通过这些域名访问 dev server（Vite 默认会拒绝陌生 Host 头）
      allowedHosts: ['alert.jylb.fun', '.jylb.fun', 'localhost'],
      // 通过 NPM/Cloudflare 反代时，告诉浏览器 HMR WebSocket 走 wss + 443
      hmr: {
        host: 'alert.jylb.fun',
        protocol: 'wss',
        clientPort: 443,
      },
      proxy: {
        '/api': createProxyEntry(),
        '/health': createProxyEntry(),
        '/ws': createProxyEntry(), // 后端实时告警 WebSocket
      },
    },
  }
})
