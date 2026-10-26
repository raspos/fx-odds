import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",  // GitHub Pages 프로젝트 사이트(/저장소이름/)에서도 동작하도록 상대 경로
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1500 },
});
