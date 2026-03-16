/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0a0a0c",
        surface: "rgba(255, 255, 255, 0.05)",
        glass: "rgba(255, 255, 255, 0.03)",
        accent: {
          cyan: "#00f2ff",
          purple: "#7000ff",
          emerald: "#00ff88",
        }
      },
      backdropBlur: {
        xs: "2px",
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}
