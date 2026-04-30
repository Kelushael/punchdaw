/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        stone: {
          slab: '#1a1a1a',
          dark: '#111111',
          border: '#333333',
        },
        neon: {
          cyan: '#00f7ff',
          green: '#39ff14',
          pink: '#ff00ff',
          red: '#ff0000',
        },
        forge: {
          bg: '#0a0a08',
          panel: '#141410',
          line: '#2d2a22',
          text: '#f2ebd9',
          muted: '#9e9684',
          accent: '#ff9f1c',
        }
      },
      fontFamily: {
        mono: ['Consolas', '"Liberation Mono"', 'Menlo', 'monospace'],
        pixel: ['"Press Start 2P"', 'system-ui'],
      }
    },
  },
  plugins: [],
}
