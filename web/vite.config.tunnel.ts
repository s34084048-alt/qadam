import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * Config for serving the demo through a public tunnel.
 *
 * Plain HTTP locally, on purpose. The tunnel terminates real, publicly trusted
 * TLS at its own hostname, and that is what makes the visitor's origin a
 * secure context — so the camera and the service worker work at the public URL
 * with no certificate warning at all. Putting a self-signed certificate
 * underneath the tunnel adds nothing and breaks the tunnel's origin handshake.
 *
 *   npm run dev:tunnel
 *   npx localtunnel --port 5173
 *
 * FOR DEMOS ONLY. Anything reachable at that URL is on the public internet:
 * run `python -m app.seed --reset` first so only synthetic data is exposed.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    // Only the domains tunnels actually serve from. A leading dot means the
    // domain and its subdomains; these resolve to nothing else.
    allowedHosts: [
      '.trycloudflare.com',
      '.loca.lt',
      '.ngrok-free.app',
      '.ngrok.io',
    ],
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
