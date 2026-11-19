import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    // Pas de cartes de sources en production : le code n'est pas offert en clair.
    sourcemap: false,
    assetsInlineLimit: 0,
  },
  server: {
    port: 5173,
    // En développement, l'API est appelée à travers la passerelle HTTPS.
    proxy: { "/api": { target: "https://localhost:9443", changeOrigin: true, secure: false } },
  },
});
