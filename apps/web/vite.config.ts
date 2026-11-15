import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/** 前端 dev 端口（契约 §3） */
const DEV_PORT = 5274;
/** 后端 FastAPI 地址（契约 §3、§7 SHIGUANG_PORT） */
const API_TARGET = 'http://127.0.0.1:8720';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // 与 tsconfig.json 的 paths 保持一致，禁止硬编码盘符
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: DEV_PORT,
    strictPort: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // 首屏性能：依赖单独成块，便于浏览器长缓存
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
});
