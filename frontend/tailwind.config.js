/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#0d3a35",
          hover: "#144d47",
          dark: "#072421",
          light: "#e6f0ee",
          subtle: "#f1f5f4",
        },
        secondary: {
          DEFAULT: "#10b981",
          foreground: "#ffffff",
        },
        accent: {
          DEFAULT: "#10b981",
          foreground: "#ffffff",
        },
        income: {
          DEFAULT: "#0d3a35",
          light: "#e6f0ee",
          text: "#0d3a35",
        },
        expense: {
          DEFAULT: "#dc2626",
          light: "#fee2e2",
          text: "#b91c1c",
        },
        surface: {
          DEFAULT: "#ffffff",
          muted: "#f1f5f4",
        },
        background: "#f1f5f4",
        "text-primary": "#1a1a1a",
        "text-secondary": "#6b7280",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "1.5rem",
      },
    },
  },
  plugins: [],
};
