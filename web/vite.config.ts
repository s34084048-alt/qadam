import fs from 'node:fs'
import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * HTTPS for phone testing.
 *
 * getUserMedia only exists in a "secure context": HTTPS, or localhost. A phone
 * opening http://192.168.x.x is neither, so the browser removes the camera API
 * entirely — the app is not broken, the platform has withdrawn the capability.
 *
 * Running the dev server over TLS with a locally generated certificate makes
 * the LAN address a secure context and the camera reappears. The certificate
 * is self-signed, so the phone shows a warning once; accepting it is what makes
 * the origin secure.
 *
 * Generate the pair (already done if certs/ exists):
 *   openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
 *     -keyout certs/dev-key.pem -out certs/dev-cert.pem -config certs/openssl.cnf
 *
 * Add your machine's LAN address to `certs/openssl.cnf` under [alt] and
 * regenerate if it changes. DEVELOPMENT ONLY — never ship this certificate.
 */
function devHttps() {
  const key = path.resolve(__dirname, 'certs/dev-key.pem')
  const cert = path.resolve(__dirname, 'certs/dev-cert.pem')
  if (!fs.existsSync(key) || !fs.existsSync(cert)) return undefined
  return { key: fs.readFileSync(key), cert: fs.readFileSync(cert) }
}

const https = devHttps()

// Vite rejects unknown Host headers as a DNS-rebinding precaution, which
// blocks tunnelled demo links. Rather than disabling the check, allow only the
// domains that tunnels actually serve from — a leading dot means "this domain
// and its subdomains", and these resolve to nothing else.
const allowedHosts = [
  '.trycloudflare.com',
  '.loca.lt',
  '.ngrok-free.app',
  '.ngrok.io',
]

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    https,
    allowedHosts,
    proxy: {
      // Same-origin API, so no token ever travels in a query string and the
      // phone needs only one address.
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  preview: { port: 5173, host: '0.0.0.0', https },
})
