/** @type {import('tailwindcss').Config} */
// Palette colours are CSS variables so themes (src/themes.css) can swap them
const v = name => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        white: 'rgb(var(--c-white) / <alpha-value>)',
        gray: { 50: v('gray-50'), 100: v('gray-100'), 200: v('gray-200'), 300: v('gray-300'), 400: v('gray-400'), 500: v('gray-500'), 600: v('gray-600'), 700: v('gray-700'), 800: v('gray-800'), 900: v('gray-900'), 950: v('gray-950') },
        brand: { 50: v('brand-50'), 100: v('brand-100'), 200: v('brand-200'), 300: v('brand-300'), 400: v('brand-400'), 500: v('brand-500'), 600: v('brand-600'), 700: v('brand-700'), 800: v('brand-800'), 900: v('brand-900'), 950: v('brand-950') },
        red: { 50: v('red-50'), 100: v('red-100'), 200: v('red-200'), 300: v('red-300'), 400: v('red-400'), 500: v('red-500'), 600: v('red-600'), 700: v('red-700'), 800: v('red-800'), 900: v('red-900'), 950: v('red-950') },
        green: { 50: v('green-50'), 100: v('green-100'), 200: v('green-200'), 300: v('green-300'), 400: v('green-400'), 500: v('green-500'), 600: v('green-600'), 700: v('green-700'), 800: v('green-800'), 900: v('green-900'), 950: v('green-950') },
        emerald: { 50: v('emerald-50'), 100: v('emerald-100'), 200: v('emerald-200'), 300: v('emerald-300'), 400: v('emerald-400'), 500: v('emerald-500'), 600: v('emerald-600'), 700: v('emerald-700'), 800: v('emerald-800'), 900: v('emerald-900'), 950: v('emerald-950') },
        blue: { 50: v('blue-50'), 100: v('blue-100'), 200: v('blue-200'), 300: v('blue-300'), 400: v('blue-400'), 500: v('blue-500'), 600: v('blue-600'), 700: v('blue-700'), 800: v('blue-800'), 900: v('blue-900'), 950: v('blue-950') },
        amber: { 50: v('amber-50'), 100: v('amber-100'), 200: v('amber-200'), 300: v('amber-300'), 400: v('amber-400'), 500: v('amber-500'), 600: v('amber-600'), 700: v('amber-700'), 800: v('amber-800'), 900: v('amber-900'), 950: v('amber-950') },
        yellow: { 50: v('yellow-50'), 100: v('yellow-100'), 200: v('yellow-200'), 300: v('yellow-300'), 400: v('yellow-400'), 500: v('yellow-500'), 600: v('yellow-600'), 700: v('yellow-700'), 800: v('yellow-800'), 900: v('yellow-900'), 950: v('yellow-950') },
        orange: { 50: v('orange-50'), 100: v('orange-100'), 200: v('orange-200'), 300: v('orange-300'), 400: v('orange-400'), 500: v('orange-500'), 600: v('orange-600'), 700: v('orange-700'), 800: v('orange-800'), 900: v('orange-900'), 950: v('orange-950') },
        purple: { 50: v('purple-50'), 100: v('purple-100'), 200: v('purple-200'), 300: v('purple-300'), 400: v('purple-400'), 500: v('purple-500'), 600: v('purple-600'), 700: v('purple-700'), 800: v('purple-800'), 900: v('purple-900'), 950: v('purple-950') },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(-4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
