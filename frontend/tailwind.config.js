/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        vms: {
          darkest: "#0b0e14",
          panel: "#131720",
          card: "#1a202c",
          border: "#283244",
          hover: "#252e3e",
          accent: "#00f0ff",
          alarm: "#ff2a55",
          warning: "#ffb703",
          success: "#06d6a0",
          text: "#e2e8f0",
          muted: "#8892b0"
        }
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "Courier New", "monospace"]
      }
    },
  },
  plugins: [],
}
