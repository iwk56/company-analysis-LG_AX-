import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 브라우저는 5173(프론트)만 부르고, /api는 백엔드(8000)로 넘긴다 → 백엔드에 CORS 설정이 필요 없다
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
