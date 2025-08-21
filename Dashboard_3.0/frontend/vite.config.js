import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa';
import path from 'path'

 // https://vite.dev/config/
 export default defineConfig({
   plugins: [
     react(),
     VitePWA({
       registerType: 'autoUpdate',
       includeAssets: ['favicon.svg', 'favicon.ico', 'robots.txt'],
       manifest: {
         name: 'Helios Priority Dashboard',
         short_name: 'Helios',
         description: 'Central cockpit for client and task intelligence',
         theme_color: '#6b21a8',
         background_color: '#ffffff',
         display: 'standalone',
         start_url: '/',
         icons: [ /* …snip… */ ]
       }
     })
   ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
   server: {
     proxy: {
       '/api': 'http://localhost:3333',
     },
   },
 });
