import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split the heavy charting library from app code so the vendor chunk
        // caches independently across deploys.
        manualChunks: {
          echarts: ["echarts"],
          vendor: ["vue", "vue-router", "pinia"],
        },
      },
    },
  },
});
