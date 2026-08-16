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
          subtle: "#f0f6f5",
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
          muted: "#f1f6f3",
        },
        background: "#f8faf9",
        "text-primary": "#11211e",
        "text-secondary": "#4b635d",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
