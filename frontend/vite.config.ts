import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {host: '127.0.0.1', port: 5173, strictPort: true,
    fs: {deny: ['.env', '.env.*', '*.{crt,pem}', '**/.git/**', '**/.local/**']},
    proxy: {'/api': process.env.LIFEAGENT_API_TARGET || 'http://127.0.0.1:8000',
            '/health': process.env.LIFEAGENT_API_TARGET || 'http://127.0.0.1:8000'}},
});
