/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: '#0a0d14',
          surface: '#111726',
          card: '#161f33',
          border: '#1f2d4a',
          hover: '#243456',
          muted: '#64748b',
          text: '#f1f5f9',
          subtext: '#94a3b8',
        },
        trade: {
          bull: '#10b981',
          bullBg: 'rgba(16, 185, 129, 0.12)',
          bullBorder: '#059669',
          bear: '#f43f5e',
          bearBg: 'rgba(244, 63, 94, 0.12)',
          bearBorder: '#e11d48',
          wait: '#f59e0b',
          waitBg: 'rgba(245, 158, 11, 0.12)',
          waitBorder: '#d97706',
          epm: '#8b5cf6',
          epmBg: 'rgba(139, 92, 246, 0.12)',
          epmBorder: '#7c3aed',
        }
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', '"Liberation Mono"', '"Courier New"', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
