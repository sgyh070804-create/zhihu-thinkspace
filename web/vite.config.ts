import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { experiencesPlugin } from "./experiences.mjs";

export default defineConfig({
  plugins: [vue(), experiencesPlugin()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
