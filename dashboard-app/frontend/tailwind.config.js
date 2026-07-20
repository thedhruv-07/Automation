/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          primary: "#0b0b0b",
          secondary: "#52514e",
          muted: "#898781",
        },
        surface: {
          DEFAULT: "#fcfcfb",
          page: "#f9f9f7",
        },
        line: "#e1e0d9",
        accent: {
          DEFAULT: "#2a78d6",
          dark: "#184f95",
        },
        status: {
          good: "#0ca30c",
          warning: "#fab219",
          serious: "#ec835a",
          critical: "#d03b3b",
        },
      },
    },
  },
  plugins: [],
};
