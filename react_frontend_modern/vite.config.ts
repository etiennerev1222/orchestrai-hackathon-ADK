import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc' // <-- Changer ici pour -swc

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    hmr: false // Désactive le Hot Module Replacement pour voir si ça aide
  }
  // Optionnel mais peut parfois aider si l'erreur revient:
  // esbuild: {
  //   jsx: 'automatic', // Ce devrait déjà être le cas par défaut pour .tsx
  // },
})
