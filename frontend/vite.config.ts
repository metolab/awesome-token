import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const backend = env.VITE_BACKEND_URL || "http://127.0.0.1:8000"

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      allowedHosts: [
        "bibi.devcloud.woa.com",
        ".devcloud.woa.com",
        "localhost",
      ],
      // changeOrigin must be false so the browser Host (e.g. bibi.devcloud.woa.com:5173) is
      // forwarded to FastAPI. Otherwise 307 redirects for trailing slashes use Location:
      // http://127.0.0.1:8000/... and the browser hits loopback (Private Network Access block).
      proxy: {
        "/api": {
          target: backend,
          changeOrigin: false,
        },
        "/auth": {
          target: backend,
          changeOrigin: false,
        },
        "/openapi": {
          target: backend,
          changeOrigin: false,
        },
      },
    },
  }
})
