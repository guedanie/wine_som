// frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink:            '#1A1A1A',
        body:           '#33312C',
        faded:          '#6B6453',
        bordeaux:       '#6E1023',
        'bordeaux-deep':'#560B1B',
        'bordeaux-tint':'#F4E6E2',
        brass:          '#B08D57',
        sage:           '#7C8A5A',
        paper:          '#EFE6D4',
        cream:          '#F5EFE6',
        'cream-raised': '#FBF8F2',
      },
      fontFamily: {
        serif: ['"DM Serif Display"', 'Georgia', 'serif'],
        sans:  ['Archivo', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
