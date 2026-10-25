import { defineConfig } from 'vite';
import { resolve } from 'path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vitejs.dev/config/
export default defineConfig({
    base: '/', // Base path for GitHub Pages (vladislav-vasilenko.github.io)
    // React + Tailwind only touch the latent.html island; the CV pages stay plain TypeScript.
    plugins: [react(), tailwindcss()],
    build: {
        rollupOptions: {
            input: {
                main: resolve(__dirname, 'index.html'),
                matcher: resolve(__dirname, 'matcher.html'),
                scrape: resolve(__dirname, 'scrape.html'),
                latent: resolve(__dirname, 'latent.html'),
            }
        }
    }
});
