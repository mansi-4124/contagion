export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#1B2A4A',
          light: '#243660',
          dark: '#111B30',
        },
        accent: {
          DEFAULT: '#C0392B',
          light: '#E74C3C',
        },
        teal: {
          DEFAULT: '#16A085',
          light: '#1ABC9C',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Calibri', 'sans-serif'],
      },
    },
  },
  plugins: []
}