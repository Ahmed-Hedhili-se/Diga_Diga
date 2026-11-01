import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite on :5173 proxies /api to FastAPI (same origin for the cookie).
// Prod: `npm run build`; FastAPI serves frontend/dist under the strict CSP (see backend/app/security.py).
//
// LAN (docs/lan_setup.md): run.ps1 sets HG_VITE_HOST=0.0.0.0 so teammates can open http://<ip>:5173.
// A frontend developer on another machine points the proxy at the backend machine with
//   VITE_BACKEND_URL=http://<backend-ip>:8000 npm run dev
// The browser only ever talks to /api on this origin: never to the Modal model URL, which needs
// backend-held credentials.
const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; " +
  "connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", ""); // "" prefix: .env files plus the shell environment
  const backend = (env.VITE_BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");
  const host = env.HG_VITE_HOST || "0.0.0.0";
  const proxy = { "/api": { target: backend, changeOrigin: false } };
  return {
    plugins: [react()],
    server: { host, port: 5173, strictPort: true, proxy },
    preview: {
      host,
      port: 4173,
      proxy,
      headers: { "Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff" },
    },
    build: { sourcemap: false, chunkSizeWarningLimit: 1500 },
  };
});
