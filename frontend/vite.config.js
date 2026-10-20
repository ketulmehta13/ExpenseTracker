import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // Without this the offline cache served the previous version's page until a later reload,
      // so new features appeared and disappeared between refreshes. Now pages come from the
      // network first (the cache is only the offline fallback), and a new version takes over at once.
      workbox: {
        globPatterns: ['**/*.{js,css,ico,png,svg,webp,woff2}'],
        navigateFallback: null,
        runtimeCaching: [
          {
            urlPattern: ({ request }) => request.mode === 'navigate',
            handler: 'NetworkFirst',
            options: { cacheName: 'pages', networkTimeoutSeconds: 4 },
          },
        ],
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
      },
      includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
      manifest: {
        name: 'Ketul Expense Tracker',
        short_name: 'ExpenseTracker',
        description: 'Professional Expense Tracker for personal finance management',
        theme_color: '#0d3a35',
        icons: [
          {
            src: 'icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            // Full-bleed, with the artwork inside the safe zone that launchers crop to
            src: 'icons/maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable'
          }
        ]
      }
    })
  ],
  server: {
    host: '0.0.0.0', // Allows mobile login testing over local network
  }
})
