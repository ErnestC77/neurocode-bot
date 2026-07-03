import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Вывод в ./dist; FastAPI раздаёт эту папку как Mini App (см. api/app.py).
// Dev-прокси перенаправляет /api на локально запущенный `uvicorn asgi:app`.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
