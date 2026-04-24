import { defineConfig } from 'vite';
import { resolve } from 'path';

// https://vitejs.dev/config/
export default defineConfig({
    base: '/', // Base path for GitHub Pages (vladislav-vasilenko.github.io)
    build: {
        rollupOptions: {
            input: {
                main: resolve(__dirname, 'index.html'),
                matcher: resolve(__dirname, 'matcher.html'),
                scrape: resolve(__dirname, 'scrape.html'),
            }
        }
    }
});
