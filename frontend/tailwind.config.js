/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./App.vue",
    "./main.js",
    "./components/**/*.{vue,js,ts,jsx,tsx}",
    "./views/**/*.{vue,js,ts,jsx,tsx}",
    "./i18n/**/*.{js,ts}",
    "./locales/**/*.{json}",
  ],
  theme: {
    extend: {},
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
