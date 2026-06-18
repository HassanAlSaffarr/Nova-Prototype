import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // GENQ dark brand
        bg: "#0a0e1a",          // near-black navy
        surface: "#111726",     // panel background
        "surface-2": "#1a2236", // raised panel
        border: "#243049",
        accent: "#00ff9d",      // neon green
        cyan: "#22d3ee",
        muted: "#8a94ad",
        text: "#e8edf7",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
