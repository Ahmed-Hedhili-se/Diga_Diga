import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite on :5173 proxies /api to FastAPI on :8000 (same origin for the cookie).
// Prod: `npm run build`; FastAPI serves frontend/dist under the strict CSP (see backend/app/security.py).
const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; " +
  "connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } },
  },
  preview: {
    port: 4173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } },
    headers: { "Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff" },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 1500 },
});
